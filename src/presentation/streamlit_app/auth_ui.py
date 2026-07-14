"""
Presentation/Streamlit: auth_ui

Login/logout compartido entre `app.py` y `pages/02_tracked_items.py` --
maneja la persistencia de sesión (`st.session_state`, que sobrevive
reruns dentro de la misma pestaña del browser) y la detección del token
que EVE SSO devuelve en la URL después de un login exitoso.

⚠️ NO EJECUTADO -- primera vez que se prueba de verdad va a ser cuando
el usuario tenga credenciales reales de EVE SSO configuradas. Ver
docs/ROADMAP_Y_PENDIENTES.md.
"""

import streamlit as st
from presentation.api_client import ApiClient


def restore_session_from_query_params(client: ApiClient) -> None:
    """
    Al volver de EVE SSO, la URL trae `?session_token=...` -- lo
    guardamos en `session_state` (persiste entre reruns de ESTA
    pestaña) y lo sacamos de la URL para no dejarlo visible ni
    reprocesarlo en cada rerun. Si ya había una sesión guardada de
    antes (se navegó a otra página de la app), la restauramos en el
    cliente sin pedir login de nuevo.

    Llamar esto ANTES de cualquier otra lógica que dependa de si el
    usuario está logueado -- primero en `app.py` y en cada página.
    """
    if "session_token" in st.query_params:
        st.session_state["session_token"] = st.query_params["session_token"]
        del st.query_params["session_token"]

    token = st.session_state.get("session_token")
    if token:
        client.set_session_token(token)


def render_login_sidebar(client: ApiClient, current_page_url: str) -> None:
    """
    Botón de "Iniciar sesión con EVE" si no hay sesión, o nombre del
    personaje + botón de logout si la hay.

    `current_page_url` es a dónde EVE SSO debe devolver al browser una
    vez que el login termine -- típicamente la URL de esta misma
    página (`http://localhost:8501/`).
    """
    st.sidebar.divider()

    if client.is_authenticated:
        me = client.get_me()
        if me:
            st.sidebar.success(f"👤 **{me['eve_character_name']}**")
            if st.sidebar.button("Cerrar sesión", use_container_width=True):
                client.clear_session_token()
                st.session_state.pop("session_token", None)
                st.rerun()
            return
        # El token que teníamos guardado ya no es válido (expiró, o el
        # usuario ya no existe) -- lo limpiamos y mostramos el login de nuevo.
        client.clear_session_token()
        st.session_state.pop("session_token", None)
        st.sidebar.info("Tu sesión expiró -- iniciá sesión de nuevo.")

    login_url = client.get_login_url(frontend_redirect=current_page_url)
    st.sidebar.link_button("🔐 Iniciar sesión con EVE", login_url, use_container_width=True)
    st.sidebar.caption(
        "Opcional -- sin sesión seguís viendo Discovery igual, pero no podés "
        "tener tu propia watchlist personal."
    )
