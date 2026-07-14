"""
Migración NO destructiva: agrega las tablas nuevas de Fase 1
(sync_status, system_state) + activa WAL mode, sin tocar los datos que
ya tenés en trader.db.

setup_database.py NO sirve para esto -- borra la base entera y la
recrea de cero. Este script solo corre CREATE TABLE IF NOT EXISTS +
PRAGMA, así que es seguro correrlo sobre una base ya poblada (y seguro
correrlo más de una vez).

Uso:
    PYTHONPATH=src python scripts/migrate_v3_add_sync_tables.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "database" / "trader.db"

MIGRATION_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sync_status (
    region_id INTEGER PRIMARY KEY,
    phase TEXT NOT NULL,
    detail TEXT,
    total INTEGER,
    done INTEGER,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(id)
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def main():
    if not DB_PATH.exists():
        print(f"❌ No existe {DB_PATH}. Corré setup_database.py primero para una base nueva.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(MIGRATION_SQL)
    conn.commit()

    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sync_status','system_state')"
        ).fetchall()
    ]
    conn.close()

    print(f"✅ journal_mode = {mode}")
    print(f"✅ Tablas presentes: {tables}")
    print("✅ Migración completa. Tus datos existentes no se tocaron.")


if __name__ == "__main__":
    main()
