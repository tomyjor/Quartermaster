"""
Shared/db: apertura de conexiones SQLite consistente en todo el proyecto.

Hallazgo real (reportado por el usuario): `database disk image is
malformed` durante el Smart Auto-Seed en background MIENTRAS la UI
leía al mismo tiempo. Revisando el código: ninguna conexión en todo el
proyecto seteaba `busy_timeout` -- sin eso, si una conexión encuentra
el archivo bloqueado por otra (así sea un instante, durante un
checkpoint de WAL), SQLite falla inmediato en vez de esperar/reintentar
un rato. `journal_mode=WAL` ya estaba en el schema (permite múltiples
lectores + un escritor a la vez), pero WAL sin `busy_timeout` sigue
siendo frágil bajo el patrón de acceso real de este proyecto: un job de
seed escribiendo en background mientras dos UIs distintas leen al
mismo tiempo.

`busy_timeout` no arregla corrupción real de archivo (eso es un
problema de sistema de archivos/antivirus, no algo que Python pueda
arreglar) -- pero reduce la ventana de contención real que puede
contribuir a que un checkpoint quede a medias.
"""

import sqlite3
from pathlib import Path
from typing import Union

#: 5 segundos -- tiempo que una conexión espera a que el archivo se
#: libere antes de fallar con "database is locked", en vez de fallar
#: inmediato. Generoso a propósito: mejor una request que tarda un poco
#: más que una que falla en seco por una escritura de background que
#: iba a terminar en milisegundos.
DEFAULT_BUSY_TIMEOUT_MS = 5000


def connect_db(db_path: Union[str, Path], busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS, **kwargs) -> sqlite3.Connection:
    """
    Reemplazo de `sqlite3.connect(db_path)` -- usar SIEMPRE esta
    función en vez de `sqlite3.connect` directo en cualquier
    repositorio/importador nuevo, para que `busy_timeout` esté
    garantizado en todos lados, no solo donde alguien se acordó de
    setearlo a mano. `**kwargs` pasa directo a `sqlite3.connect` (ej.
    `check_same_thread=False` para los importadores con threads).
    """
    conn = sqlite3.connect(db_path, **kwargs)
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    return conn
