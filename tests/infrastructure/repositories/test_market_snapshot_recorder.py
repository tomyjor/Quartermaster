"""
Tests para MarketSnapshotRecorder -- registrar y consultar el estado
del order book de Jita en el tiempo, para derivar un proxy de
turnover específico de Jita (no regional como market_history).
"""

import sqlite3
import tempfile
from pathlib import Path
from datetime import date, timedelta

from infrastructure.repositories.market_snapshot_recorder import MarketSnapshotRecorder, JITA_STATION_ID
from _winsafe import safe_unlink

REGION_ID = 10000002
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


def _make_db_with_orders(volume_remain: int = 1000, station_id: int = JITA_STATION_ID) -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute("INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')", (REGION_ID,))
    conn.execute("INSERT INTO item_types (id, name, published) VALUES (34, 'Test Item', 1)")

    now = "2026-07-13T00:00:00+00:00"
    conn.execute(
        "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
        "volume_remain, volume_total, min_volume, duration, issued, location_id, "
        "order_range, fetched_at) VALUES (1, ?, 34, 1, 10.0, ?, ?, 1, 90, ?, ?, '', ?)",
        (REGION_ID, volume_remain, volume_remain, now, station_id, now),
    )
    conn.execute(
        "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
        "volume_remain, volume_total, min_volume, duration, issued, location_id, "
        "order_range, fetched_at) VALUES (2, ?, 34, 0, 12.0, ?, ?, 1, 90, ?, ?, '', ?)",
        (REGION_ID, volume_remain, volume_remain, now, station_id, now),
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_record_snapshot_captures_jita_orders_only():
    """Órdenes de OTRA estación en la misma región no deben aparecer en el snapshot."""
    db_path = _make_db_with_orders(station_id=99999999)  # estación distinta a Jita
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        count = recorder.record_snapshot(region_id=REGION_ID, snapshot_date="2026-07-13")
        assert count == 0, "no debería capturar órdenes de otra estación"
    finally:
        safe_unlink(db_path)


def test_record_snapshot_captures_real_jita_orders():
    db_path = _make_db_with_orders(station_id=JITA_STATION_ID)
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        count = recorder.record_snapshot(region_id=REGION_ID, snapshot_date="2026-07-13")

        assert count == 1  # un solo type_id (34)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT buy_order_count, sell_order_count, total_volume_remain "
            "FROM market_order_snapshots WHERE type_id = 34"
        ).fetchone()
        conn.close()
        assert row == (1, 1, 2000)  # 1000 buy + 1000 sell
    finally:
        safe_unlink(db_path)


def test_recording_same_day_twice_does_not_duplicate():
    db_path = _make_db_with_orders()
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date="2026-07-13")
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date="2026-07-13")

        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM market_order_snapshots").fetchone()[0]
        conn.close()
        assert total == 1
    finally:
        safe_unlink(db_path)


def test_turnover_proxy_is_none_with_a_single_snapshot():
    db_path = _make_db_with_orders()
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=date.today().isoformat())

        proxy = recorder.get_jita_turnover_proxy(region_id=REGION_ID, type_id=34)
        assert proxy is None
    finally:
        safe_unlink(db_path)


def test_turnover_proxy_reflects_real_volume_decrease():
    db_path = _make_db_with_orders(volume_remain=1000)
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        old_date = (date.today() - timedelta(days=3)).isoformat()
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=old_date)

        # Simulamos que se vendio/compro la mitad del book (volume_remain bajo)
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE market_orders SET volume_remain = 500 WHERE order_id IN (1, 2)")
        conn.commit()
        conn.close()

        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=date.today().isoformat())

        proxy = recorder.get_jita_turnover_proxy(region_id=REGION_ID, type_id=34)
        assert proxy == 1000.0  # 2000 -> 1000, delta de 1000
    finally:
        safe_unlink(db_path)


def test_turnover_proxy_never_negative_when_book_grows():
    db_path = _make_db_with_orders(volume_remain=1000)
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        old_date = (date.today() - timedelta(days=3)).isoformat()
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=old_date)

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE market_orders SET volume_remain = 5000 WHERE order_id IN (1, 2)")
        conn.commit()
        conn.close()

        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=date.today().isoformat())

        proxy = recorder.get_jita_turnover_proxy(region_id=REGION_ID, type_id=34)
        assert proxy == 0.0, "un book que crece no debe dar un delta negativo"
    finally:
        safe_unlink(db_path)


def test_turnover_proxy_ignores_snapshots_outside_lookback_window():
    db_path = _make_db_with_orders(volume_remain=1000)
    try:
        recorder = MarketSnapshotRecorder(db_path=db_path)
        far_past = (date.today() - timedelta(days=30)).isoformat()
        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=far_past)

        recorder.record_snapshot(region_id=REGION_ID, snapshot_date=date.today().isoformat())

        proxy = recorder.get_jita_turnover_proxy(region_id=REGION_ID, type_id=34, lookback_days=7)
        assert proxy is None, "un snapshot de hace 30 dias no deberia contar dentro de una ventana de 7"
    finally:
        safe_unlink(db_path)
