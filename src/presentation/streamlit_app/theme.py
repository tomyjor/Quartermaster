"""
Presentation: theme (Streamlit)

Sistema de diseño completo -- no un par de reglas CSS sueltas. Define
tokens (color, tipografía, spacing) una sola vez y los reusa tanto en
CSS global como en los componentes HTML custom (pills, badges, barras)
que arma `components/opportunity_table.py`. El objetivo del rediseño:
que la app se sienta una herramienta profesional de inteligencia de
mercado, no un visor de datos con el theme default de Streamlit.

Vive en presentación porque es puramente estético -- cero lógica de
negocio acá. Los UMBRALES de color (qué es "fuerte"/"débil") sí replican
los de `OpportunityExplainer` a propósito, para que el color de un pill
nunca contradiga lo que dice el texto de al lado.
"""

import streamlit as st

# ============================================================
# TOKENS -- fuente única de verdad para color/tipografía/spacing.
# Reusados tanto en el CSS inyectado como en los componentes HTML
# custom de opportunity_table.py, para que nunca queden desincronizados.
# ============================================================

COLOR_BG = "#0B0D12"
COLOR_SURFACE = "#151822"
COLOR_SURFACE_ELEVATED = "#1C202C"
COLOR_BORDER = "rgba(232, 163, 61, 0.14)"
COLOR_BORDER_HOVER = "rgba(232, 163, 61, 0.42)"

COLOR_PRIMARY = "#E8A33D"
COLOR_TEXT = "#F0EEE8"
COLOR_TEXT_SECONDARY = "#A8A59E"
COLOR_TEXT_MUTED = "#6B6860"

COLOR_SUCCESS = "#3DBA6D"
COLOR_WARNING = "#E8A33D"
COLOR_DANGER = "#E2685F"
COLOR_INFO = "#5B9BD5"

# Mismos umbrales que OpportunityExplainer (STRENGTH/WEAKNESS) -- el
# color de un indicador nunca debe contradecir el texto que lo acompaña.
STRENGTH_THRESHOLD = 70.0
WEAKNESS_THRESHOLD = 40.0

FONT_DISPLAY = "Rajdhani"
FONT_MONO = "JetBrains Mono"

RISK_COLORS = {
    "Low": COLOR_SUCCESS,
    "Medium": COLOR_WARNING,
    "High": "#E08A4F",
    "Critical": COLOR_DANGER,
}


def _band_color(value: float) -> str:
    if value >= STRENGTH_THRESHOLD:
        return COLOR_SUCCESS
    if value >= WEAKNESS_THRESHOLD:
        return COLOR_WARNING
    return COLOR_DANGER


def inject_theme() -> None:
    """Inyecta el CSS del sistema de diseño. Llamar una sola vez por página, después de `st.set_page_config`."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family={FONT_DISPLAY}:wght@500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

        :root {{
            --jt-bg: {COLOR_BG};
            --jt-surface: {COLOR_SURFACE};
            --jt-surface-elevated: {COLOR_SURFACE_ELEVATED};
            --jt-border: {COLOR_BORDER};
            --jt-border-hover: {COLOR_BORDER_HOVER};
            --jt-primary: {COLOR_PRIMARY};
            --jt-text: {COLOR_TEXT};
            --jt-text-secondary: {COLOR_TEXT_SECONDARY};
            --jt-text-muted: {COLOR_TEXT_MUTED};
            --jt-success: {COLOR_SUCCESS};
            --jt-warning: {COLOR_WARNING};
            --jt-danger: {COLOR_DANGER};
            --jt-info: {COLOR_INFO};
        }}

        /* ---------- Tipografía ---------- */
        h1, h2, h3 {{
            font-family: '{FONT_DISPLAY}', sans-serif !important;
            letter-spacing: 0.02em;
        }}
        h1 {{
            font-weight: 700 !important;
            border-bottom: 2px solid var(--jt-border-hover);
            padding-bottom: 0.5rem;
            margin-bottom: 1.2rem !important;
        }}
        h2, h3 {{ font-weight: 600 !important; }}

        p, .stMarkdown, div[data-testid="stCaptionContainer"] {{
            color: var(--jt-text-secondary);
        }}

        div[data-testid="stMetricValue"] {{
            font-family: '{FONT_MONO}', monospace !important;
            font-weight: 700;
        }}
        div[data-testid="stMetricLabel"] {{
            opacity: 0.7;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-size: 0.72rem !important;
            color: var(--jt-text-muted) !important;
        }}

        /* ---------- Tarjetas ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 14px !important;
            border-color: var(--jt-border) !important;
            background: var(--jt-surface);
            transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
            padding: 0.3rem 0.15rem;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
            border-color: var(--jt-border-hover) !important;
            box-shadow: 0 4px 20px rgba(232, 163, 61, 0.10);
        }}

        /* ---------- Sidebar ---------- */
        section[data-testid="stSidebar"] {{
            border-right: 1px solid var(--jt-border);
            background: var(--jt-bg);
        }}
        section[data-testid="stSidebar"] h3 {{
            font-size: 1rem !important;
            opacity: 0.9;
        }}

        /* ---------- Botones ---------- */
        button[kind="primary"] {{
            font-weight: 600 !important;
            letter-spacing: 0.02em;
            border-radius: 8px !important;
        }}
        button[kind="secondary"] {{
            border-radius: 8px !important;
        }}

        /* ---------- Expanders (panel "Ver análisis completo") ---------- */
        div[data-testid="stExpander"] {{
            border-radius: 10px !important;
            border-color: var(--jt-border) !important;
            background: var(--jt-surface-elevated);
        }}

        /* ---------- Componentes custom (ver funciones _html abajo) ---------- */
        .jt-score-pill {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 700;
            font-size: 1.5rem;
            padding: 0.2rem 0.85rem;
            border-radius: 10px;
            line-height: 1.3;
            min-width: 3.2rem;
        }}

        .jt-risk-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 600;
            font-size: 0.85rem;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
        }}

        .jt-liquidity-bar-track {{
            width: 100%;
            height: 8px;
            border-radius: 999px;
            background: rgba(255,255,255,0.06);
            overflow: hidden;
            margin-top: 0.15rem;
        }}
        .jt-liquidity-bar-fill {{
            height: 100%;
            border-radius: 999px;
            transition: width 0.2s ease;
        }}

        .jt-badge-banner {{
            border-radius: 10px;
            padding: 0.6rem 0.9rem;
            font-size: 0.92rem;
            line-height: 1.4;
            margin: 0.5rem 0;
        }}

        .jt-meta-row {{
            color: var(--jt-text-muted);
            font-size: 0.82rem;
            margin: 0.35rem 0;
        }}
        .jt-meta-row .jt-mono {{
            font-family: '{FONT_MONO}', monospace;
            color: var(--jt-text-secondary);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Componentes HTML reusables -- devuelven un string, el caller decide
# cuándo pintarlo con `st.markdown(..., unsafe_allow_html=True)`.
# Centralizados acá (no repetidos en cada call site) para que un cambio
# de diseño futuro se haga en un solo lugar.
# ============================================================

def score_pill_html(score: float) -> str:
    """Pill de score coloreado por rango -- mismos umbrales que OpportunityExplainer."""
    color = _band_color(score)
    bg = f"{color}29"  # mismo hex + alpha ~16%, _band_color siempre devuelve hex
    return f'<span class="jt-score-pill" style="background:{bg}; color:{color};">{score:.1f}</span>'


def risk_badge_html(risk_level: str) -> str:
    """Badge de nivel de riesgo con color semántico (Low=verde .. Critical=rojo)."""
    color = RISK_COLORS.get(risk_level, COLOR_TEXT_SECONDARY)
    bg = f"{color}22"
    return f'<span class="jt-risk-badge" style="background:{bg}; color:{color};">⬤ {risk_level}</span>'


def liquidity_pill_html(liquidity_score: float) -> str:
    """
    Pill compacto para liquidez -- MISMO lenguaje visual que
    `risk_badge_html` (mismo tamaño, misma forma de píldora), para que
    ROI/Riesgo/Liquidez tengan el mismo peso visual entre sí.

    v2 (feedback real): antes esto era una barra horizontal larga y
    fina (`liquidity_bar_html`) que ocupaba todo el ancho de su columna
    -- "la barra de liquidez es muy larga y chiquita, queda fuera de
    lugar comparado con el resto". Reemplazada por este pill, que se ve
    y pesa igual que el badge de riesgo de al lado.
    """
    color = _band_color(liquidity_score)
    bg = f"{color}22"
    return (
        f'<span class="jt-risk-badge" style="background:{bg}; color:{color};">'
        f'{liquidity_score:.0f}/100</span>'
    )


def liquidity_bar_html(liquidity_score: float) -> str:
    """
    Barra horizontal 0-100 -- versión más detallada, para contextos con
    más espacio (ej. el panel expandido). Para la tarjeta principal usar
    `liquidity_pill_html`, no esta -- ver su docstring para el porqué.
    """
    color = _band_color(liquidity_score)
    pct = max(0.0, min(100.0, liquidity_score))
    return (
        f'<div class="jt-liquidity-bar-track">'
        f'<div class="jt-liquidity-bar-fill" style="width:{pct}%; background:{color};"></div>'
        f'</div>'
    )
