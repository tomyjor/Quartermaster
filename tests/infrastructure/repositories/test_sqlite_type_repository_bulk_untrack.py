"""
Tests para SQLiteTypeRepository.untrack_all / untrack_many.

Regresión del bug "borra de a tandas": la versión anterior de "eliminar
todos" llamaba a untrack() en un loop Python (una conexión SQLite nueva
por ítem). Con watchlists grandes eso era lo bastante lento como para
que un click de más -- mientras el loop seguía corriendo -- interrumpiera
el proceso a la mitad (Streamlit cancela el script en curso ante una
nueva interacción). untrack_all / untrack_many hacen la eliminación
completa en UNA sola sentencia SQL, sin loop que se pueda cortar a la
mitad.

v2 (multi-tenancy): todos los métodos ahora requieren `user_id` --
cada watchlist tiene dueño. También se sacó por completo el flag
`also_cleanup_orders` que tenían `untrack`/`untrack_many`/`untrack_all`:
borraba `market_orders`, que desde el Smart Auto-Seed es un recurso
COMPARTIDO por todos los usuarios (alimenta Discovery para todo el
mundo) -- destrackear un ítem ya no debe borrarle datos de mercado a
nadie más. Ver test `test_untrack_does_not_touch_shared_market_orders`.
"""

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from infrastructure.repositories.sqlite_type_repository import SQLiteTypeRepository, JITA_REGION_ID
from _winsafe import safe_unlink

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"
TEST_USER_ID = 1
OTHER_USER_ID = 2


def _make_temp_db_with_tracked_items(n: int, user_id: int = TEST_USER_ID) -> Path:
    """Crea una DB temporal con el schema real, un usuario de prueba, y n ítems trackeados por ese usuario."""
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')",
        (JITA_REGION_ID,),
    )
    conn.execute(
        "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, user_id * 1000, f"Test Pilot {user_id}", now, now),
    )
    for i in range(1, n + 1):
        conn.execute(
            "INSERT INTO item_types (id, name, published) VALUES (?, ?, 1)",
            (i, f"Test Item {i}"),
        )
        conn.execute(
            "INSERT INTO tracked_types (user_id, type_id, region_id, added_at, reason) VALUES (?, ?, ?, ?, ?)",
            (user_id, i, JITA_REGION_ID, now, "test"),
        )
        # Un par de órdenes por ítem -- para confirmar que ya NO se tocan al destrackear (dato compartido).
        conn.execute(
            "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
            "volume_remain, volume_total, min_volume, duration, issued, location_id, "
            "order_range, fetched_at) VALUES (?, ?, ?, 0, 100.0, 5, 5, 1, 90, ?, 60003760, '', ?)",
            (i * 1000, JITA_REGION_ID, i, now, now),
        )
    conn.commit()
    conn.close()
    return tmp_path


def test_untrack_many_deletes_exactly_the_given_ids_in_one_statement():
    db_path = _make_temp_db_with_tracked_items(10)
    try:
        repo = SQLiteTypeRepository(db_path=db_path)
        to_remove = [1, 2, 3]

        deleted = repo.untrack_many(TEST_USER_ID, to_remove, JITA_REGION_ID)

        assert deleted == 3
        remaining = repo.tracked_type_ids(TEST_USER_ID, JITA_REGION_ID)
        assert sorted(remaining) == [4, 5, 6, 7, 8, 9, 10]
    finally:
        safe_unlink(db_path)


def test_untrack_all_removes_everything_regardless_of_watchlist_size():
    db_path = _make_temp_db_with_tracked_items(50)
    try:
        repo = SQLiteTypeRepository(db_path=db_path)

        deleted = repo.untrack_all(TEST_USER_ID, JITA_REGION_ID)

        assert deleted == 50
        assert repo.tracked_type_ids(TEST_USER_ID, JITA_REGION_ID) == []
    finally:
        safe_unlink(db_path)


def test_untrack_many_empty_list_is_a_safe_noop():
    db_path = _make_temp_db_with_tracked_items(3)
    try:
        repo = SQLiteTypeRepository(db_path=db_path)
        deleted = repo.untrack_many(TEST_USER_ID, [], JITA_REGION_ID)
        assert deleted == 0
        assert len(repo.tracked_type_ids(TEST_USER_ID, JITA_REGION_ID)) == 3
    finally:
        safe_unlink(db_path)


def test_untrack_does_not_touch_shared_market_orders():
    """
    Regresión real, encontrada revisando el código al agregar
    multi-tenancy: `untrack`/`untrack_many`/`untrack_all` antes tenían
    un flag `also_cleanup_orders=True` por default que borraba
    `market_orders` del ítem destrackeado. Desde el Smart Auto-Seed,
    `market_orders` es COMPARTIDO por todos los usuarios (alimenta
    Discovery para todo el mundo) -- si el Usuario A destrackea un
    ítem, NO debe desaparecerle los datos de mercado al Usuario B que
    todavía lo está mirando. El comportamiento se sacó por completo.
    """
    db_path = _make_temp_db_with_tracked_items(5)
    try:
        repo = SQLiteTypeRepository(db_path=db_path)

        repo.untrack_all(TEST_USER_ID, JITA_REGION_ID)

        conn = sqlite3.connect(db_path)
        remaining_orders = conn.execute(
            "SELECT COUNT(*) FROM market_orders WHERE region_id = ?", (JITA_REGION_ID,)
        ).fetchone()[0]
        conn.close()
        assert remaining_orders == 5, (
            "destrackear no debería borrar market_orders -- es un recurso compartido "
            "entre todos los usuarios, no propiedad de quien lo trackeó"
        )
    finally:
        safe_unlink(db_path)


def test_untrack_only_affects_the_given_user_not_others():
    """Dos usuarios trackeando el MISMO ítem -- uno lo destrackea, el otro lo sigue teniendo."""
    db_path = _make_temp_db_with_tracked_items(3, user_id=TEST_USER_ID)
    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (OTHER_USER_ID, OTHER_USER_ID * 1000, "Other Pilot", now, now),
        )
        conn.execute(
            "INSERT INTO tracked_types (user_id, type_id, region_id, added_at, reason) VALUES (?, ?, ?, ?, ?)",
            (OTHER_USER_ID, 1, JITA_REGION_ID, now, "test"),
        )
        conn.commit()
        conn.close()

        repo = SQLiteTypeRepository(db_path=db_path)
        repo.untrack(TEST_USER_ID, 1, JITA_REGION_ID)

        assert 1 not in repo.tracked_type_ids(TEST_USER_ID, JITA_REGION_ID)
        assert 1 in repo.tracked_type_ids(OTHER_USER_ID, JITA_REGION_ID), (
            "el otro usuario no debería perder su propio tracking del mismo ítem"
        )
    finally:
        safe_unlink(db_path)
