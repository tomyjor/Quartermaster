"""
Shared: paths

Resuelve la raíz del proyecto y la ruta default de la base de datos de
forma robusta, sin depender de cuál es el directorio de trabajo (cwd)
del proceso que ejecuta el código.

--------------------------------------------------------------------------
Bug real que motivó esto
--------------------------------------------------------------------------
Varios módulos (`ApiServices`, `SmartAutoSeedJob`, `SyncStatusRepository`,
los repos SQLite, el scheduler) tenían `Path("database/trader.db")` como
default -- una ruta RELATIVA. Eso se resuelve contra el cwd del proceso,
no contra la ubicación del proyecto. `uvicorn --app-dir <ruta>` solo
agrega esa carpeta a `sys.path` para que los imports funcionen -- NO
cambia el cwd del proceso. Si alguien lanza uvicorn parado en su carpeta
de usuario (`cd` nunca hecho a la carpeta del proyecto), "database/trader.db"
apuntaba a un archivo que no existe ahí, con
`sqlite3.OperationalError: unable to open database file` -- exactamente
lo que le pasó a un usuario real en producción.

Esto reemplaza todos esos defaults relativos por una ruta absoluta,
calculada subiendo directorios desde la ubicación de ESTE archivo (que
es estable, no depende de desde dónde se lance python) hasta encontrar
la carpeta `database/` del proyecto -- mismo patrón que
`_find_project_root()` ya usaba en las páginas de Streamlit para
resolver `sys.path`, ahora centralizado y reusado también del lado del
server.
"""

from pathlib import Path


def get_project_root() -> Path:
    """
    Sube directorios desde la ubicación de este archivo hasta encontrar
    la raíz del proyecto (la que contiene `database/`). Estable sin
    importar el cwd del proceso que importa este módulo.
    """
    current = Path(__file__).resolve().parent
    while not (current / "database").exists() and current.parent != current:
        current = current.parent
    return current


PROJECT_ROOT = get_project_root()
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "trader.db"
