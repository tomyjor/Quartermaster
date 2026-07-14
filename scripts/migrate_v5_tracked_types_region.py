"""
Migración NO destructiva: agrega `region_id` a la clave de
`tracked_types`.

Antes de esto, un ítem trackeado (user_id, type_id) no decía a qué hub
pertenecía -- pero un mismo type_id (ej. "Tritanium") se comercia en
TODOS los hubs simultáneamente con precios distintos. Trackearlo sin
especificar hub era ambiguo: ¿el usuario quería seguir el precio en
Jita, en Amarr, o en los cinco a la vez?

Todo lo que ya estaba trackeado se asume Jita (el único hub que existía
antes de la modularización) -- no se pierde nada, cada fila existente
gana `region_id=10000002` explícito.

Uso:
    python scripts/migrate_v5_tracked_types_region.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "database" / "trader.db"
JITA_REGION_ID = 10000002


def _tracked_types_has_region_id(conn: sqlite3.Connection) -> bool:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(tracked_types)").fetchall()]
    return "region_id" in cols


def _migrate(conn: sqlite3.Connection) -> int:
    """Devuelve la cantidad de filas migradas. -1 si ya estaba migrado (sentinel, como en v4)."""
    if _tracked_types_has_region_id(conn):
        return -1

    old_rows = conn.execute("SELECT user_id, type_id, added_at, reason FROM tracked_types").fetchall()

    conn.execute("ALTER TABLE tracked_types RENAME TO tracked_types_old_v4")

    conn.execute("""
        CREATE TABLE tracked_types (
            user_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            region_id INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY (user_id, type_id, region_id),
            FOREIGN KEY (type_id) REFERENCES item_types(id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_types_user ON tracked_types(user_id)")

    conn.executemany(
        "INSERT INTO tracked_types (user_id, type_id, region_id, added_at, reason) VALUES (?, ?, ?, ?, ?)",
        [(r[0], r[1], JITA_REGION_ID, r[2], r[3]) for r in old_rows],
    )

    conn.execute("DROP TABLE tracked_types_old_v4")

    return len(old_rows)


def main():
    if not DB_PATH.exists():
        print(f"❌ No existe {DB_PATH}. Corré setup_database.py primero para una base nueva.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("BEGIN")
    try:
        migrated = _migrate(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if migrated == -1:
        print("✅ 'tracked_types' ya tenía region_id -- no se tocó nada (migración ya aplicada antes).")
    else:
        print(f"✅ {migrated} ítems trackeados migrados, todos asignados a Jita (region_id={JITA_REGION_ID}).")
        print("   Es el único hub que existía antes de la modularización -- nada se perdió.")
    print("✅ Migración completa.")


if __name__ == "__main__":
    main()
