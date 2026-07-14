"""
Dashboard principal de Quartermaster.

v2 (Fase 1 completa -- migración a API): esta página ya NO importa nada
de `domain.*` / `application.*` / `infrastructure.*`. Es un cliente HTTP
de la API FastAPI (`api_client.py`) -- exactamente el mismo dato que
antes calculaba localmente llamando a `DetectOpportunitiesUseCase`
directo, ahora viene de `GET /api/opportunities`. Ver
docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §6 (Fase 1) para el
razonamiento completo.

Regla de capa (sin cambios): esta página NUNCA decide reglas de negocio
(umbrales de score, de liquidez, etc.) -- solo lee lo que
`OpportunityEngine` ya decidió del otro lado del HTTP
(`recommendation` / `recommendation_reason`) y lo pinta.

Simplificación real habilitada por la nueva arquitectura: antes había
DOS botones separados en el sidebar ("Refrescar order books" e
"Importar volumen histórico"), porque Streamlit orquestaba los imports
de ESI a mano, ítem por ítem. Ahora un solo Smart Auto-Seed
(`POST /api/sync/seed`) cubre TODA la región (order book completo +
historial acotado a lo que tiene actividad real) en un job de
background del lado del server -- no hace falta que Streamlit sepa
nada de ESI en absoluto.
"""

import sys
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    """Sube directorios hasta encontrar la raíz del proyecto (la que contiene `src/`)."""
    current = start
    while not (current / "src").exists() and current.parent != current:
        current = current.parent
    return current


sys.path.insert(0, str(_find_project_root(Path(__file__).resolve()) / "src"))

import streamlit as st
from presentation.api_client import ApiClient, ApiConnectionError
from presentation.streamlit_app.components.opportunity_table import (
    render_opportunity_card, show_opportunity_table, render_market_summary_bar
)
from presentation.streamlit_app.theme import inject_theme
from presentation.streamlit_app.auth_ui import restore_session_from_query_params, render_login_sidebar

# URL de esta misma página -- a dónde EVE SSO devuelve al browser
# después del login. Hardcodeada al puerto convencional de Streamlit en
# este proyecto (8501); si se despliega en otro host/puerto, esto
# debería salir de una variable de entorno en vez de estar fijo acá.
CURRENT_PAGE_URL = "http://localhost:8501/"

st.set_page_config(page_title="Quartermaster", page_icon="📡", layout="wide")
inject_theme()
st.title("📡 Quartermaster — Dashboard de Oportunidades de Mercado (Jita)")


def get_client() -> ApiClient:
    """
    v2 (multi-tenancy): a propósito SIN `@st.cache_resource`. Ese
    decorador comparte UNA instancia entre TODAS las sesiones de
    usuario del proceso -- estaba bien mientras `ApiClient` no tenía
    estado propio, pero ahora `session_token` vive en la instancia. Si
    se compartiera, el token de un usuario podría filtrarse al request
    de otro (dos personas usando el mismo server Streamlit al mismo
    tiempo). Construir un cliente nuevo por rerun es barato (un
    `requests.Session()`) y es lo que garantiza que cada sesión de
    Streamlit tenga su propio token, sin cruces.
    """
    return ApiClient()


client = get_client()
restore_session_from_query_params(client)

# === Chequeo de salud: si la API no está corriendo, avisar claro en vez
# de que Streamlit tire un traceback crudo de requests.ConnectionError ===
if not client.health_check():
    st.error(
        "🔌 **No se pudo conectar a la API.**\n\n"
        "Quartermaster ahora corre como cliente de una API separada. Antes de usar el "
        "dashboard, abrí OTRA terminal y dejala corriendo con:\n\n"
        "```powershell\n"
        "python -m uvicorn presentation.api.main:app --reload --app-dir src\n"
        "```\n\n"
        "Esperá a que diga `Application startup complete.`, después recargá esta página."
    )
    st.stop()

# === Sidebar controls ===
render_login_sidebar(client, current_page_url=CURRENT_PAGE_URL)

st.sidebar.header("⚙️ Filtros de Análisis")
min_score = st.sidebar.slider("Score mínimo de oportunidad", 40, 95, 55, step=1)
max_results = st.sidebar.slider("Máx. oportunidades a mostrar", 5, 50, 20)
exclude_caution = st.sidebar.checkbox(
    "Ocultar ítems en categorías de precaución",
    value=False,
    help="Saca del ranking los ítems marcados caution_* (order book fino, liquidez fantasma, "
         "sin volumen, riesgo alto). El score no se toca, es solo un filtro de vista.",
)

st.sidebar.divider()
st.sidebar.subheader("📋 Watchlist actual")

if client.is_authenticated:
    try:
        tracked = client.list_tracked()
    except ApiConnectionError as e:
        st.sidebar.error(str(e))
        tracked = []
else:
    tracked = []

if tracked:
    st.sidebar.success(f"**{len(tracked)}** productos trackeados")
    for item in tracked[:8]:
        st.sidebar.write(f"• {item['name']}")
    if len(tracked) > 8:
        st.sidebar.caption(f"... y {len(tracked) - 8} más")
elif not client.is_authenticated:
    st.sidebar.info("Iniciá sesión con tu personaje de EVE para tener tu propia watchlist.")
else:
    st.sidebar.info("Modo Discovery: mostrando mejores oportunidades del mercado general.")

st.sidebar.divider()
st.sidebar.subheader("🌍 Sincronización de mercado")

try:
    sync_status = client.get_sync_status()
except ApiConnectionError:
    sync_status = None

if sync_status and sync_status["phase"] in ("orders", "history"):
    st.sidebar.info(f"⏳ Sync en curso: {sync_status.get('detail', sync_status['phase'])}")

    total = sync_status.get("total")
    done = sync_status.get("done")
    if total and done is not None and total > 0:
        st.sidebar.progress(min(done / total, 1.0))

    eta_human = sync_status.get("eta_human")
    if eta_human:
        st.sidebar.caption(f"⏱️ Tiempo estimado restante: {eta_human}")
    else:
        st.sidebar.caption(
            "⏱️ Todavía no hay suficiente progreso para estimar cuánto falta -- "
            "recargá en un momento."
        )

    st.sidebar.caption(
        "💡 Mientras el sync está en curso, es normal que Discovery muestre pocos "
        "ítems (o ninguno) -- todavía no terminó de traer todo el mercado. No está "
        "colgado, solo está trabajando."
    )
    if st.sidebar.button("🔄 Actualizar progreso"):
        st.rerun()
else:
    if sync_status and sync_status["phase"] == "completed":
        st.sidebar.caption(f"✅ Último sync: {sync_status.get('detail', '')}")
    elif sync_status and sync_status["phase"] == "error":
        st.sidebar.warning(f"⚠️ El último sync falló: {sync_status.get('error', '')}")

    if st.sidebar.button("🚀 Sincronizar todo Jita (Smart Auto-Seed)"):
        try:
            resp = client.trigger_seed()
            if resp["status"] == "already_running":
                st.sidebar.warning(resp["message"])
            else:
                st.sidebar.success(
                    "Sync encolado en el server. Puede tardar minutos (el order book completo "
                    "es rápido, el historial de volumen es más lento) -- vas a ver el progreso "
                    "y el tiempo estimado acá mismo apenas arranque."
                )
        except ApiConnectionError as e:
            st.sidebar.error(str(e))
        st.rerun()

# === Main logic ===
if not tracked:
    st.info("📌 **Modo Discovery activado** — Mostrando las mejores oportunidades del mercado Jita con datos reales.")
    st.caption("Se buscan items que tengan order book activo (compra + venta). Trackeá items específicos desde 'Tracked Items' para análisis más profundos y automáticos.")
    scope = "discovery"
else:
    st.success(f"🎯 Analizando tus **{len(tracked)}** productos trackeados en Jita.")
    scope = "tracked"

try:
    with st.spinner("Consultando la API (ROI, Liquidez, Riesgo, Competencia, Exit Time)..."):
        page = client.get_opportunities(
            scope=scope, min_score=min_score, max_results=max_results,
            sort_by="score", sort_desc=True, exclude_caution=exclude_caution,
        )
except ApiConnectionError as e:
    st.error(str(e))
    st.stop()

is_discovery = scope == "discovery"

if page["opportunities"]:
    opportunities_to_show = page["opportunities"]
    label = "Mejores Oportunidades en Jita" if is_discovery else "Oportunidades Detectadas"
    st.subheader(f"📊 {label} ({len(opportunities_to_show)} de {page['total_with_data']} con datos)")
elif page["total_with_data"] > 0:
    # Nada cruzó el umbral de score -- pedimos lo mejor disponible igual
    # (min_score=0) para que el usuario nunca se quede en blanco si hay
    # evidencia suficiente para al menos un ítem.
    fallback_page = client.get_opportunities(
        scope=scope, min_score=0, max_results=15,
        sort_by="score", sort_desc=True, exclude_caution=exclude_caution,
    )
    opportunities_to_show = fallback_page["opportunities"]
    st.warning(
        f"⚠️ Ninguno de los {page['total_with_data']} items con datos reales superó tu score mínimo ({min_score}). "
        f"Mostrando los {len(opportunities_to_show)} mejores igual, para que siempre tengas algo que mirar — "
        "pero ojo, esto no es una recomendación de compra, es 'lo menos malo disponible ahora'. "
        "Bajá el slider de score mínimo en la barra lateral si querés ver más."
    )
    st.subheader(f"📊 Mejores {len(opportunities_to_show)} disponibles (todos por debajo de {min_score})")
else:
    opportunities_to_show = []
    st.subheader("📊 Oportunidades Detectadas (0 con datos)")

if opportunities_to_show:
    render_market_summary_bar(opportunities_to_show, page["total_with_data"])
    st.divider()

    view_mode = st.radio(
        "Vista",
        ["🗂️ Tarjetas (detalle + desglose)", "📊 Tabla (ordenable por columna)"],
        horizontal=True,
        label_visibility="collapsed",
        key="dashboard_view_mode",
    )
    if view_mode.startswith("📊"):
        show_opportunity_table(opportunities_to_show)
        st.caption(
            "💡 Click en el header de cualquier columna (Score, ROI %, Liquidez, etc.) "
            "para ordenar — de nuevo para invertir el orden."
        )
    else:
        for i, o in enumerate(opportunities_to_show, start=1):
            render_opportunity_card(o, rank=i)
else:
    if page["total_with_data"] == 0:
        st.info(
            "Ninguno de los productos evaluados tiene snapshots completos de order book "
            "todavía. Si nunca corriste un Smart Auto-Seed, hacelo desde el botón del sidebar "
            "('🚀 Sincronizar todo Jita')."
        )

# Resumen (formato legible)
with st.expander("📈 Resumen del análisis", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("Items evaluados", page["total_evaluated"])
    c2.metric("Con datos reales", page["total_with_data"])
    c3.metric("Score mínimo usado", f"{min_score:.0f}")

    if opportunities_to_show:
        avg_score = sum(o["score"] for o in opportunities_to_show) / len(opportunities_to_show)
        avg_roi = sum(o["roi_percent"] for o in opportunities_to_show) / len(opportunities_to_show)
        n_no_volume = sum(
            1 for o in opportunities_to_show
            if not o["score_breakdown"].get("has_volume_evidence", True)
        )
        st.success(f"**Promedio de las mostradas:** Score {avg_score:.1f}  |  ROI {avg_roi:.1f}%")
        if n_no_volume:
            st.caption(f"📉 {n_no_volume} de {len(opportunities_to_show)} ítems mostrados no tienen historial de "
                       "volumen importado (liquidez tratada conservadoramente como desconocida).")

st.divider()
st.caption("Quartermaster • Clean Architecture + DDD • Cliente de API FastAPI • Datos en tiempo real desde ESI (Tranquility)")
