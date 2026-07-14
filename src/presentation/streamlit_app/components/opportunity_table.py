"""
Componente reutilizable de presentación para mostrar Opportunities.

v2 (migración a API): antes tomaba objetos de dominio
(`domain.value_objects.opportunity.Opportunity` / `AnalysisResult`)
directo. Ahora Streamlit es un cliente HTTP de la API (ver
`api_client.py`), así que este módulo trabaja sobre los dicts crudos que
devuelve `ApiClient.get_opportunities()` / `.get_opportunity()` --
mismo shape que `OpportunitySchema` en `presentation/api/schemas.py`.
Streamlit ya no importa nada de `domain.*` ni `infrastructure.*`.

Sigue centralizando acá el renderizado del badge de recomendación y del
desglose del score para que Dashboard (`app.py`) y Tracked Items
(`pages/02_tracked_items.py`) muestren exactamente lo mismo.

Importante: este módulo solo PINTA datos que la API ya calculó
(`recommendation`, `score_breakdown`, etc.). Nunca decide umbrales ni
reglas de negocio -- esas viven en `OpportunityEngine`, del otro lado
del HTTP.
"""

from typing import List, Dict, Any
import re

import streamlit as st
from presentation.streamlit_app.theme import score_pill_html, risk_badge_html, liquidity_bar_html, liquidity_pill_html

# Cómo se pinta cada valor de `recommendation` (string plano, ya no un
# RecommendationLevel de dominio -- ver nota de migración arriba). Único
# lugar de la UI que traduce la categoría a colores/iconos -- el TEXTO
# de la razón siempre viene de `recommendation_reason`, calculado por
# el motor del lado del server, nunca hardcodeado acá.
_BADGE_STYLE = {
    "buy": ("success", "✅"),
    "caution_low_liquidity": ("warning", "⚠️"),
    "caution_no_volume_data": ("warning", "📉"),
    "caution_high_risk": ("warning", "🔥"),
    "caution_thin_order_book": ("warning", "🎲"),
    "caution_implausible_spread": ("warning", "↕️"),
    "neutral": ("info", "➖"),
}


_BADGE_LABELS = {
    "buy": "Comprar",
    "caution_low_liquidity": "Precaución · Liquidez baja",
    "caution_no_volume_data": "Precaución · Sin volumen",
    "caution_high_risk": "Precaución · Riesgo alto",
    "caution_thin_order_book": "Precaución · Book fino",
    "caution_implausible_spread": "Precaución · Spread implausible",
    "neutral": "Neutral",
}


def render_recommendation_badge(o: Dict[str, Any]) -> None:
    """Pinta el badge de recomendación leyendo SOLO lo que ya calculó la API. Versión completa (con la razón entera) -- para el panel expandido."""
    kind, icon = _BADGE_STYLE.get(o.get("recommendation"), ("info", "➖"))
    message = f"{icon} **{o.get('recommendation_reason', '')}**"
    if kind == "success":
        st.success(message, icon=icon)
    elif kind == "warning":
        st.warning(message, icon=icon)
    else:
        st.info(message, icon=icon)


def _trim_summary_for_banner(summary: str) -> str:
    """
    El resumen completo de `OpportunityExplainer` empieza con "El score
    final (X.X) es/está..." -- redundante en la tarjeta, donde el score
    ya se ve en el pill de al lado. Recorta ese prefijo para la vista
    compacta; el texto completo (con el número) sigue disponible en el
    panel expandido (`render_explanation`), donde no hay ese problema.
    """
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
    Banner de recomendación -- PROMINENTE y ESPECÍFICO por ítem, no un
    genérico repetido.

    v5 (feedback real): "Neutral" solo, repetido en 15 ítems distintos,
    no diferencia nada -- "es difícil de entender, tiene que dar la
    info clave, no tirar los datos crudos". La categoría (Comprar /
    Precaución / Neutral) sigue siendo el color -- pero el TEXTO ahora
    es el resumen específico de `OpportunityExplainer`
    (`explanation.summary`, recortado del número de score redundante,
    ver `_trim_summary_for_banner`), que ya usa los números reales de
    ESTE ítem puntual -- antes quedaba escondido en el panel expandido.
    Si no hay explicación disponible, cae a la categoría sola.

    v6 (feedback real): "el insight me gustaría que esté como
    protagonista en el cubo de información" -- se agrega el primer
    insight de `explanation.insights` como segunda línea del mismo
    banner (antes solo vivía en el panel expandido, vía
    `render_explanation`). El resto de los insights, si hay más de uno,
    sigue en el panel completo -- acá solo el más relevante.
    """
    from presentation.streamlit_app.theme import COLOR_SUCCESS, COLOR_WARNING, COLOR_INFO
    kind, icon = _BADGE_STYLE.get(o.get("recommendation"), ("info", "➖"))
    label = _BADGE_LABELS.get(o.get("recommendation"), "Neutral")
    color = {"success": COLOR_SUCCESS, "warning": COLOR_WARNING, "info": COLOR_INFO}[kind]
    bg = f"{color}20"

    summary = (o.get("explanation") or {}).get("summary", "").strip()
    insights = (o.get("explanation") or {}).get("insights", [])
    if summary:
        body = f"<strong>{icon} {label}:</strong> {_trim_summary_for_banner(summary)}"
    else:
        body = f"{icon} {label}"

    # El insight (si hay) va como SEGUNDA línea del mismo banner -- no
    # solo el resumen corto. Feedback real: "el insight me gustaría
    # que esté como protagonista en el cubo de información", en vez de
    # quedar escondido en el panel expandido.
    insight_line = ""
    if insights:
        insight_line = f'<div style="margin-top:0.35rem; font-size:0.88rem; opacity:0.9;">💡 {insights[0]}</div>'

    return (
        f'<div style="display:flex; flex-direction:column; '
        f'background:{bg}; border-left:4px solid {color}; border-radius:8px; '
        f'padding:0.55rem 0.9rem; margin:0.6rem 0; font-size:0.95rem; '
        f'line-height:1.4; color:{color};">{body}{insight_line}</div>'
    )


def compact_badge_html(o: Dict[str, Any]) -> str:
    """
    Versión chica del badge (solo texto, sin bloque de fondo) -- para
    contextos densos donde el banner completo no entra (ej. la lista
    de checkboxes de Tracked Items). Para la tarjeta principal usar
    `recommendation_banner_html`, no esta.
    """
    from presentation.streamlit_app.theme import COLOR_SUCCESS, COLOR_WARNING, COLOR_INFO
    kind, icon = _BADGE_STYLE.get(o.get("recommendation"), ("info", "➖"))
    label = _BADGE_LABELS.get(o.get("recommendation"), "Neutral")
    color = {"success": COLOR_SUCCESS, "warning": COLOR_WARNING, "info": COLOR_INFO}[kind]
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.3rem; '
        f'font-size:0.85rem; font-weight:600; color:{color};">{icon} {label}</span>'
    )


def render_market_summary_bar(opportunities: List[Dict[str, Any]], total_with_data: int) -> None:
    """
    Barra de resumen agregado -- no existía antes del rediseño. Da un
    panorama de un vistazo (cuántas, score promedio, cuántas son "buy")
    antes de bajar a la lista ítem por ítem -- el tipo de elemento que
    distingue un dashboard profesional de una lista cruda de resultados.
    """
    if not opportunities:
        return
    scores = [o["score"] for o in opportunities]
    avg_score = sum(scores) / len(scores)
    top_score = max(scores)
    buy_count = sum(1 for o in opportunities if o.get("recommendation") == "buy")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mostrando", f"{len(opportunities)}", help=f"de {total_with_data} con datos suficientes")
    c2.metric("Score promedio", f"{avg_score:.1f}")
    c3.metric("Mejor score", f"{top_score:.1f}")
    c4.metric("Recomendadas (buy)", f"{buy_count}")


def render_score_breakdown(score_breakdown: Dict[str, Any]) -> None:
    """
    Renderiza la tabla de desglose del score de forma genérica a partir
    de `score_breakdown["components"]`, sin hardcodear filas -- si
    OpportunityEngine agrega o quita un componente, la tabla se
    actualiza sola. Cada fila muestra raw_value * weight = contribution
    de forma literal (ver `OpportunityEngine._build_score_breakdown`,
    del lado del server).
    """
    components = score_breakdown.get("components", {})
    if not components:
        st.caption("Sin desglose disponible para esta oportunidad.")
        return

    rows = ["| Componente | Valor (0-100) | Peso | Contribución |", "|---|---|---|---|"]
    for comp in components.values():
        rows.append(
            f"| {comp['label']} | {comp['raw_value']:.1f} | {comp['weight']:.2f} | "
            f"{comp['contribution']:.2f} |"
        )
    st.markdown("\n".join(rows))

    final_score = score_breakdown.get("final_score", 0)
    checksum = score_breakdown.get("sum_of_contributions", final_score)
    st.markdown(f"**Score Final = {final_score}** (`{score_breakdown.get('formula_version', 'v1')}`)")
    st.caption(
        f"✔️ Chequeo de transparencia: la suma de todas las contribuciones da {checksum} "
        f"— debe coincidir con el score final salvo redondeo. Si no coincide, hay un bug."
    )

    if not score_breakdown.get("has_volume_evidence", True):
        st.caption(
            "📉 Este ítem no tiene ningún día de volumen histórico importado todavía "
            "(`market_history` vacía para este type_id). Su componente de liquidez es 0 "
            "por diseño hasta que se importe historial real — no es una liquidez confirmada "
            "en 0, es una liquidez *desconocida* tratada de forma conservadora."
        )


def render_explanation(explanation: Dict[str, Any]) -> None:
    """
    Pinta la explicación data-driven generada por
    `domain.services.opportunity_explainer.OpportunityExplainer` --
    resumen, fortalezas, debilidades, interpretación de liquidez y
    riesgo, e insights accionables. Todo el TEXTO ya viene armado del
    lado del dominio con los números reales de esta oportunidad
    puntual; acá solo se pinta, no se decide nada.
    """
    if not explanation:
        return

    st.markdown(f"**{explanation.get('summary', '')}**")

    strengths = explanation.get("strengths", [])
    weaknesses = explanation.get("weaknesses", [])
    neutral = explanation.get("neutral_factors", [])

    if strengths:
        st.markdown("**✅ Fortalezas**")
        for s in strengths:
            st.markdown(f"- {s}")
    if weaknesses:
        st.markdown("**⚠️ Debilidades**")
        for w in weaknesses:
            st.markdown(f"- {w}")
    if neutral:
        with st.expander("➖ Factores neutros"):
            for n in neutral:
                st.markdown(f"- {n}")

    liquidity_text = explanation.get("liquidity_interpretation")
    if liquidity_text:
        st.markdown("**💧 Interpretación de liquidez**")
        st.caption(liquidity_text)

    risk_text = explanation.get("risk_interpretation")
    if risk_text:
        st.markdown("**⚠️ Interpretación de riesgo**")
        st.caption(risk_text)

    insights = explanation.get("insights", [])
    if insights:
        st.markdown("**💡 Insights**")
        for i in insights:
            st.info(i, icon="💡")


def render_opportunity_card(o: Dict[str, Any], rank: int = None) -> None:
    """
    Renderiza una Opportunity dentro de un `st.container(border=True)`.
    Es el bloque de UI que usan tanto el Dashboard como Tracked Items
    para mostrar cada ítem de forma consistente.

    v3 (rediseño real, no solo color): la jerarquía por defecto ahora es
    genuinamente mínima -- nombre, score, 3 métricas compactas, y un
    badge CORTO (ícono + categoría, no la oración completa). Todo lo
    demás (razón completa de la recomendación, precios buy/sell,
    conteo de órdenes, tiempo de venta, explicación completa, desglose
    numérico) vive en el panel expandible -- esto es lo que pedía el
    punto 7 del pedido de rediseño ("visible inicialmente: score,
    indicadores principales, resumen corto") y que la v2 (solo colores)
    no había cumplido en realidad, seguía mostrando todo siempre.

    `rank`: posición en el ranking (1, 2, 3...) -- opcional, se muestra
    como número de orden si se pasa. El ranking es el valor central de
    la herramienta y antes no se reforzaba visualmente en ningún lado.

    `o` es un dict con el shape de `OpportunitySchema` (ver
    `presentation/api/schemas.py`), tal como lo devuelve
    `ApiClient.get_opportunities()`.
    """
    with st.container(border=True):
        header_l, header_r = st.columns([4, 1.3])
        with header_l:
            rank_prefix = f'<span class="jt-mono" style="color:var(--jt-text-muted); margin-right:0.4rem;">#{rank}</span>' if rank else ""
            # Ícono real del ítem -- CDN público de CCP, sin auth. Con
            # onerror que oculta la imagen sola si el type no tiene
            # variante "icon" (pasa con SKINs, algunos blueprints) --
            # ver docs.esi.evetech.net/docs/image_server.html.
            icon_url = f'https://images.evetech.net/types/{o["type_id"]}/icon?size=32'
            st.markdown(
                f'<div style="display:flex; align-items:center; gap:0.5rem;">'
                f'<img src="{icon_url}" width="28" height="28" style="border-radius:4px; flex-shrink:0;" '
                f'onerror="this.style.display=\'none\'" />'
                f'<span>{rank_prefix}<strong>{o["type_name"]}</strong></span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<span class="jt-meta-row"><span class="jt-mono">ID: {o["type_id"]}</span></span>',
                unsafe_allow_html=True,
            )
        with header_r:
            st.markdown(
                f'<div style="text-align:right;">'
                f'<div style="font-size:0.7rem; color:var(--jt-text-muted); '
                f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px;">Score</div>'
                f'{score_pill_html(o["score"])}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # La recomendación va ACÁ, entre el header y las métricas -- es
        # lo segundo que se lee después del nombre/score, no una nota al
        # pie. Feedback real: "la recomendación tiene que ser
        # protagonista, no algo que solo se ve en el detalle".
        st.markdown(recommendation_banner_html(o), unsafe_allow_html=True)

        m1, m2, m3 = st.columns([1, 1, 1])
        with m1:
            st.markdown('<div style="font-size:0.72rem; color:var(--jt-text-muted); text-transform:uppercase;">ROI</div>', unsafe_allow_html=True)
            st.markdown(f'<span class="jt-mono" style="font-size:1.25rem; font-weight:700;">{o["roi_percent"]:.1f}%</span>', unsafe_allow_html=True)
        with m2:
            st.markdown('<div style="font-size:0.72rem; color:var(--jt-text-muted); text-transform:uppercase;">Riesgo</div>', unsafe_allow_html=True)
            st.markdown(risk_badge_html(o["risk"]["risk_level"]), unsafe_allow_html=True)
        with m3:
            st.markdown('<div style="font-size:0.72rem; color:var(--jt-text-muted); text-transform:uppercase;">Liquidez</div>', unsafe_allow_html=True)
            st.markdown(liquidity_pill_html(o["liquidity"]["liquidity_score"]), unsafe_allow_html=True)

        if o.get("explanation") or o.get("score_breakdown"):
            with st.expander("🔍 Ver análisis completo"):
                st.caption(o.get("recommendation_reason", ""))
                st.markdown(
                    f'<div class="jt-meta-row">💰 Buy: <span class="jt-mono">{o["buy_price"]:.2f} ISK</span>'
                    f'&nbsp;&nbsp;·&nbsp;&nbsp;Sell: <span class="jt-mono">{o["sell_price"]:.2f} ISK</span>'
                    f'&nbsp;&nbsp;·&nbsp;&nbsp;📋 {o["sell_order_count"]} venta / {o["buy_order_count"]} compra'
                    f'&nbsp;&nbsp;·&nbsp;&nbsp;Confianza: {o.get("confidence", 0):.0f}%</div>',
                    unsafe_allow_html=True,
                )
                exit_human = o.get("estimated_exit_human")
                if exit_human:
                    ref_size = o.get("estimated_exit_position_size", 100)
                    st.markdown(
                        f'<div class="jt-meta-row">⏱️ Tiempo estimado de venta ({ref_size:,.0f}u de referencia): '
                        f'<span class="jt-mono">{exit_human}</span></div>',
                        unsafe_allow_html=True,
                    )
                st.divider()
                if o.get("explanation"):
                    render_explanation(o["explanation"])
                    st.divider()
                if o.get("score_breakdown"):
                    st.markdown("**📐 Desglose numérico del score**")
                    render_score_breakdown(o["score_breakdown"])


def show_opportunity_table(opportunities: List[Dict[str, Any]]) -> None:
    """
    Muestra una tabla compacta (una fila por ítem) de oportunidades,
    incluyendo la recomendación. Útil para vistas resumidas donde una
    tarjeta completa por ítem sería demasiado (p.ej. listas largas en
    Tracked Items, o Discovery con miles de ítems).
    """
    if not opportunities:
        st.info("No hay oportunidades para mostrar.")
        return

    data = []
    for o in opportunities:
        kind, icon = _BADGE_STYLE.get(o.get("recommendation"), ("info", "➖"))
        label = _BADGE_LABELS.get(o.get("recommendation"), "Neutral")
        data.append({
            "Item": o["type_name"],
            # Recomendación justo al lado del nombre, con ícono -- antes
            # era la 6ta columna con la palabra plana ("buy", "neutral"),
            # se perdía entre el resto de los números. Feedback real:
            # "la recomendación tiene que ser protagonista".
            "Recomendación": f"{icon} {label}",
            "Score": round(o["score"], 1),
            "ROI %": round(o["roi_percent"], 1),
            "Riesgo": o["risk"]["risk_level"],
            "Liquidez": round(o["liquidity"]["liquidity_score"], 1),
            "Órdenes venta": o["sell_order_count"],
            "Órdenes compra": o["buy_order_count"],
            "Buy Price": o["buy_price"],
            "Sell Price": o["sell_price"],
            "Tiempo venta (ref. 100u)": o.get("estimated_exit_human") or "-",
        })

    st.dataframe(data, use_container_width=True, hide_index=True)
