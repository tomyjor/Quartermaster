"""
Presentation/UI (NiceGUI): Tracked Items page.

v4 (rediseño visual completo): pedido explícito del usuario -- los
inputs/selects default de NiceGUI eran "cero accesibles" comparados
con Streamlit (líneas planas, bajo contraste). Rediseñado con
`theme.styled_search_input` / `theme.styled_select` (contenedor sólido,
foco ámbar, ícono de lupa) y tarjetas horizontales compactas
(`.jt-row-card`) en vez de las tarjetas grandes de antes. Se agregó
también el explorador de Categoría → Grupo (existía en Streamlit,
nunca se había portado -- necesitó 3 endpoints nuevos, ver
`routers/catalog.py`).

Reusa `presentation/api_client.py` -- tracking, búsqueda, catálogo y
sync pasan por la misma API que consume Streamlit.
"""

from typing import Optional

from presentation.api_client import ApiClient, ApiConnectionError
from presentation.ui.components import render_nav_header, render_explanation, recommendation_banner_html
from presentation.ui.theme import (
    score_pill_html, risk_badge_html, liquidity_pill_html,
    styled_search_input, styled_select,
)

CURRENT_PAGE_URL = "http://localhost:8502/tracked-items"


def register_tracked_items_page() -> None:
    """Registra la página `/tracked-items`. Llamar desde `main.py`."""
    from nicegui import ui
    from presentation.ui.theme import apply_theme
    from presentation.ui.auth_ui import restore_session, render_login_section

    @ui.page("/tracked-items")
    def tracked_items_page(session_token: Optional[str] = None) -> None:
        client = ApiClient()
        apply_theme()
        render_nav_header(active="tracked_items")
        restore_session(client, session_token)

        if not client.health_check():
            with ui.card().classes("jt-card"):
                ui.label("🔌 No se pudo conectar a la API").classes("jt-heading text-h6")
                ui.label(
                    "Corré en otra terminal: python -m uvicorn presentation.api.main:app "
                    "--reload --app-dir src -- y esperá a 'Application startup complete.'"
                )
            return

        with ui.row().classes("items-center justify-between w-full"):
            ui.label("📋 Gestión de Productos Trackeados").classes("jt-heading text-h4")
            render_login_section(client, current_page_url=CURRENT_PAGE_URL)

        if not client.is_authenticated or client.get_me() is None:
            with ui.card().classes("jt-card"):
                ui.label(
                    "🔐 Necesitás iniciar sesión con tu personaje de EVE para gestionar tu "
                    "watchlist personal. Usá el link de arriba."
                )
            return

        # --- Sección refrescable: lista de tracked + acciones ---
        @ui.refreshable
        def tracked_section() -> None:
            try:
                tracked = client.list_tracked()
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")
                return

            if not tracked:
                ui.label("Aún no tenés productos trackeados. Usá la búsqueda más abajo para empezar.").classes("jt-muted")
                return

            with ui.row().classes("items-center justify-between w-full"):
                ui.label(f"Tenés {len(tracked)} productos en tu watchlist.").classes("text-caption")

                def do_untrack_all() -> None:
                    deleted = client.untrack_all()
                    ui.notify(f"✅ Se eliminaron {deleted} productos.", type="positive")
                    tracked_section.refresh()

                ui.button("Eliminar todos", icon="delete_sweep", on_click=do_untrack_all) \
                    .props("outline color=negative").classes("jt-btn-compact")

            # Una sola llamada trae score/recomendación para todos los
            # que ya tienen order book completo -- mismo patrón que la
            # versión Streamlit (evita 1 conexión/análisis por ítem).
            try:
                page = client.get_opportunities(
                    scope="tracked", min_score=0, max_results=len(tracked), sort_by="score",
                )
                opportunities_by_id = {o["type_id"]: o for o in page["opportunities"]}
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")
                opportunities_by_id = {}

            for item in tracked:
                o = opportunities_by_id.get(item["type_id"])
                with ui.column().classes("jt-row-card w-full gap-1"):
                    with ui.row().classes("items-center justify-between w-full no-wrap"):
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            icon_url = f'https://images.evetech.net/types/{item["type_id"]}/icon?size=32'
                            ui.html(
                                f'<img src="{icon_url}" width="26" height="26" '
                                f'style="border-radius:4px;" onerror="this.style.display=\'none\'" />'
                            )
                            ui.label(item["name"]).classes("jt-heading")
                            ui.label(f"#{item['type_id']}").classes("jt-muted")
                            if o:
                                ui.html(score_pill_html(o["score"]))

                        def make_untrack(tid: int, name: str):
                            def _untrack() -> None:
                                client.untrack_item(tid)
                                ui.notify(f"✅ {name} quitado.", type="positive")
                                tracked_section.refresh()
                            return _untrack

                        ui.button(icon="close", on_click=make_untrack(item["type_id"], item["name"])) \
                            .props("flat round dense color=negative").classes("jt-btn-compact")

                    if o:
                        with ui.row().classes("items-center gap-3 no-wrap"):
                            ui.html(f'<span class="jt-mono">ROI {o["roi_percent"]:.1f}%</span>')
                            ui.html(risk_badge_html(o["risk"]["risk_level"]))
                            ui.html(liquidity_pill_html(o["liquidity"]["liquidity_score"]))
                        ui.html(recommendation_banner_html(o)).classes("w-full")
                        with ui.expansion("Ver análisis completo", icon="search").classes("w-full"):
                            ui.label(o["recommendation_reason"]).classes("jt-muted")
                            if o.get("explanation"):
                                render_explanation(o["explanation"])
                                ui.separator()
                            ui.label("Desglose numérico del score").classes("text-bold")
                            for comp in o["score_breakdown"]["components"].values():
                                ui.label(
                                    f"{comp['label']}: {comp['raw_value']:.1f} × {comp['weight']:.2f} "
                                    f"= {comp['contribution']:.2f}"
                                ).classes("jt-mono")
                    else:
                        ui.label("⏳ Sin datos de order book todavía.").classes("jt-muted")

        tracked_section()

        ui.separator().classes("q-my-md")

        # --- Búsqueda + track individual ---
        ui.label("🔍 Buscar y Agregar").classes("jt-heading text-h5")
        search_input = styled_search_input("Ej: Scourge, Shield, Tritanium...")

        @ui.refreshable
        def search_results_section() -> None:
            term = search_input.value
            if not term:
                return
            try:
                results = client.search_items(term.strip(), limit=12)
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")
                return

            try:
                tracked_ids = {item["type_id"] for item in client.list_tracked()}
            except ApiConnectionError:
                tracked_ids = set()

            if not results:
                ui.label("No se encontraron resultados.").classes("jt-muted")
                return

            for item in results:
                with ui.row().classes("jt-row-card items-center justify-between w-full no-wrap"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        icon_url = f'https://images.evetech.net/types/{item["id"]}/icon?size=28'
                        ui.html(
                            f'<img src="{icon_url}" width="24" height="24" '
                            f'style="border-radius:4px;" onerror="this.style.display=\'none\'" />'
                        )
                        ui.label(item["name"])
                        ui.label(f"#{item['id']}").classes("jt-muted")
                    if item["id"] in tracked_ids:
                        ui.label("✅ Ya trackeado").classes("text-positive")
                    else:
                        def make_track(tid: int, name: str):
                            def _track() -> None:
                                try:
                                    client.track_item(tid, reason=f"Búsqueda: {term}")
                                    ui.notify(
                                        f"✅ {name} trackeado. El import corre en background "
                                        "del lado del server -- puede tardar unos segundos.",
                                        type="positive",
                                    )
                                    tracked_section.refresh()
                                    search_results_section.refresh()
                                except ApiConnectionError as e:
                                    ui.notify(str(e), type="negative")
                            return _track

                        ui.button("Trackear", icon="add", on_click=make_track(item["id"], item["name"])) \
                            .props("outline color=amber").classes("jt-btn-compact")

        search_results_section()
        search_input.on_value_change(lambda: search_results_section.refresh())

        ui.separator().classes("q-my-md")

        # --- Explorador por Categoría → Grupo ---
        # Portado desde Streamlit -- existía como método de repositorio
        # desde hace tiempo, nunca se había expuesto vía HTTP (ver
        # routers/catalog.py, nuevo). Mismo criterio de diseño que la
        # búsqueda: selects "premium" en vez del combo plano default.
        ui.label("🗂️ Explorar por Categoría → Grupo").classes("jt-heading text-h5")

        try:
            categories = client.list_categories()
        except ApiConnectionError as e:
            categories = []
            ui.label(str(e)).classes("text-negative")

        state = {"category_id": None, "group_id": None}

        with ui.row().classes("w-full gap-4 no-wrap"):
            with ui.column().classes("flex-1"):
                cat_options = {
                    c["category_id"]: f'{c["name"]} ({c["item_count"]} items)' for c in categories
                }

                @ui.refreshable
                def group_select_section() -> None:
                    if state["category_id"] is None:
                        return
                    try:
                        groups = client.list_groups(state["category_id"])
                    except ApiConnectionError as e:
                        ui.label(str(e)).classes("text-negative")
                        return
                    if not groups:
                        ui.label("Esta categoría no tiene grupos.").classes("jt-muted")
                        return
                    group_options = {g["group_id"]: f'{g["name"]} ({g["item_count"]} items)' for g in groups}

                    def on_group_change(e) -> None:
                        state["group_id"] = e.value
                        items_section.refresh()

                    styled_select("2. Elegí un Grupo", group_options, on_change=on_group_change)

                def on_cat_change(e) -> None:
                    state["category_id"] = e.value
                    state["group_id"] = None
                    group_select_section.refresh()
                    items_section.refresh()

                styled_select("1. Elegí una Categoría", cat_options, on_change=on_cat_change)

            with ui.column().classes("flex-1"):
                group_select_section()

        @ui.refreshable
        def items_section() -> None:
            if state["group_id"] is None:
                return
            try:
                items_in_group = client.list_types_in_group(state["group_id"], limit=40)
            except ApiConnectionError as e:
                ui.label(str(e)).classes("text-negative")
                return
            if not items_in_group:
                ui.label("No hay ítems en este grupo.").classes("jt-muted")
                return

            try:
                tracked_ids = {item["type_id"] for item in client.list_tracked()}
            except ApiConnectionError:
                tracked_ids = set()

            ui.label("Ítems del grupo (elegí los que querés trackear):").classes("jt-muted")

            checkboxes = {}
            with ui.row().classes("gap-2"):
                def select_all() -> None:
                    for cb in checkboxes.values():
                        cb.value = True

                def deselect_all() -> None:
                    for cb in checkboxes.values():
                        cb.value = False

                ui.button("Seleccionar todos", icon="done_all", on_click=select_all) \
                    .props("outline color=amber dense").classes("jt-btn-compact")
                ui.button("Deseleccionar todos", icon="clear_all", on_click=deselect_all) \
                    .props("outline dense").classes("jt-btn-compact")

            for item in items_in_group:
                is_tracked = item["id"] in tracked_ids
                with ui.row().classes("jt-row-card items-center gap-2 w-full no-wrap"):
                    cb = ui.checkbox(value=is_tracked)
                    checkboxes[item["id"]] = cb
                    icon_url = f'https://images.evetech.net/types/{item["id"]}/icon?size=28'
                    ui.html(
                        f'<img src="{icon_url}" width="24" height="24" '
                        f'style="border-radius:4px;" onerror="this.style.display=\'none\'" />'
                    )
                    ui.label(item["name"])
                    ui.label(f"#{item['id']}").classes("jt-muted")
                    if is_tracked:
                        ui.label("✅").classes("text-positive")

            def do_bulk_track() -> None:
                selected = [tid for tid, cb in checkboxes.items() if cb.value]
                if not selected:
                    ui.notify("No seleccionaste ningún ítem.", type="warning")
                    return
                errors = []
                for tid in selected:
                    try:
                        client.track_item(tid, reason="Bulk import from group explorer")
                    except ApiConnectionError as e:
                        errors.append((tid, str(e)))
                ok_count = len(selected) - len(errors)
                ui.notify(
                    f"✅ {ok_count} de {len(selected)} ítems trackeados. Los imports corren en background.",
                    type="positive",
                )
                tracked_section.refresh()
                items_section.refresh()

            ui.button("Trackear seleccionados", icon="rocket_launch", on_click=do_bulk_track) \
                .props("color=amber").classes("jt-btn-compact")

        items_section()

        ui.separator().classes("q-my-md")

        # --- Smart Auto-Seed ---
        ui.label("🌍 Sincronizar todo Jita").classes("jt-heading text-h6")
        ui.label(
            "En vez de buscar y trackear ítems uno por uno, el Smart Auto-Seed sincroniza el "
            "order book completo de Jita de una sola vez."
        ).classes("jt-muted")

        @ui.refreshable
        def sync_status_section() -> None:
            try:
                sync_status = client.get_sync_status()
            except ApiConnectionError:
                sync_status = None

            if sync_status and sync_status["phase"] in ("orders", "history"):
                ui.label(f"⏳ Sync en curso: {sync_status.get('detail', sync_status['phase'])}").classes("jt-muted")
                total, done = sync_status.get("total"), sync_status.get("done")
                if total and done is not None and total > 0:
                    ui.linear_progress(value=min(done / total, 1.0)).props("color=amber")
                eta_human = sync_status.get("eta_human")
                if eta_human:
                    ui.label(f"⏱️ Tiempo estimado restante: {eta_human}").classes("jt-muted")
                else:
                    ui.label("⏱️ Todavía no hay suficiente progreso para estimar cuánto falta.").classes("jt-muted")
                ui.label(
                    "💡 Mientras el sync está en curso, es normal que Discovery muestre pocos "
                    "ítems -- no está colgado, solo está trabajando."
                ).classes("jt-muted")
                ui.button("Actualizar progreso", icon="refresh", on_click=sync_status_section.refresh) \
                    .props("flat dense").classes("jt-btn-compact")
            elif sync_status and sync_status["phase"] == "completed":
                ui.label(f"✅ Último sync: {sync_status.get('detail', '')}").classes("jt-muted")
            elif sync_status and sync_status["phase"] == "error":
                ui.label(f"⚠️ El último sync falló: {sync_status.get('error', '')}").classes("text-negative")

        sync_status_section()

        def do_trigger_seed() -> None:
            try:
                resp = client.trigger_seed()
                kind = "warning" if resp["status"] == "already_running" else "positive"
                ui.notify(resp["message"], type=kind)
                sync_status_section.refresh()
            except ApiConnectionError as e:
                ui.notify(str(e), type="negative")

        ui.button("Sincronizar todo Jita", icon="public", on_click=do_trigger_seed) \
            .props("color=amber").classes("jt-btn-compact")
