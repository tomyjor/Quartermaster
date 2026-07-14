"""
Presentation/UI (NiceGUI): theme

Mismos tokens de diseño que `streamlit_app/theme.py` -- misma paleta,
misma tipografía, mismos umbrales de color para score/riesgo/liquidez
-- para que Streamlit y NiceGUI se sientan la misma herramienta, no dos
apps distintas. NiceGUI no tiene un archivo de config declarativo tipo
`.streamlit/config.toml`, así que el theming se aplica por código al
arrancar cada página.

⚠️ NO EJECUTADO -- requiere `nicegui`, no instalado en este entorno.
"""

# ============================================================
# TOKENS -- deben coincidir con streamlit_app/theme.py. Si cambia uno,
# cambia el otro, para que ambas UIs se vean coherentes entre sí.
# ============================================================

COLOR_BG = "#090D16"
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

#: Paleta específica de inputs/selectores -- pedido explícito del
#: usuario ("Sci-Fi / Tactical Dark Mode"): los campos de NiceGUI por
#: default son planos, de bajo contraste, "cero accesibles" comparados
#: con Streamlit. Slate en vez de los grises del resto de la paleta a
#: propósito -- da un contenedor sólido, no una línea plana.
COLOR_INPUT_BG = "rgba(15, 23, 42, 0.9)"      # slate-900/90
COLOR_INPUT_BORDER = "#1e293b"                 # slate-800
COLOR_INPUT_BORDER_FOCUS = "rgba(245, 158, 11, 0.5)"  # amber-500/50
COLOR_INPUT_TEXT = "#f1f5f9"                   # slate-100
COLOR_INPUT_PLACEHOLDER = "#94a3b8"            # slate-400

#: Mismos umbrales que `OpportunityExplainer` -- el color de un
#: indicador nunca debe contradecir el texto que lo acompaña.
STRENGTH_THRESHOLD = 70.0
WEAKNESS_THRESHOLD = 40.0

RISK_COLORS = {
    "Low": COLOR_SUCCESS,
    "Medium": COLOR_WARNING,
    "High": "#E08A4F",
    "Critical": COLOR_DANGER,
}

FONT_HEADING = "Rajdhani"
FONT_MONO = "JetBrains Mono"


def band_color(value: float) -> str:
    """Mismo esquema de color que `streamlit_app/theme._band_color`."""
    if value >= STRENGTH_THRESHOLD:
        return COLOR_SUCCESS
    if value >= WEAKNESS_THRESHOLD:
        return COLOR_WARNING
    return COLOR_DANGER


def styled_search_input(placeholder: str, on_change=None):
    """
    Input de búsqueda "premium" -- contenedor sólido, ícono de lupa,
    contraste alto, foco ámbar. Pedido explícito del usuario: los
    inputs default de NiceGUI son "cero accesibles" comparados con
    Streamlit. Devuelve el `ui.input` ya creado y estilizado -- usar
    `.value` / `.on_value_change` como con cualquier `ui.input` normal.
    """
    from nicegui import ui

    field = ui.input(placeholder=placeholder, on_change=on_change).props(
        "outlined dark color=amber"
    ).classes("jt-input-wrapper w-full")
    with field.add_slot("prepend"):
        ui.icon("search").classes("text-slate-400")
    return field


def styled_select(label: str, options, on_change=None, multiple: bool = False):
    """
    Select "premium" -- mismo contenedor sólido que `styled_search_input`,
    props de Quasar (`outlined dark color=amber`) para que el menú
    desplegable respete la estética táctica en vez del blanco/gris
    default de Quasar (ver `.q-menu` en el CSS de `apply_theme`).
    """
    from nicegui import ui

    field = ui.select(
        options, label=label, on_change=on_change, multiple=multiple,
    ).props("outlined dark color=amber options-dark").classes("jt-input-wrapper w-full")
    return field


def apply_theme() -> None:
    """
    Aplica el tema oscuro + sistema de diseño completo a la app NiceGUI.
    Llamar al principio de CADA función de página (ver nota en
    `pages/dashboard.py` sobre por qué no puede ir a nivel de módulo en
    NiceGUI 3.x).
    """
    from nicegui import ui

    ui.dark_mode().enable()
    ui.colors(primary=COLOR_PRIMARY, secondary=COLOR_SURFACE)

    ui.add_head_html(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family={FONT_HEADING}:wght@500;600;700&family={FONT_MONO.replace(' ', '+')}:wght@500;600;700&display=swap');

        body {{
            background-color: {COLOR_BG} !important;
            color: {COLOR_TEXT};
        }}

        .jt-heading {{
            font-family: '{FONT_HEADING}', sans-serif !important;
            letter-spacing: 0.02em;
        }}
        .jt-mono {{
            font-family: '{FONT_MONO}', monospace !important;
            font-weight: 600;
            color: {COLOR_TEXT_SECONDARY};
        }}
        .jt-muted {{
            color: {COLOR_TEXT_MUTED};
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .jt-card {{
            background-color: {COLOR_SURFACE} !important;
            border: 1px solid {COLOR_BORDER};
            border-radius: 14px;
            padding: 4px;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        .jt-card:hover {{
            border-color: {COLOR_BORDER_HOVER};
            box-shadow: 0 4px 20px rgba(232, 163, 61, 0.10);
        }}

        /* Pill de score -- mismos umbrales/colores que el lado Streamlit. */
        .jt-score-pill {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 700;
            font-size: 1.5rem;
            padding: 0.2rem 0.85rem;
            border-radius: 10px;
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
            margin-top: 3px;
        }}
        .jt-liquidity-bar-fill {{
            height: 100%;
            border-radius: 999px;
        }}

        /* ============================================================
           Inputs y selects -- punto débil explícito señalado por el
           usuario: por default en NiceGUI son planos, una línea
           inferior nomás, bajo contraste, "cero accesibles" comparado
           con Streamlit. Los componentes de NiceGUI son Quasar por
           dentro -- Tailwind en .classes() no penetra los pseudo-
           elementos que Quasar usa para el borde "outlined" (:before),
           hace falta apuntar directo a esas clases internas.
           ============================================================ */
        .jt-input-wrapper .q-field__control {{
            background-color: {COLOR_INPUT_BG} !important;
            border-radius: 10px !important;
            padding-left: 4px;
        }}
        .jt-input-wrapper .q-field--outlined .q-field__control:before {{
            border: 1.5px solid {COLOR_INPUT_BORDER} !important;
            border-radius: 10px !important;
        }}
        .jt-input-wrapper .q-field--outlined.q-field--focused .q-field__control:before,
        .jt-input-wrapper .q-field--outlined.q-field--highlighted .q-field__control:before {{
            border-color: {COLOR_INPUT_BORDER_FOCUS} !important;
            border-width: 2px !important;
        }}
        .jt-input-wrapper .q-field__native,
        .jt-input-wrapper .q-field__input,
        .jt-input-wrapper .q-field__prefix,
        .jt-input-wrapper .q-field__suffix {{
            color: {COLOR_INPUT_TEXT} !important;
            font-family: '{FONT_MONO}', monospace !important;
        }}
        .jt-input-wrapper .q-field__native::placeholder {{
            color: {COLOR_INPUT_PLACEHOLDER} !important;
            opacity: 1 !important;
        }}
        .jt-input-wrapper .q-field__label {{
            color: {COLOR_INPUT_PLACEHOLDER} !important;
        }}
        .jt-input-wrapper .q-icon {{
            color: {COLOR_INPUT_PLACEHOLDER} !important;
        }}
        .jt-input-wrapper .q-field--focused .q-icon {{
            color: {COLOR_PRIMARY} !important;
        }}
        /* Menú desplegable de ui.select -- mismo fondo sólido que el
           input, no el blanco/gris default de Quasar que rompería la
           estética táctica. */
        .q-menu {{
            background-color: {COLOR_SURFACE_ELEVATED} !important;
            border: 1px solid {COLOR_INPUT_BORDER} !important;
            border-radius: 10px !important;
        }}
        .q-menu .q-item {{
            color: {COLOR_INPUT_TEXT} !important;
            font-family: '{FONT_MONO}', monospace !important;
        }}
        .q-menu .q-item.q-manual-focusable--focused,
        .q-menu .q-item:hover {{
            background-color: rgba(232, 163, 61, 0.12) !important;
        }}

        /* Botones -- compactos, bordes definidos, sin colores sólidos
           chillones (pedido explícito). */
        .jt-btn-compact {{
            border-radius: 8px !important;
            font-family: '{FONT_MONO}', monospace !important;
            font-weight: 600 !important;
            font-size: 0.82rem !important;
            padding: 0.4rem 0.85rem !important;
            text-transform: none !important;
            letter-spacing: 0.01em;
            transition: filter 0.15s ease, border-color 0.15s ease;
        }}
        .jt-btn-compact:hover {{
            filter: brightness(1.15);
        }}

        /* Tarjeta horizontal compacta de producto -- reemplaza las
           tarjetas grandes de antes en la lista de trackeados. Borde
           fino translúcido, hover elegante, sin ocupar tanto alto por
           ítem (pedido explícito: "en vez de cajas enormes, hazlas
           compactas"). */
        .jt-row-card {{
            background-color: {COLOR_SURFACE} !important;
            border: 1px solid {COLOR_INPUT_BORDER};
            border-radius: 10px;
            padding: 0.65rem 1rem;
            transition: border-color 0.15s ease, background-color 0.15s ease;
        }}
        .jt-row-card:hover {{
            border-color: {COLOR_BORDER_HOVER};
            background-color: {COLOR_SURFACE_ELEVATED} !important;
        }}

        /* Barra de navegación -- pedido explícito: antes era texto
           plano sin ningún contenedor. Ahora tiene fondo propio, borde
           inferior, y la pestaña activa se marca con una línea de
           color abajo (como pestañas reales), no solo un cambio de
           color de texto. */
        .jt-nav-bar {{
            background-color: {COLOR_SURFACE};
            border-bottom: 1px solid {COLOR_INPUT_BORDER};
            padding: 0.6rem 1rem;
            margin-bottom: 0.75rem;
        }}
        .jt-nav-tab {{
            font-family: '{FONT_HEADING}', sans-serif !important;
            color: {COLOR_TEXT_SECONDARY} !important;
            text-decoration: none !important;
            padding: 0.4rem 0.9rem;
            border-radius: 6px 6px 0 0;
            border-bottom: 2px solid transparent;
            transition: color 0.15s ease, border-color 0.15s ease;
        }}
        .jt-nav-tab:hover {{
            color: {COLOR_TEXT} !important;
        }}
        .jt-nav-tab-active {{
            color: {COLOR_PRIMARY} !important;
            border-bottom: 2px solid {COLOR_PRIMARY};
        }}

        /* Panel de sidebar -- mismo lenguaje que .jt-row-card pero para
           contenedores más grandes (filtros, watchlist), no filas de
           lista. Consistencia visual entre Tracked Items y Dashboard. */
        .jt-panel {{
            background-color: {COLOR_SURFACE} !important;
            border: 1px solid {COLOR_INPUT_BORDER};
            border-radius: 12px;
            padding: 1rem;
        }}

        /* Sidebar (ui.left_drawer) -- Quasar le pone su propio fondo
           al q-drawer que pisa cualquier clase Tailwind/custom que se
           le ponga al elemento en sí (pedido explícito: el sidebar se
           veía "texto tirado en un fondo", sin panel real detrás).
           Hay que apuntar a la clase interna de Quasar directo, no
           alcanza con .classes() en el elemento de NiceGUI. La
           `.jt-panel` real va en un `ui.column()` ADENTRO del drawer
           (no en el drawer mismo), esta regla solo ajusta el margen
           para que no quede pegado al borde. */
        .q-drawer {{
            background-color: {COLOR_BG} !important;
            border-right: 1px solid {COLOR_INPUT_BORDER} !important;
        }}
        .q-drawer .jt-panel {{
            margin: 0.75rem;
            margin-top: 1rem;
        }}

        /* Sliders -- thumb reforzado para que se vea sólido, no una
           línea fina perdida sobre el track. */
        .q-slider__track-container--h {{
            height: 6px !important;
        }}
        .q-slider__thumb {{
            transform: scale(1.15);
        }}

        /* Banners de estado (Discovery activo, avisos) -- mismo
           lenguaje visual que el banner de recomendación de las
           tarjetas, para que la jerarquía de información sea coherente
           en toda la página, no texto plano suelto. */
        .jt-status-banner {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(91, 155, 213, 0.10);
            border-left: 4px solid {COLOR_INFO};
            border-radius: 8px;
            padding: 0.55rem 0.9rem;
            margin: 0.5rem 0;
            font-size: 0.92rem;
            color: {COLOR_INFO};
        }}
        .jt-status-banner.warning {{
            background: rgba(232, 163, 61, 0.10);
            border-left-color: {COLOR_WARNING};
            color: {COLOR_WARNING};
        }}

        /* AG-Grid -- tema oscuro nativo en vez del claro default, que
           desentonaba fuerte con el resto de la página. */
        .ag-theme-alpine-dark {{
            --ag-background-color: {COLOR_SURFACE};
            --ag-header-background-color: {COLOR_SURFACE_ELEVATED};
            --ag-odd-row-background-color: rgba(255,255,255,0.02);
            --ag-border-color: {COLOR_INPUT_BORDER};
            --ag-header-foreground-color: {COLOR_TEXT_SECONDARY};
            --ag-foreground-color: {COLOR_TEXT};
            --ag-font-family: '{FONT_MONO}', monospace;
        }}
    </style>
    """)


def score_pill_html(score: float) -> str:
    """Igual a `streamlit_app/theme.score_pill_html` -- mismo output, distinto framework consumiéndolo."""
    color = band_color(score)
    bg = f"{color}29"
    return f'<span class="jt-score-pill" style="background:{bg}; color:{color};">{score:.1f}</span>'


def risk_badge_html(risk_level: str) -> str:
    """Igual a `streamlit_app/theme.risk_badge_html`."""
    color = RISK_COLORS.get(risk_level, COLOR_TEXT_SECONDARY)
    bg = f"{color}22"
    return f'<span class="jt-risk-badge" style="background:{bg}; color:{color};">⬤ {risk_level}</span>'


def liquidity_pill_html(liquidity_score: float) -> str:
    """
    Pill compacto -- mismo lenguaje visual que `risk_badge_html`. Ver
    `streamlit_app/theme.liquidity_pill_html`: reemplaza la barra larga
    y fina que quedaba fuera de lugar comparada con el resto de los
    indicadores (feedback real del usuario).
    """
    color = band_color(liquidity_score)
    bg = f"{color}22"
    return f'<span class="jt-risk-badge" style="background:{bg}; color:{color};">{liquidity_score:.0f}/100</span>'


def liquidity_bar_html(liquidity_score: float) -> str:
    """Barra horizontal -- versión con más detalle, para el panel expandido. Ver `liquidity_pill_html` para la tarjeta principal."""
    color = band_color(liquidity_score)
    pct = max(0.0, min(100.0, liquidity_score))
    return (
        f'<div class="jt-liquidity-bar-track">'
        f'<div class="jt-liquidity-bar-fill" style="width:{pct}%; background:{color};"></div>'
        f'</div>'
    )
