"""
Tests/_winsafe: borrado seguro de archivos temporales de SQLite.

Hallazgo real (reportado por el usuario corriendo `pytest` en Windows):
en POSIX (Linux/Mac), se puede borrar un archivo aunque siga abierto --
el handle sigue funcionando hasta que se cierra, pero el `unlink` en sí
nunca falla. En Windows, el sistema de archivos bloquea el borrado
mientras CUALQUIER proceso tenga el archivo abierto -- si una conexión
SQLite no se cerró explícitamente antes del `finally: db_path.unlink(...)`
de un test (confiando en que el garbage collector la cierre sola, lo
cual pasa casi siempre en CPython pero no está garantizado que pase
ANTES del unlink), Windows tira `PermissionError: [WinError 32]`.

Esto nunca se vio corriendo los tests en este entorno (Linux) -- la
primera vez que se corrió en Windows real fue cuando lo hizo el
usuario, y ahí apareció. `safe_unlink` reintenta con un `gc.collect()`
de por medio (fuerza a Python a cerrar conexiones sin referencias
pendientes) antes de rendirse.
"""

import gc
import time
from pathlib import Path


def safe_unlink(path: Path, attempts: int = 5, delay: float = 0.1) -> None:
    """
    Reemplazo de `path.unlink(missing_ok=True)` seguro en Windows.
    En POSIX esto es esencialmente un no-op extra (el unlink normal ya
    funciona a la primera) -- el retry solo importa en Windows.
    """
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
            time.sleep(delay)
    # Último intento -- si sigue fallando acá, que se vea el error real
    # en vez de tragárselo en silencio para siempre.
    path.unlink(missing_ok=True)
