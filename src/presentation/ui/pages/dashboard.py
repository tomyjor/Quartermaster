"""
Presentation/UI (NiceGUI): Dashboard page.

v5 (feedback real, honesto: "sigue pareciendo muy feo comparado con
Streamlit"): tres problemas concretos señalados y arreglados acá:

1. Discovery NO tenía el fallback "mostrá lo mejor disponible aunque
   nada cruce el score mínimo" que Streamlit sí tiene -- se replica
   ahora exacto (mismo texto, misma lógica de min_score=0 + top 15).
2. El nav de arriba y el sidebar eran "texto tirado en un fondo, sin
   divisiones" -- nav rediseñado como barra con pestañas reales
   (`render_nav_header`, en components.py), sidebar como panel sólido
   real (`.jt-panel` puesto en un `ui.column()` DENTRO del drawer, no
   en el drawer mismo -- Quasar pisa cualquier estilo puesto directo
   en el q-drawer).
3. "El detalle me encanta, pero debería estar arriba, y la tabla abajo
   o en otra pestaña" -- ahora son pestañas (`ui.tabs`), con Tarjetas
   como default (la que gustó), Tabla como segunda opción -- mismo
   patrón que ya funciona bien en Streamlit (ahí es un radio, acá es
   el equivalente NiceGUI).

v3 (login): la página ya NO recibe un `ApiClient` compartido como
parámetro -- construye el suyo propio, por conexión.
"""

from typing import Optional

from presentation.api_client import ApiClient, ApiConnectionError
from presentation.ui.components import (
    render_opportunity_card, render_nav_header, render_market_summary_bar,
    opportunity_to_grid_row, OPPORTUNITIES_GRID_COLUMN_DEFS,
)

CURRENT_PAGE_URL = "http://localhost:8502/"


def register_dashboard_page() -> None:
    """Registra la página `/` en la app NiceGUI. Llamar desde `main.py`."""
    from nicegui import ui
    from presentation.ui.theme import apply_theme
    from presentation.ui.auth_ui import restore_session, render_login_section

    @ui.page("/")
    def dashboard(session_token: Optional[str] = None) -> None:
        client = ApiClient()
        apply_theme()
        render_nav_header(active="dashboard")
        restore_session(client, session_token)

        if not client.health_check():
            with ui.card().classes("jt-card"):
                ui.label("🔌 No se pudo conectar a la API").classes("jt-heading text-h6")
                ui.label(
                    "Corré en otra terminal: python -m uvicorn presentation.api.main:app "
                    "--reload --app-dir src -- y esperá a 'Application startup complete.'"
                )
            return

        with ui.row().classes("items-center justify-between w-full q-px-md"):
            ui.label("📡 Quartermaster — Dashboard").classes("jt-heading text-h4")
            render_login_section(client, current_page_url=CURRENT_PAGE_URL)

        tracked = []
        if client.is_authenticated:
            try:
                tracked = client.list_tracked()
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")

        scope = "tracked" if tracked else "discovery"
        with ui.column().classes("w-full q-px-md"):
            if tracked:
                ui.html(f'<div class="jt-status-banner">🎯 Analizando tus {len(tracked)} productos trackeados en Jita.</div>')
            elif client.is_authenticated:
                ui.html('<div class="jt-status-banner">📌 Modo Discovery — todavía no tenés nada trackeado.</div>')
            else:
                ui.html(
                    '<div class="jt-status-banner">📌 Modo Discovery — mejores oportunidades del '
                    'mercado Jita. Iniciá sesión para tu propia watchlist.</div>'
                )

        # --- Sidebar (filtros + watchlist) ---
        with ui.left_drawer():
            with ui.column().classes("jt-panel gap-2"):
                ui.label("⚙️ Filtros de Análisis").classes("jt-heading text-h6")
                ui.label("Score mínimo").classes("jt-muted")
                min_score_slider = ui.slider(min=40, max=95, value=55, step=1).props("label-always color=amber")
                ui.label("Máx. oportunidades a mostrar").classes("jt-muted")
                max_results_slider = ui.slider(min=5, max=50, value=20, step=1).props("label-always color=amber")
                exclude_caution_switch = ui.switch("Ocultar categorías de precaución", value=False).props("color=amber")

            with ui.column().classes("jt-panel gap-1"):
                ui.label("📋 Watchlist actual").classes("jt-heading text-h6")
                if tracked:
                    for item in tracked[:8]:
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            icon_url = f'https://images.evetech.net/types/{item["type_id"]}/icon?size=24'
                            ui.html(
                                f'<img src="{icon_url}" width="20" height="20" '
                                f'style="border-radius:3px;" onerror="this.style.display=\'none\'" />'
                            )
                            ui.label(item["name"]).classes("jt-mono").style("font-size: 0.85rem;")
                    if len(tracked) > 8:
                        ui.label(f"... y {len(tracked) - 8} más").classes("jt-muted")
                else:
                    ui.label("Sin ítems trackeados todavía.").classes("jt-muted")

        # --- Sección de oportunidades (refrescable sin recargar toda la página) ---
        @ui.refreshable
        def opportunities_section() -> None:
            try:
                page = client.get_opportunities(
                    scope=scope, min_score=min_score_slider.value, max_results=max_results_slider.value,
                    sort_by="score", sort_desc=True, exclude_caution=exclude_caution_switch.value,
                )
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")
                return

            # Fallback real (portado de Streamlit, antes faltaba acá):
            # si NADA cruza el score mínimo pero hay evidencia real para
            # al menos un ítem, mostramos lo mejor disponible igual en
            # vez de dejar la página vacía con solo una advertencia.
            if page["opportunities"]:
                opportunities_to_show = page["opportunities"]
                label = "Mejores Oportunidades en Jita" if scope == "discovery" else "Oportunidades Detectadas"
                ui.label(
                    f"📊 {label} ({len(opportunities_to_show)} de {page['total_with_data']} con datos)"
                ).classes("jt-heading text-h6")
            elif page["total_with_data"] > 0:
                try:
                    fallback_page = client.get_opportunities(
                        scope=scope, min_score=0, max_results=15,
                        sort_by="score", sort_desc=True, exclude_caution=exclude_caution_switch.value,
                    )
                except ApiConnectionError as e:
                    ui.label(str(e)).classes("text-negative")
                    return
                opportunities_to_show = fallback_page["opportunities"]
                ui.html(
                    f'<div class="jt-status-banner warning">⚠️ Ninguno de los {page["total_with_data"]} '
                    f'ítems con datos reales superó tu score mínimo ({min_score_slider.value:.0f}). '
                    f'Mostrando los {len(opportunities_to_show)} mejores igual, para que siempre tengas '
                    f'algo que mirar — pero ojo, esto no es una recomendación de compra, es "lo menos '
                    f'malo disponible ahora". Bajá el slider de score mínimo si querés ver más.</div>'
                )
                ui.label(
                    f"📊 Mejores {len(opportunities_to_show)} disponibles "
                    f"(todos por debajo de {min_score_slider.value:.0f})"
                ).classes("jt-heading text-h6")
            else:
                opportunities_to_show = []
                ui.label("📊 Oportunidades Detectadas (0 con datos)").classes("jt-heading text-h6")

            if not opportunities_to_show:
                ui.html(
                    '<div class="jt-status-banner">Ninguno de los productos evaluados tiene snapshots '
                    'completos de order book todavía. Si nunca corriste un Smart Auto-Seed, hacelo desde '
                    'Tracked Items ("Sincronizar todo Jita").</div>'
                )
                return

            render_market_summary_bar(opportunities_to_show, page["total_with_data"])
            ui.separator().classes("q-my-sm")

            # Tarjetas primero (pestaña default) -- "el detalle me
            # encanta, debería estar arriba"; la tabla queda disponible
            # en su propia pestaña, no empujando el contenido bueno
            # hacia abajo.
            with ui.tabs().classes("w-full") as tabs:
                tab_cards = ui.tab("🗂️ Tarjetas (detalle + desglose)")
                tab_table = ui.tab("📊 Tabla (ordenable por columna)")
            with ui.tab_panels(tabs, value=tab_cards).classes("w-full").style("background: transparent;"):
                with ui.tab_panel(tab_cards):
                    for i, o in enumerate(opportunities_to_show, start=1):
                        render_opportunity_card(o, rank=i)
                with ui.tab_panel(tab_table):
                    row_data = [opportunity_to_grid_row(o) for o in opportunities_to_show]
                    ui.aggrid({
                        "columnDefs": OPPORTUNITIES_GRID_COLUMN_DEFS, "rowData": row_data,
                    }).classes("ag-theme-alpine-dark w-full").style("height: 400px")
                    ui.label("💡 Click en cualquier header para ordenar (nativo de AG-Grid).").classes("jt-muted")

        with ui.column().classes("w-full q-px-md"):
            opportunities_section()

        # Cualquier cambio en un filtro refresca SOLO esta sección, no
        # toda la página -- equivalente NiceGUI del rerun de Streamlit,
        # pero acotado (más eficiente para listas grandes).
        min_score_slider.on_value_change(lambda: opportunities_section.refresh())
        max_results_slider.on_value_change(lambda: opportunities_section.refresh())
        exclude_caution_switch.on_value_change(lambda: opportunities_section.refresh())
