"""
Migración NO destructiva: agrega multi-tenancy (usuarios vía EVE SSO).

Antes de esto, `tracked_types` era una tabla global -- un solo usuario
implícito para todo el sistema. Esta migración:

1. Crea `users` y `oauth_tokens` (nuevas, vacías).
2. Si `tracked_types` todavía NO tiene columna `user_id` (schema viejo):
   - Crea un usuario "legacy" (placeholder, `eve_character_id=-1` --
     nunca puede colisionar con un character_id real de EVE, que
     siempre es positivo) para ser dueño de lo que ya estaba trackeado.
   - Migra las filas existentes a la tabla nueva con ese `user_id`.
   - NO se pierde ningún dato: los ítems que ya tenías trackeados
     siguen ahí, asociados al usuario legacy hasta que hagas login real
     con tu personaje de EVE y los reclames (ver
     `scripts/claim_legacy_watchlist.py`, Fase 2 de esta migración).
3. Si `tracked_types` YA tiene `user_id` (ya migrado antes), no hace
   nada -- seguro correrlo más de una vez.

SQLite no soporta agregar una columna a una PRIMARY KEY compuesta
existente con ALTER TABLE -- el patrón estándar (y el que se usa acá)
es: crear la tabla nueva con el schema correcto, copiar los datos,
borrar la vieja, renombrar la nueva. Todo dentro de una transacción,
así que si algo falla a la mitad, no queda la base en un estado
intermedio roto.

Uso:
    python scripts/migrate_v4_multi_tenant.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "database" / "trader.db"

#: Nunca puede colisionar con un character_id real de EVE (siempre positivo).
LEGACY_USER_EVE_CHARACTER_ID = -1
LEGACY_USER_NAME = "(legacy -- sin reclamar, hacé login con tu personaje de EVE)"

USERS_AND_TOKENS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eve_character_id INTEGER NOT NULL UNIQUE,
    eve_character_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_eve_character_id
ON users(eve_character_id);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    user_id INTEGER PRIMARY KEY,
    access_token_encrypted BLOB NOT NULL,
    refresh_token_encrypted BLOB NOT NULL,
    expires_at TEXT NOT NULL,
    scopes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _tracked_types_has_user_id(conn: sqlite3.Connection) -> bool:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(tracked_types)").fetchall()]
    return "user_id" in cols


def _get_or_create_legacy_user(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT id FROM users WHERE eve_character_id = ?", (LEGACY_USER_EVE_CHARACTER_ID,)
    ).fetchone()
    if row:
        return row[0]

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO users (eve_character_id, eve_character_name, created_at, last_login_at) "
        "VALUES (?, ?, ?, ?)",
        (LEGACY_USER_EVE_CHARACTER_ID, LEGACY_USER_NAME, now, now),
    )
    return cursor.lastrowid


def _migrate_tracked_types(conn: sqlite3.Connection) -> int:
    """Devuelve la cantidad de filas migradas. 0 si no había nada que migrar."""
    if _tracked_types_has_user_id(conn):
        return -1  # sentinel: "ya estaba migrado, no se tocó nada"

    legacy_user_id = _get_or_create_legacy_user(conn)

    old_rows = conn.execute("SELECT type_id, added_at, reason FROM tracked_types").fetchall()

    conn.execute("ALTER TABLE tracked_types RENAME TO tracked_types_old_v3")

    conn.execute("""
        CREATE TABLE tracked_types (
            user_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY (user_id, type_id),
            FOREIGN KEY (type_id) REFERENCES item_types(id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_types_user ON tracked_types(user_id)")

    conn.executemany(
        "INSERT INTO tracked_types (user_id, type_id, added_at, reason) VALUES (?, ?, ?, ?)",
        [(legacy_user_id, r[0], r[1], r[2]) for r in old_rows],
    )

    conn.execute("DROP TABLE tracked_types_old_v3")

    return len(old_rows)


def main():
    if not DB_PATH.exists():
        print(f"❌ No existe {DB_PATH}. Corré setup_database.py primero para una base nueva.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("BEGIN")
    try:
        conn.executescript(USERS_AND_TOKENS_SQL)
        migrated = _migrate_tracked_types(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("✅ Tablas 'users' y 'oauth_tokens' presentes.")
    if migrated == -1:
        print("✅ 'tracked_types' ya tenía user_id -- no se tocó nada (migración ya aplicada antes).")
    else:
        print(f"✅ {migrated} ítems trackeados migrados al usuario legacy (sin reclamar todavía).")
        print("   Van a seguir apareciendo como tuyos hasta que hagas login real con tu personaje")
        print("   de EVE y decidamos cómo reclamarlos (próximo paso, todavía no implementado).")
    print("✅ Migración completa.")


if __name__ == "__main__":
    main()
