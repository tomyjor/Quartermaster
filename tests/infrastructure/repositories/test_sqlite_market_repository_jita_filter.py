"""
Regresión del hallazgo real: "análisis de Jita" mezclaba órdenes de
TODA la región de La Forge (region_id=10000002), no solo de Jita 4-4
(location_id=60003760) -- encontrado comparando manualmente contra el
cliente del juego (un comprador en "Kisogo VII - AIR Laboratories"
aparecía como si fuera de Jita). Ver changelog v1.4 en
`SQLiteMarketRepository`.

Estos tests prueban explícitamente que una orden en OTRA estación de la
misma región NO contamina ningún resultado, y que SÍ se cuenta cuando
corresponde a Jita 4-4.
"""

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from infrastructure.repositories.sqlite_market_repository import SQLiteMarketRepository
from _winsafe import safe_unlink

REGION_ID = 10000002  # La Forge
JITA_STATION_ID = 60003760  # Jita IV - Moon 4
OTHER_STATION_ID = 60015068  # Cualquier otra estación de La Forge, no Jita


def _make_db_with_orders(orders: list[tuple]) -> Path:
    """orders: lista de (type_id, is_buy_order, price, volume_remain, location_id)."""
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fd.close()
    db_path = Path(fd.name)

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE market_orders (
            order_id INTEGER PRIMARY KEY, region_id INTEGER, type_id INTEGER,
            is_buy_order INTEGER, price REAL, volume_remain INTEGER, volume_total INTEGER,
            min_volume INTEGER, duration INTEGER, issued TEXT, location_id INTEGER,
            order_range TEXT, fetched_at TEXT
        );
        CREATE TABLE market_history (
            region_id INTEGER, type_id INTEGER, date TEXT, average REAL,
            highest REAL, lowest REAL, volume INTEGER, order_count INTEGER
        );
    """)
    now = datetime.now(timezone.utc).isoformat()
    for i, (type_id, is_buy, price, vol_remain, loc) in enumerate(orders):
        conn.execute(
            "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
            "volume_remain, volume_total, min_volume, duration, issued, location_id, "
            "order_range, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 90, ?, ?, '', ?)",
            (i + 1, REGION_ID, type_id, is_buy, price, vol_remain, vol_remain, now, loc, now),
        )
    conn.commit()
    conn.close()
    return db_path


def test_get_current_snapshot_excludes_orders_from_other_stations_in_same_region():
    """
    Caso exacto encontrado en producción: sell en Jita 4-4, pero el
    ÚNICO buy disponible está en otra estación de la región -- antes
    esto se combinaba igual (dando un snapshot "completo" falso); ahora
    debe verse como sin book bidireccional en Jita 4-4 (snapshot None).
    """
    db_path = _make_db_with_orders([
        (34, 0, 5.0, 1000, JITA_STATION_ID),   # sell en Jita 4-4
        (34, 1, 4.5, 500, OTHER_STATION_ID),   # buy en OTRA estación
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        snapshot = repo.get_current_snapshot(34, REGION_ID)
        assert snapshot is None, "no debería armar snapshot con el buy de otra estación"
    finally:
        safe_unlink(db_path)


def test_get_current_snapshot_uses_only_jita_orders_when_both_sides_present_elsewhere_too():
    """
    Con órdenes en AMBOS lados en Jita 4-4 Y órdenes adicionales
    (mejores incluso) en otra estación, el snapshot debe reflejar SOLO
    los precios de Jita 4-4 -- una orden de compra más generosa en otro
    lado del mapa no es la que un trader en Jita puede ejecutar.
    """
    db_path = _make_db_with_orders([
        (34, 0, 5.0, 1000, JITA_STATION_ID),    # sell Jita: 5.0
        (34, 1, 4.5, 500, JITA_STATION_ID),     # buy Jita: 4.5
        (34, 1, 9.0, 999, OTHER_STATION_ID),    # buy MUY mejor, pero en otra estación
        (34, 0, 1.0, 999, OTHER_STATION_ID),    # sell MUY mejor, pero en otra estación
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        snapshot = repo.get_current_snapshot(34, REGION_ID)
        assert snapshot is not None
        assert snapshot.sell_price.amount == 5.0
        assert snapshot.buy_price.amount == 4.5
    finally:
        safe_unlink(db_path)


def test_order_counts_and_volume_remain_ignore_other_stations():
    db_path = _make_db_with_orders([
        (34, 0, 5.0, 100, JITA_STATION_ID),
        (34, 0, 5.1, 200, JITA_STATION_ID),
        (34, 0, 5.2, 999, OTHER_STATION_ID),  # no debe contar
        (34, 1, 4.5, 50, JITA_STATION_ID),
        (34, 1, 4.4, 999, OTHER_STATION_ID),  # no debe contar
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        sell_count, buy_count = repo.order_counts(34, REGION_ID)
        assert sell_count == 2, "solo las 2 ordenes de venta en Jita 4-4"
        assert buy_count == 1, "solo la 1 orden de compra en Jita 4-4"

        assert repo.total_sell_volume_remain(34, REGION_ID) == 300.0  # 100+200, no 999
        assert repo.total_buy_volume_remain(34, REGION_ID) == 50.0    # no 999
    finally:
        safe_unlink(db_path)


def test_get_active_type_ids_excludes_items_only_active_outside_jita():
    db_path = _make_db_with_orders([
        # type_id 1: book completo en Jita 4-4 -- debe aparecer
        (1, 0, 5.0, 100, JITA_STATION_ID),
        (1, 1, 4.5, 50, JITA_STATION_ID),
        # type_id 2: book completo pero SOLO en otra estación -- NO debe aparecer
        (2, 0, 5.0, 100, OTHER_STATION_ID),
        (2, 1, 4.5, 50, OTHER_STATION_ID),
        # type_id 3: sell en Jita, buy solo en otra estación -- NO debe aparecer
        (3, 0, 5.0, 100, JITA_STATION_ID),
        (3, 1, 4.5, 50, OTHER_STATION_ID),
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        active = repo.get_active_type_ids(REGION_ID)
        assert active == [1]
    finally:
        safe_unlink(db_path)


def test_get_market_snapshots_bulk_excludes_other_stations():
    db_path = _make_db_with_orders([
        (1, 0, 5.0, 100, JITA_STATION_ID),
        (1, 1, 4.5, 50, JITA_STATION_ID),
        (2, 0, 5.0, 100, OTHER_STATION_ID),
        (2, 1, 4.5, 50, OTHER_STATION_ID),
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        snapshots = repo.get_market_snapshots_bulk(REGION_ID)
        assert 1 in snapshots
        assert 2 not in snapshots, "type_id 2 solo tiene book en otra estación, no debería aparecer"
    finally:
        safe_unlink(db_path)


def test_location_id_is_overridable_for_future_flexibility():
    """
    El parámetro tiene un default (Jita 4-4) pero no está hardcodeado a
    fuego -- si algún día se quiere analizar otra estación, se puede
    sin tocar código, solo pasando `location_id` explícito.
    """
    db_path = _make_db_with_orders([
        (34, 0, 5.0, 100, OTHER_STATION_ID),
        (34, 1, 4.5, 50, OTHER_STATION_ID),
    ])
    try:
        repo = SQLiteMarketRepository(db_path=db_path)
        # Con el default (Jita), no debería encontrar nada.
        assert repo.get_current_snapshot(34, REGION_ID) is None
        # Pidiendo explícitamente la otra estación, sí.
        snapshot = repo.get_current_snapshot(34, REGION_ID, location_id=OTHER_STATION_ID)
        assert snapshot is not None
    finally:
        safe_unlink(db_path)
