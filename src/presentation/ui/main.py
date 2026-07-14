"""
Presentation/UI (NiceGUI): main entrypoint.

⚠️ NO EJECUTADO -- requiere `nicegui` (`pip install nicegui`, o
`pip install -e ".[api]"` si ya arreglaste el bug de hatchling -- ver
sección "Si igual querés pip install -e" en el README). No hay red en
este entorno para instalarlo ni para correrlo, así que esto está
verificado solo hasta donde se puede sin ejecutar: sintaxis válida,
imports propios resueltos, contra la documentación pública de NiceGUI
1.4 -- no contra una corrida real.

Corre como proceso SEPARADO de la API, mismo patrón que Streamlit: un
cliente HTTP más, en su propio puerto (8502 por default, para no chocar
con la API en 8000 ni con Streamlit en 8501 si los corrés juntos
durante la migración -- no hace falta apagar Streamlit para probar esto).

Para correrlo (una vez instalado nicegui):

    python -m presentation.ui.main --app-dir src

Si esa invocación no resuelve los imports igual que uvicorn con
`--app-dir` (NiceGUI no es un servidor ASGI genérico como uvicorn, así
que `--app-dir` podría no ser un flag válido acá) -- alternativa segura,
pararse en la carpeta del proyecto y correr:

    cd Quartermaster
    python src\\presentation\\ui\\main.py

Este archivo ya resuelve `sys.path` solo (ver `_find_project_root`,
mismo patrón que las páginas de Streamlit), así que no debería depender
de un flag externo para encontrar el resto del proyecto.
"""

import sys
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    """Ver docstring gemela en streamlit_app/app.py."""
    current = start
    while not (current / "src").exists() and current.parent != current:
        current = current.parent
    return current


sys.path.insert(0, str(_find_project_root(Path(__file__).resolve()) / "src"))

from presentation.ui.pages.dashboard import register_dashboard_page
from presentation.ui.pages.tracked_items import register_tracked_items_page

# v3 (login): ya NO se construye un ApiClient compartido acá -- cada
# página construye el suyo propio, por conexión de browser. Ver
# docstring de `auth_ui.py` para el porqué (evitar que el token de
# sesión de un usuario se filtre a otro navegador conectado al mismo
# proceso).
register_dashboard_page()
register_tracked_items_page()

# El guard `__mp_main__` es el patrón documentado de NiceGUI: el proceso
# de reload interno re-ejecuta este módulo bajo ese nombre, sin el
# guard terminarías con múltiples instancias de la app arrancando.
import os
import secrets

if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import ui
    # Puerto configurable vía variable de entorno -- si 8502 queda
    # ocupado por un proceso zombie de un intento anterior (típico en
    # Windows si no se cerró limpio con Ctrl+C), se puede correr con
    # otro puerto sin tocar código:
    #   $env:QUARTERMASTER_UI_PORT = "8503"; python src\presentation\ui\main.py
    port = int(os.environ.get("QUARTERMASTER_UI_PORT", "8502"))

    # `storage_secret`: necesario para `app.storage.user` (donde se
    # guarda el session_token entre navegaciones, ver `auth_ui.py`).
    # Sin esto, NiceGUI no puede firmar la cookie que identifica a cada
    # navegador. Idealmente fijo (variable de entorno) para que la
    # sesión sobreviva un restart del server -- con un valor random
    # generado en cada arranque (el fallback acá), todos los logins
    # activos se invalidan cada vez que se reinicia el proceso. Para
    # desarrollo local esto es aceptable; para algo compartido con la
    # comunidad, conviene fijar QUARTERMASTER_UI_STORAGE_SECRET.
    storage_secret = os.environ.get("QUARTERMASTER_UI_STORAGE_SECRET", secrets.token_urlsafe(32))

    # `dark` sacado de acá a propósito -- ya se maneja con
    # `ui.dark_mode().enable()` dentro de la página (theme.py), y no
    # tengo certeza de que `dark=` sea un kwarg válido de `ui.run()` en
    # esta versión -- mejor no arriesgar un segundo crash por lo mismo.
    ui.run(title="Quartermaster", port=port, reload=False, storage_secret=storage_secret)
