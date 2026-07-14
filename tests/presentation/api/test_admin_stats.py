"""Test para ApiServices.get_admin_stats -- panorama básico del sistema."""

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from presentation.api.services import ApiServices
from _winsafe import safe_unlink

REGION_ID = 10000002
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


def _make_db_with_users_and_tracking() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute("INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')", (REGION_ID,))

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
        "VALUES (1, 100, 'Pilot A', ?, ?)", (now, now),
    )
    conn.execute(
        "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
        "VALUES (2, 200, 'Pilot B', ?, ?)", (now, now),
    )
    conn.execute("INSERT INTO item_types (id, name, published) VALUES (34, 'Test Item', 1)")
    conn.execute(
        "INSERT INTO tracked_types (user_id, type_id, region_id, added_at, reason) VALUES (1, 34, ?, ?, 'test')",
        (REGION_ID, now),
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_admin_stats_reflects_real_counts():
    db_path = _make_db_with_users_and_tracking()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        stats = svc.get_admin_stats()

        assert stats["total_users"] == 2
        assert stats["users_with_watchlist"] == 1  # solo Pilot A trackeó algo
        assert stats["total_tracked_items"] == 1
        assert len(stats["recent_logins"]) == 2
    finally:
        safe_unlink(db_path)


def test_admin_stats_on_empty_system_does_not_crash():
    db_path = Path(tempfile.mkstemp(suffix=".db")[1])
    try:
        conn = sqlite3.connect(db_path)
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
        conn.close()

        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        stats = svc.get_admin_stats()

        assert stats["total_users"] == 0
        assert stats["users_with_watchlist"] == 0
        assert stats["total_tracked_items"] == 0
        assert stats["recent_logins"] == []
    finally:
        safe_unlink(db_path)
