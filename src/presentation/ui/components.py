"""
Presentation/UI (NiceGUI): components

Renderizado compartido entre las páginas de NiceGUI (Dashboard, Tracked
Items) -- mismo espíritu que `streamlit_app/components/opportunity_table.py`:
un solo lugar que traduce un dict de `OpportunitySchema` a UI, para que
ambas páginas se vean consistentes y no dupliquen la lógica.

⚠️ NO EJECUTADO -- requiere `nicegui`. Ver nota en `pages/dashboard.py`.
"""

from typing import Any, Dict
import re

from presentation.ui.theme import COLOR_SUCCESS, COLOR_WARNING, COLOR_INFO

# Mismo mapeo semántico que `_BADGE_STYLE` en
# `streamlit_app/components/opportunity_table.py`.
BADGE_ICON = {
    "buy": ("✅", COLOR_SUCCESS),
    "caution_low_liquidity": ("⚠️", COLOR_WARNING),
    "caution_no_volume_data": ("📉", COLOR_WARNING),
    "caution_high_risk": ("🔥", COLOR_WARNING),
    "caution_thin_order_book": ("🎲", COLOR_WARNING),
    "caution_implausible_spread": ("↕️", COLOR_WARNING),
    "neutral": ("➖", COLOR_INFO),
}

BADGE_LABELS = {
    "buy": "Comprar",
    "caution_low_liquidity": "Precaución · Liquidez baja",
    "caution_no_volume_data": "Precaución · Sin volumen",
    "caution_high_risk": "Precaución · Riesgo alto",
    "caution_thin_order_book": "Precaución · Book fino",
    "caution_implausible_spread": "Precaución · Spread implausible",
    "neutral": "Neutral",
}


def _trim_summary_for_banner(summary: str) -> str:
    """Igual a `streamlit_app/components/opportunity_table._trim_summary_for_banner`."""
    summary = re.sub(r"^El score final \([\d.]+\) es elevado principalmente por: ", "📈 ", summary)
    summary = re.sub(r"^El score final \([\d.]+\) se ve limitado principalmente por: ", "📉 ", summary)
    summary = re.sub(
        r"^El score final \([\d.]+\) refleja un balance.*",
        "⚖️ Sin señal dominante en ningún sentido -- mirá el desglose para más detalle.",
        summary,
    )
    return summary


def recommendation_banner_html(o: Dict[str, Any]) -> str:
    """
    Banner de recomendación -- PROMINENTE y ESPECÍFICO por ítem. Mismo
    criterio que la versión Streamlit: "Neutral" solo, repetido en
    varios ítems, no diferencia nada -- el texto ahora es el resumen
    específico de `OpportunityExplainer` (con los números reales de
    ESTE ítem), no la categoría genérica sola.

    v2 (feedback real): "el insight me gustaría que esté como
    protagonista en el cubo de información" -- se agrega el primer
    insight de `explanation.insights` como segunda línea del banner.
    """
    icon, color = BADGE_ICON.get(o.get("recommendation"), ("➖", COLOR_INFO))
    label = BADGE_LABELS.get(o.get("recommendation"), "Neutral")
    bg = f"{color}20"

    summary = (o.get("explanation") or {}).get("summary", "").strip()
    insights = (o.get("explanation") or {}).get("insights", [])
    if summary:
        body = f"<strong>{icon} {label}:</strong> {_trim_summary_for_banner(summary)}"
    else:
        body = f"{icon} {label}"

    insight_line = ""
    if insights:
        insight_line = f'<div style="margin-top:0.35rem; font-size:0.88rem; opacity:0.9;">💡 {insights[0]}</div>'

    return (
        f'<div style="display:flex; flex-direction:column; '
        f'background:{bg}; border-left:4px solid {color}; border-radius:8px; '
        f'padding:0.55rem 0.9rem; margin:0.5rem 0; font-size:0.95rem; '
        f'line-height:1.4; color:{color};">{body}{insight_line}</div>'
    )


def compact_badge_html(o: Dict[str, Any]) -> str:
    """Versión chica (sin bloque de fondo) -- para contextos densos. Ver `recommendation_banner_html` para la tarjeta principal."""
    icon, color = BADGE_ICON.get(o.get("recommendation"), ("➖", COLOR_INFO))
    label = BADGE_LABELS.get(o.get("recommendation"), "Neutral")
    return f'<span style="color:{color}; font-weight:600; font-size:0.85rem;">{icon} {label}</span>'


def opportunity_to_grid_row(o: Dict[str, Any]) -> Dict[str, Any]:
    """Aplana un dict de OpportunitySchema a una fila apta para `ui.aggrid`."""
    icon, _ = BADGE_ICON.get(o.get("recommendation"), ("➖", COLOR_INFO))
    label = BADGE_LABELS.get(o.get("recommendation"), "Neutral")
    return {
        "type_name": o["type_name"],
        "type_id": o["type_id"],
        # Con ícono, no la categoría plana ("buy") -- antes se perdía
        # entre el resto de las columnas numéricas. Feedback real: "la
        # recomendación tiene que ser protagonista".
        "recommendation": f"{icon} {label}",
        "score": round(o["score"], 1),
        "roi_percent": round(o["roi_percent"], 1),
        "liquidity_score": round(o["liquidity"]["liquidity_score"], 1),
        "risk_level": o["risk"]["risk_level"],
        "exit_time": o.get("estimated_exit_human") or "-",
    }


# ⚠️ VERIFICAR: convención de AG-Grid (JS: `headerName`, no `label`).
OPPORTUNITIES_GRID_COLUMN_DEFS = [
    {"headerName": "Item", "field": "type_name", "sortable": True, "filter": True},
    {"headerName": "Recomendación", "field": "recommendation", "sortable": True},
    {"headerName": "Score", "field": "score", "sortable": True},
    {"headerName": "ROI %", "field": "roi_percent", "sortable": True},
    {"headerName": "Liquidez", "field": "liquidity_score", "sortable": True},
    {"headerName": "Riesgo", "field": "risk_level", "sortable": True},
    {"headerName": "Tiempo venta (ref. 100u)", "field": "exit_time", "sortable": True},
]


def render_explanation(explanation: Dict[str, Any]) -> None:
    """
    Pinta la explicación data-driven de
    `domain.services.opportunity_explainer.OpportunityExplainer` --
    mismo contenido que la versión de Streamlit
    (`streamlit_app/components/opportunity_table.py`), para que ambas
    UIs muestren exactamente la misma profundidad de análisis.
    """
    from nicegui import ui

    if not explanation:
        return

    ui.label(explanation.get("summary", "")).classes("jt-heading")

    strengths = explanation.get("strengths", [])
    weaknesses = explanation.get("weaknesses", [])
    neutral = explanation.get("neutral_factors", [])

    if strengths:
        ui.label("✅ Fortalezas").classes("text-bold")
        for s in strengths:
            ui.label(f"• {s}").classes("text-caption")
    if weaknesses:
        ui.label("⚠️ Debilidades").classes("text-bold")
        for w in weaknesses:
            ui.label(f"• {w}").classes("text-caption")
    if neutral:
        with ui.expansion("➖ Factores neutros"):
            for n in neutral:
                ui.label(f"• {n}").classes("text-caption")

    liquidity_text = explanation.get("liquidity_interpretation")
    if liquidity_text:
        ui.label("💧 Interpretación de liquidez").classes("text-bold")
        ui.label(liquidity_text).classes("text-caption")

    risk_text = explanation.get("risk_interpretation")
    if risk_text:
        ui.label("⚠️ Interpretación de riesgo").classes("text-bold")
        ui.label(risk_text).classes("text-caption")

    insights = explanation.get("insights", [])
    if insights:
        ui.label("💡 Insights").classes("text-bold")
        for i in insights:
            ui.label(f"💡 {i}").classes("text-caption")


def render_opportunity_card(o: Dict[str, Any], rank: int = None) -> None:
    """
    Tarjeta para una Opportunity.

    v3 (rediseño real, no solo color): igual que la versión Streamlit --
    por defecto solo se ve nombre, score, 3 métricas compactas, y un
    badge corto (ícono + categoría). Precios, conteo de órdenes, tiempo
    de venta, confianza, y la razón completa de la recomendación pasan
    al panel expandible. `rank` (opcional) refuerza visualmente la
    posición en el ranking.
    """
    from nicegui import ui
    from presentation.ui.theme import score_pill_html, risk_badge_html, liquidity_pill_html

    with ui.card().classes("jt-card w-full").style("padding: 16px 20px;"):
        with ui.row().classes("items-start justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                # Ícono real del ítem -- CDN público de CCP, sin auth.
                # NiceGUI's ui.image no tiene onerror nativo fácil, así
                # que va como <img> crudo vía ui.html -- mismo criterio
                # que Streamlit, oculto solo si el type no tiene ícono.
                icon_url = f'https://images.evetech.net/types/{o["type_id"]}/icon?size=32'
                ui.html(
                    f'<img src="{icon_url}" width="28" height="28" '
                    f'style="border-radius:4px;" onerror="this.style.display=\'none\'" />'
                )
                with ui.column().classes("gap-0"):
                    name_prefix = f"#{rank} · " if rank else ""
                    ui.label(f"{name_prefix}{o['type_name']}").classes("jt-heading text-h6")
                    ui.label(f"ID: {o['type_id']}").classes("jt-muted")
            with ui.column().classes("items-end gap-0"):
                ui.label("SCORE").classes("jt-muted")
                ui.html(score_pill_html(o["score"]))

        # Recomendación PRIMERO, antes de las métricas -- feedback real:
        # "tiene que ser protagonista, no algo que solo se ve en el
        # detalle". Antes era texto chico al final de la tarjeta.
        ui.html(recommendation_banner_html(o)).classes("w-full")

        with ui.row().classes("gap-8 items-end w-full").style("margin-top: 6px;"):
            with ui.column().classes("gap-0"):
                ui.label("ROI").classes("jt-muted")
                ui.label(f"{o['roi_percent']:.1f}%").classes("jt-mono").style("font-size: 1.15rem;")
            with ui.column().classes("gap-0"):
                ui.label("RIESGO").classes("jt-muted")
                ui.html(risk_badge_html(o["risk"]["risk_level"]))
            with ui.column().classes("gap-0"):
                ui.label("LIQUIDEZ").classes("jt-muted")
                # Pill compacto, mismo peso visual que Riesgo -- antes
                # era una barra larga y fina que quedaba fuera de lugar
                # comparada con el resto ("liquidity_bar_html", feedback real).
                ui.html(liquidity_pill_html(o["liquidity"]["liquidity_score"]))

        with ui.expansion("🔍 Ver análisis completo"):
            ui.label(o["recommendation_reason"]).classes("jt-muted")
            ui.label(
                f"💰 Buy: {o['buy_price']:.2f} ISK   ·   Sell: {o['sell_price']:.2f} ISK   ·   "
                f"📋 {o['sell_order_count']} venta / {o['buy_order_count']} compra   ·   "
                f"Confianza: {o.get('confidence', 0):.0f}%"
            ).classes("jt-muted")
            exit_human = o.get("estimated_exit_human")
            if exit_human:
                ref_size = o.get("estimated_exit_position_size", 100)
                ui.label(
                    f"⏱️ Tiempo estimado de venta ({ref_size:,.0f}u de referencia): {exit_human}"
                ).classes("jt-muted")
            ui.separator()
            if o.get("explanation"):
                render_explanation(o["explanation"])
                ui.separator()
            ui.label("📐 Desglose numérico del score").classes("text-bold")
            for comp in o["score_breakdown"]["components"].values():
                ui.label(
                    f"{comp['label']}: {comp['raw_value']:.1f} × {comp['weight']:.2f} "
                    f"= {comp['contribution']:.2f}"
                ).classes("jt-mono")
            ui.label(
                f"Score final = {o['score_breakdown']['final_score']} "
                f"(suma de contribuciones: {o['score_breakdown']['sum_of_contributions']})"
            ).classes("text-caption")


def render_market_summary_bar(opportunities, total_with_data: int) -> None:
    """
    Barra de resumen agregado -- mismo criterio que
    `streamlit_app/components/opportunity_table.render_market_summary_bar`.
    No existía antes del rediseño; da un panorama de un vistazo antes de
    bajar a la lista ítem por ítem.
    """
    from nicegui import ui

    if not opportunities:
        return
    scores = [o["score"] for o in opportunities]
    avg_score = sum(scores) / len(scores)
    top_score = max(scores)
    buy_count = sum(1 for o in opportunities if o.get("recommendation") == "buy")

    with ui.row().classes("gap-8 w-full"):
        for label, value in [
            ("Mostrando", str(len(opportunities))),
            ("Score promedio", f"{avg_score:.1f}"),
            ("Mejor score", f"{top_score:.1f}"),
            ("Recomendadas", str(buy_count)),
        ]:
            with ui.column().classes("gap-0"):
                ui.label(label.upper()).classes("jt-muted")
                ui.label(value).classes("jt-mono").style("font-size: 1.3rem;")
    ui.label(f"(de {total_with_data} ítems con datos suficientes)").classes("text-caption")


def render_nav_header(active: str) -> None:
    """
    Barra de navegación -- NiceGUI no arma un menú de páginas solo como
    Streamlit (que lo hace automático a partir de `pages/`), así que se
    arma a mano acá. `active` es "dashboard" o "tracked_items".

    v2 (feedback real): la versión anterior era texto plano con un
    `ui.separator()` abajo -- "sin divisiones, sin nada, simplemente
    texto tirado en un fondo". Ahora es una barra real (`.jt-nav-bar`)
    con fondo propio, borde inferior, y la pestaña activa marcada con
    una línea inferior de color -- mismo lenguaje visual que pestañas
    reales, no un link que cambia de color nomás.
    """
    from nicegui import ui

    with ui.row().classes("jt-nav-bar items-center gap-1 w-full no-wrap"):
        ui.link("📡 Dashboard", "/").classes(
            "jt-nav-tab" + (" jt-nav-tab-active" if active == "dashboard" else "")
        )
        ui.link("📋 Tracked Items", "/tracked-items").classes(
            "jt-nav-tab" + (" jt-nav-tab-active" if active == "tracked_items" else "")
        )
