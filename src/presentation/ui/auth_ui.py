"""
Presentation/UI (NiceGUI): auth_ui

Login/logout compartido entre `pages/dashboard.py` y
`pages/tracked_items.py`.

⚠️ Importante sobre concurrencia (por qué NO se comparte un ApiClient
entre páginas/conexiones): cada `@ui.page(...)` corre una vez POR
CONEXIÓN de browser -- si `main.py` construyera un único `ApiClient()`
a nivel de módulo y lo pasara a las páginas (como hacía la versión
anterior a multi-tenancy), TODOS los navegadores conectados
compartirían la misma instancia, y con ella el mismo `session_token`.
El login de una persona se filtraría a la sesión de otra. Por eso cada
función de página construye su PROPIO `ApiClient()` -- ver
`pages/dashboard.py` / `pages/tracked_items.py`, cada una llama
`ApiClient()` fresco al principio de la función, no lo recibe como
parámetro compartido.

Persistencia entre navegaciones (Dashboard -> Tracked Items y viceversa):
usa `app.storage.user` de NiceGUI (almacenamiento por navegador, atado a
una cookie que NiceGUI maneja solo) -- requiere `storage_secret`
configurado en `ui.run()` (ver `main.py`). ⚠️ NO PROBADO contra la
versión real de NiceGUI en este entorno -- si `app.storage.user` no
existe o se comporta distinto en la versión instalada, esto es lo
primero a revisar.
"""

from typing import Optional

from presentation.api_client import ApiClient


def restore_session(client: ApiClient, session_token: Optional[str]) -> None:
    """
    `session_token` es el query param que NiceGUI ya resolvió como
    argumento de la función de página (ver `@ui.page` en
    dashboard.py/tracked_items.py) -- llega con valor la primera vez que
    el browser vuelve de EVE SSO. Si viene, lo guardamos en
    `app.storage.user` para que sobreviva a la próxima navegación sin
    tener que repetirlo en cada URL. Si no viene, tratamos de restaurar
    lo que ya estuviera guardado de antes.
    """
    from nicegui import app

    if session_token:
        app.storage.user["session_token"] = session_token
    else:
        session_token = app.storage.user.get("session_token")

    if session_token:
        client.set_session_token(session_token)


def render_login_section(client: ApiClient, current_page_url: str) -> None:
    """Sección de login/logout -- pensada para ir en el header o el costado de cada página."""
    from nicegui import ui, app

    if client.is_authenticated:
        me = client.get_me()
        if me:
            with ui.row().classes("items-center gap-2"):
                ui.label(f"👤 {me['eve_character_name']}").classes("jt-mono")

                def do_logout():
                    client.clear_session_token()
                    app.storage.user.pop("session_token", None)
                    ui.navigate.reload()

                ui.button("Cerrar sesión", on_click=do_logout).props("flat dense")
            return
        # Token guardado pero ya no válido (expiró, etc.)
        client.clear_session_token()
        app.storage.user.pop("session_token", None)
        ui.label("Tu sesión expiró.").classes("text-caption")

    login_url = client.get_login_url(frontend_redirect=current_page_url)
    ui.link("🔐 Iniciar sesión con EVE", login_url)
