"""
Gestión de Productos Trackeados.

v2 (Fase 1 completa -- migración a API): tracking, búsqueda, y
score/recomendación de cada ítem ahora vienen de la API FastAPI vía
`api_client.py` -- ya NO se llama a `DetectOpportunitiesUseCase` ni a
los repos de mercado directo. Ver
docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §6.

Excepción deliberada, documentada acá para que no parezca un
descuido: el explorador de Categoría → Grupo (metadata local del SDE
de EVE, archivos `sde/categories.jsonl` / `sde/groups.jsonl`) sigue
usando `SQLiteTypeRepository` directo. Es lectura de datos estáticos
del juego sin ninguna relación con ESI ni con el pipeline de mercado
-- exponerlo detrás de la API no aporta nada al objetivo de esta fase
(que es el pipeline de trading intelligence), así que no se migró.

Simplificación real habilitada por la nueva arquitectura: el botón de
"Panorama General" (que antes armaba una muestra aleatoria de items y
orquestaba el import de ESI a mano, ítem por ítem, desde Streamlit) ya
no tiene sentido -- el Smart Auto-Seed del Dashboard sincroniza TODA
la región de una vez, sin necesidad de elegir una muestra. Se
reemplaza por un simple recordatorio + acceso directo a ese botón.
"""

import sys
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    """Ver docstring gemela en app.py. Sube directorios hasta encontrar la raíz del proyecto."""
    current = start
    while not (current / "src").exists() and current.parent != current:
        current = current.parent
    return current


sys.path.insert(0, str(_find_project_root(Path(__file__).resolve()) / "src"))

import json

import streamlit as st
from presentation.api_client import ApiClient, ApiConnectionError
from presentation.streamlit_app.components.opportunity_table import (
    render_recommendation_badge, render_score_breakdown, render_explanation, show_opportunity_table,
    recommendation_banner_html
)
from presentation.streamlit_app.theme import inject_theme, score_pill_html, risk_badge_html, liquidity_pill_html
from presentation.streamlit_app.auth_ui import restore_session_from_query_params, render_login_sidebar

# Excepción documentada arriba: solo para browsing de metadata SDE local.
from infrastructure.repositories.sqlite_type_repository import SQLiteTypeRepository

CURRENT_PAGE_URL = "http://localhost:8501/tracked_items"

st.set_page_config(page_title="Tracked Items - Quartermaster", page_icon="📋", layout="wide")
inject_theme()
st.title("📋 Gestión de Productos Trackeados")


def get_client() -> ApiClient:
    """
    v2 (multi-tenancy): a propósito SIN `@st.cache_resource` -- ver
    docstring gemela en `app.py`. `session_token` vive en la instancia,
    compartirla entre sesiones de usuario mezclaría credenciales.
    """
    return ApiClient()


@st.cache_resource
def get_sde_repo() -> SQLiteTypeRepository:
    """Solo para el explorador de Categoría → Grupo, ver docstring del módulo."""
    return SQLiteTypeRepository()


client = get_client()
sde_repo = get_sde_repo()
restore_session_from_query_params(client)

if not client.health_check():
    st.error(
        "🔌 **No se pudo conectar a la API.** Abrí otra terminal y corré:\n\n"
        "```powershell\npython -m uvicorn presentation.api.main:app --reload --app-dir src\n```\n\n"
        "Esperá a `Application startup complete.` y recargá esta página."
    )
    st.stop()

render_login_sidebar(client, current_page_url=CURRENT_PAGE_URL)

# Esta página entera gira alrededor de "tu" watchlist personal -- a
# diferencia del Dashboard (que tiene Discovery como modo sin sesión),
# acá no hay un modo anónimo con sentido. Login obligatorio.
if not client.is_authenticated or client.get_me() is None:
    st.info(
        "🔐 **Necesitás iniciar sesión con tu personaje de EVE para gestionar tu watchlist "
        "personal.** Usá el botón en la barra lateral."
    )
    st.stop()

try:
    tracked_items = client.list_tracked()
except ApiConnectionError as e:
    st.error(str(e))
    st.stop()

tracked_ids = [item["type_id"] for item in tracked_items]
tracked_names_by_id = {item["type_id"]: item["name"] for item in tracked_items}

# ============================================================
# NAVEGACIÓN PRINCIPAL
# ============================================================
active_view = st.radio(
    "Sección",
    ["📋 Tracked Items (Mis seleccionados)", "🔍 Buscar y Agregar"],
    horizontal=True,
    label_visibility="collapsed",
    key="tracked_items_page_view",
)
st.divider()

# ============================================================
# SECCIÓN 1: TRACKED ITEMS
# ============================================================
if active_view.startswith("📋"):
    st.subheader("Productos que estás trackeando actualmente")

    if tracked_ids:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"Tienes **{len(tracked_ids)}** productos en tu watchlist.")
        with col2:
            if st.button("🗑️ Eliminar TODOS los trackeados", type="secondary"):
                if st.session_state.get("confirm_delete_all", False):
                    with st.spinner(f"Eliminando {len(tracked_ids)} productos..."):
                        deleted = client.untrack_all()
                    st.success(f"✅ Se eliminaron {deleted} productos.")
                    st.session_state["confirm_delete_all"] = False
                    st.rerun()
                else:
                    st.session_state["confirm_delete_all"] = True
                    st.warning("⚠️ ¿Estás seguro? Esta acción no se puede deshacer. Presioná el botón nuevamente para confirmar.")

    if tracked_ids:
        show_only_without_data = st.checkbox("Mostrar solo los que NO tienen datos importados", value=False)

        # Una sola llamada a la API trae score/recomendación para TODOS
        # los trackeados que ya tienen order book bidireccional completo
        # -- los que no aparecen acá todavía no tienen datos importados
        # (import pendiente o recién trackeados).
        with st.spinner("Consultando la API..."):
            page = client.get_opportunities(scope="tracked", min_score=0, max_results=len(tracked_ids), sort_by="score")
        opportunities_by_id = {o["type_id"]: o for o in page["opportunities"]}

        items_to_show = []
        for tid in tracked_ids:
            has_data = tid in opportunities_by_id
            if show_only_without_data and has_data:
                continue
            items_to_show.append({"id": tid, "name": tracked_names_by_id[tid], "has_data": has_data})

        if items_to_show:
            st.caption(f"Mostrando {len(items_to_show)} de {len(tracked_ids)} productos trackeados.")

            default_view_table = len(items_to_show) > 50
            view_mode = st.radio(
                "Vista",
                ["✅ Gestión (marcar / quitar)", "📊 Tabla resumen (ordenable, rápida)"],
                index=1 if default_view_table else 0,
                horizontal=True,
                label_visibility="collapsed",
                key="tracked_view_mode",
            )

            if view_mode.startswith("📊"):
                table_opportunities = list(opportunities_by_id.values())
                if table_opportunities:
                    show_opportunity_table(table_opportunities)
                    st.caption(
                        "💡 Click en el header de cualquier columna (Score, ROI %, Liquidez, etc.) "
                        "para ordenar. Los ítems sin order book importado no tienen score y no "
                        "aparecen acá -- usá la vista de Gestión para verlos."
                    )
                else:
                    st.info("Ninguno de los ítems mostrados tiene datos de mercado importados todavía.")

            else:
                selected_to_remove = []
                for item in items_to_show:
                    col1, col2, col3 = st.columns([6, 2.5, 1.5])
                    with col1:
                        label = f"**{item['name']}** (ID: {item['id']})"
                        checked = st.checkbox(label, value=True, key=f"track_{item['id']}")
                        if not checked:
                            selected_to_remove.append(item['id'])

                        o = opportunities_by_id.get(item['id'])
                        if o:
                            st.markdown(
                                f'{score_pill_html(o["score"])} &nbsp; '
                                f'<span class="jt-mono">ROI {o["roi_percent"]:.1f}%</span> &nbsp; '
                                f'{risk_badge_html(o["risk"]["risk_level"])} &nbsp; '
                                f'{liquidity_pill_html(o["liquidity"]["liquidity_score"])}',
                                unsafe_allow_html=True,
                            )
                            st.markdown(recommendation_banner_html(o), unsafe_allow_html=True)
                            with st.expander("🔍 Ver análisis completo"):
                                st.caption(o.get("recommendation_reason", ""))
                                if o.get("explanation"):
                                    render_explanation(o["explanation"])
                                    st.divider()
                                st.markdown("**📐 Desglose numérico del score**")
                                render_score_breakdown(o["score_breakdown"])

                    with col2:
                        status = "✅ Datos importados" if item['has_data'] else "⏳ Sin datos de order book"
                        st.caption(status)

                    with col3:
                        if st.button("🗑️ Quitar", key=f"quick_untrack_{item['id']}"):
                            client.untrack_item(item['id'])
                            st.success(f"✅ {item['name']} quitado.")
                            st.rerun()

                if selected_to_remove:
                    if st.button(f"🗑️ Quitar los {len(selected_to_remove)} seleccionados", type="primary"):
                        with st.spinner(f"Quitando {len(selected_to_remove)} productos..."):
                            deleted = client.untrack_many(selected_to_remove)
                        st.success(f"✅ {deleted} productos quitados de la watchlist.")
                        st.rerun()
        else:
            st.info("No hay productos que cumplan el filtro actual.")
    else:
        st.info("Aún no tenés productos trackeados. Usá la sección **Buscar y Agregar** para empezar.")

# ============================================================
# SECCIÓN 2: BUSCAR Y AGREGAR
# ============================================================
elif active_view.startswith("🔍"):
    st.subheader("🔍 Buscar y Agregar productos")

    st.markdown("### Búsqueda libre por nombre")
    search_term = st.text_input(
        "Escribí cualquier parte del nombre",
        key="search_in_tab",
        placeholder="Ej: Scourge, Shield, Warp Disruptor, Tritanium..."
    )

    if search_term:
        try:
            results = client.search_items(search_term.strip(), limit=12)
        except ApiConnectionError as e:
            st.error(str(e))
            results = []

        if results:
            tracked_id_set = set(tracked_ids)
            for item in results:
                col1, col2 = st.columns([5.5, 2.5])
                with col1:
                    st.write(f"**{item['name']}** (ID: {item['id']})")
                with col2:
                    if item['id'] in tracked_id_set:
                        st.success("✅ Ya trackeado")
                    else:
                        if st.button("🚀 Trackear + Importar", key=f"search_track_{item['id']}", type="primary"):
                            # v2: antes esto bloqueaba Streamlit con un
                            # st.status() de varios pasos mientras esperaba
                            # a ESI. Ahora POST /api/tracked-items/{id}
                            # devuelve 202 inmediato -- el import de
                            # órdenes+historial corre en background del
                            # lado del server, Streamlit nunca espera.
                            try:
                                client.track_item(item['id'], reason=f"Búsqueda: {search_term}")
                                st.success(
                                    f"✅ {item['name']} trackeado. La importación de datos está "
                                    "corriendo en el server (unos segundos) -- recargá en un momento "
                                    "para ver el score."
                                )
                                st.rerun()
                            except ApiConnectionError as e:
                                st.error(str(e))
        else:
            st.info("No se encontraron resultados.")

    st.divider()

    # ============================================================
    # SMART AUTO-SEED (reemplaza al viejo "Panorama General")
    # ============================================================
    # v2: antes acá se armaba una muestra aleatoria de items y se
    # orquestaba el import de ESI a mano desde Streamlit. El Smart
    # Auto-Seed del Dashboard ya sincroniza TODA la región de una vez
    # (sin necesidad de elegir una muestra), así que esa lógica quedó
    # obsoleta -- se reemplaza por un acceso directo al mismo botón.
    st.markdown("### 🌍 Sincronizar todo Jita (recomendado en vez de trackear a mano)")
    st.caption(
        "En vez de buscar y trackear items uno por uno, el Smart Auto-Seed sincroniza el "
        "order book COMPLETO de Jita de una sola vez (todos los ítems con actividad real, "
        "no una muestra) -- el mismo botón está en el sidebar del Dashboard."
    )
    try:
        sync_status = client.get_sync_status()
    except ApiConnectionError:
        sync_status = None

    if sync_status and sync_status["phase"] in ("orders", "history"):
        st.info(f"⏳ Sync en curso: {sync_status.get('detail', sync_status['phase'])}")
    else:
        if st.button("🚀 Sincronizar todo Jita (Smart Auto-Seed)", type="primary"):
            try:
                resp = client.trigger_seed()
                if resp["status"] == "already_running":
                    st.warning(resp["message"])
                else:
                    st.success("Sync encolado en el server. Puede tardar minutos -- mirá el progreso en el sidebar del Dashboard.")
            except ApiConnectionError as e:
                st.error(str(e))

    st.divider()

    # ============================================================
    # IMPORTAR SDE (CATEGORÍAS Y GRUPOS) -- local, sin ESI, sin API
    # ============================================================
    with st.expander("📥 Importar / Actualizar nombres de Categorías y Grupos del SDE de EVE", expanded=False):
        st.caption("Usa los archivos `sde/categories.jsonl` y `sde/groups.jsonl` que están en la carpeta del proyecto.")

        if st.button("🚀 Importar SDE Ahora (Categorías + Grupos)", type="primary"):
            project_root = Path(__file__).resolve()
            while not (project_root / "src").exists() and not (project_root / "sde").exists() and project_root.parent != project_root:
                project_root = project_root.parent

            sde_dir = project_root / "sde"
            cat_file = sde_dir / "categories.jsonl"
            grp_file = sde_dir / "groups.jsonl"

            if not cat_file.exists() or not grp_file.exists():
                st.error("No se encontraron los archivos categories.jsonl y/o groups.jsonl en la carpeta 'sde/' del proyecto.")
            else:
                with st.spinner("Importando categorías y grupos del SDE... Esto puede tardar unos segundos."):
                    try:
                        conn = sde_repo._connect()

                        count_cat = 0
                        with open(cat_file, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    obj = json.loads(line)
                                    cat_id = obj.get("_key") or obj.get("id") or obj.get("categoryID")
                                    name = obj.get("name", {}).get("en") if isinstance(obj.get("name"), dict) else obj.get("name")
                                    if cat_id and name:
                                        conn.execute(
                                            "INSERT OR REPLACE INTO categories (id, name, published) VALUES (?, ?, 1)",
                                            (int(cat_id), str(name))
                                        )
                                        count_cat += 1

                        count_grp = 0
                        with open(grp_file, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    obj = json.loads(line)
                                    grp_id = obj.get("_key") or obj.get("id") or obj.get("groupID")
                                    cat_id = obj.get("categoryID") or obj.get("category_id")
                                    name = obj.get("name", {}).get("en") if isinstance(obj.get("name"), dict) else obj.get("name")
                                    if grp_id and cat_id and name:
                                        conn.execute(
                                            "INSERT OR REPLACE INTO groups (id, category_id, name, published) VALUES (?, ?, ?, 1)",
                                            (int(grp_id), int(cat_id), str(name))
                                        )
                                        count_grp += 1

                        conn.commit()
                        conn.close()

                        st.success(f"✅ Importación completada: {count_cat} categorías y {count_grp} grupos actualizados.")
                        st.info("Los nombres en el explorador ahora deberían ser los reales de EVE. Refrescá la página si es necesario.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error durante la importación: {e}")

    # ============================================================
    # EXPLORADOR POR CATEGORÍA Y GRUPO -- local, metadata SDE
    # (ver nota de scope en el docstring del módulo)
    # ============================================================
    st.markdown("### Explorar por Categoría → Grupo (SDE de EVE)")

    col_cat, col_group = st.columns(2)

    with col_cat:
        categories = sde_repo.get_distinct_categories()
        if categories:
            cat_options = {
                f"{c.get('category_id', c.get('id', '?'))} — {c.get('name', c.get('example_name', 'Sin nombre'))} ({c['item_count']} items)": c.get('category_id', c.get('id'))
                for c in categories
            }
            selected_cat_label = st.selectbox(
                "1. Elegí una Categoría", options=list(cat_options.keys()), index=0, key="cat_in_tab"
            )
            selected_cat_id = cat_options[selected_cat_label]
        else:
            st.warning("No se encontraron categorías.")
            selected_cat_id = None

    with col_group:
        if selected_cat_id:
            groups = sde_repo.get_groups_by_category(selected_cat_id)
            if groups:
                group_options = {
                    f"{g.get('group_id', g.get('id', '?'))} — {g.get('name', g.get('example_name', 'Grupo'))} ({g['item_count']} items)": g.get('group_id', g.get('id'))
                    for g in groups
                }
                selected_group_label = st.selectbox(
                    "2. Elegí un Grupo", options=list(group_options.keys()), index=0, key="group_in_tab"
                )
                selected_group_id = group_options[selected_group_label]
            else:
                st.info("Esta categoría no tiene grupos.")
                selected_group_id = None
        else:
            selected_group_id = None

    if selected_group_id:
        st.markdown("**Items del grupo seleccionado (seleccioná los que querés analizar):**")
        items_in_group = sde_repo.get_types_in_group(selected_group_id, limit=40)

        if items_in_group:
            col_all1, col_all2, _ = st.columns([2, 2, 4])
            with col_all1:
                if st.button("✅ Seleccionar todos", key="select_all_group"):
                    for item in items_in_group:
                        st.session_state[f"bulk_group_{item['id']}"] = True
                    st.rerun()
            with col_all2:
                if st.button("❌ Deseleccionar todos", key="deselect_all_group"):
                    for item in items_in_group:
                        st.session_state[f"bulk_group_{item['id']}"] = False
                    st.rerun()

            tracked_id_set = set(tracked_ids)
            selected_ids = []
            for item in items_in_group:
                is_tracked = item['id'] in tracked_id_set
                col1, col2 = st.columns([6.5, 2])
                with col1:
                    label = f"{'✅ ' if is_tracked else ''}{item['name']} (ID: {item['id']})"
                    checked = st.checkbox(label, value=is_tracked, key=f"bulk_group_{item['id']}")
                    if checked:
                        selected_ids.append(item['id'])

            st.divider()

            if selected_ids:
                st.warning(f"⚠️ Vas a trackear **{len(selected_ids)}** items. El import de cada uno corre en background.")
                if st.button(f"🚀 Trackear los {len(selected_ids)} seleccionados", type="primary"):
                    # v2: cada llamada a track_item responde inmediato (202) --
                    # el import real corre en background del lado del server,
                    # así que este loop es rápido incluso para varias decenas
                    # de ítems (no bloquea esperando ESI como antes).
                    progress = st.progress(0, text="Trackeando...")
                    errors = []
                    for i, tid in enumerate(selected_ids):
                        try:
                            client.track_item(tid, reason="Bulk import from group explorer")
                        except ApiConnectionError as e:
                            errors.append((tid, str(e)))
                        progress.progress((i + 1) / len(selected_ids), text=f"{i + 1}/{len(selected_ids)}")
                    progress.empty()

                    ok_count = len(selected_ids) - len(errors)
                    st.success(f"✅ {ok_count} de {len(selected_ids)} items trackeados. Los imports están corriendo en background.")
                    if errors:
                        with st.expander(f"⚠️ {len(errors)} con error"):
                            for tid, err in errors:
                                st.caption(f"• ID {tid}: {err}")
                    st.rerun()
        else:
            st.info("No hay items en este grupo.")

    st.caption("💡 Tip: Usá la sección 'Tracked Items' para ver y gestionar todo lo que ya seleccionaste.")
