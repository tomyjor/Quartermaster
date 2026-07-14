"""
Tests para ApiServices (capa de servicios de la API, sin FastAPI).

Usa una DB temporal con datos de fixture (no la real) para no depender
del estado de trader.db. Cubre discovery vs. tracked scope, sort_by,
tracking/untracking, y el estado de sync.
"""

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from presentation.api.services import ApiServices
from _winsafe import safe_unlink

REGION_ID = 10000002
TEST_USER_ID = 1
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


def _make_temp_db_with_fixture() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())

    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')", (REGION_ID,))
    conn.execute(
        "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
        "VALUES (?, 999999, 'Test Pilot', ?, ?)",
        (TEST_USER_ID, now, now),
    )

    items = [
        (1, "Test Item A"), (2, "Test Item B"), (3, "Test Item C"),
    ]
    for type_id, name in items:
        conn.execute(
            "INSERT INTO item_types (id, name, published) VALUES (?, ?, 1)", (type_id, name)
        )
        # Order book bidireccional con varias órdenes de cada lado, para
        # que el gate de thin-order-book no interfiera en estos tests.
        for i in range(3):
            conn.execute(
                "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
                "volume_remain, volume_total, min_volume, duration, issued, location_id, "
                "order_range, fetched_at) VALUES (?, ?, ?, 0, ?, 100, 100, 1, 90, ?, 60003760, '', ?)",
                (type_id * 100 + i, REGION_ID, type_id, 10.0 + type_id, now, now),
            )
            conn.execute(
                "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
                "volume_remain, volume_total, min_volume, duration, issued, location_id, "
                "order_range, fetched_at) VALUES (?, ?, ?, 1, ?, 100, 100, 1, 90, ?, 60003760, '', ?)",
                (type_id * 1000 + i, REGION_ID, type_id, 5.0, now, now),
            )
        conn.execute(
            "INSERT INTO market_history (region_id, type_id, date, average, highest, lowest, "
            "volume, order_count) VALUES (?, ?, '2026-07-01', 7.0, 10.0, 5.0, 5000, 6)",
            (REGION_ID, type_id),
        )

    # Solo el item 1 está trackeado a mano, por TEST_USER_ID.
    conn.execute(
        "INSERT INTO tracked_types (user_id, type_id, region_id, added_at, reason) VALUES (?, 1, ?, ?, 'test')",
        (TEST_USER_ID, REGION_ID, now),
    )

    conn.commit()
    conn.close()
    return tmp_path


def test_discovery_scope_includes_untracked_items_with_active_orders():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        page = svc.list_opportunities(scope="discovery", min_score=0, max_results=10)

        # Los 3 items tienen order book activo, aunque solo el 1 está trackeado.
        assert page.total_evaluated == 3
        assert {o.instrument_id for o, _ in page.opportunities} == {1, 2, 3}
    finally:
        safe_unlink(db_path)


def test_tracked_scope_only_includes_watchlist():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        page = svc.list_opportunities(scope="tracked", min_score=0, max_results=10, user_id=TEST_USER_ID)

        assert page.total_evaluated == 1
        assert [o.instrument_id for o, _ in page.opportunities] == [1]
    finally:
        safe_unlink(db_path)


def test_invalid_scope_raises_clear_error():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        try:
            svc.list_opportunities(scope="everything", min_score=0, max_results=10)
            assert False, "debería haber lanzado ValueError"
        except ValueError as e:
            assert "scope" in str(e)
    finally:
        safe_unlink(db_path)


def test_track_and_untrack_roundtrip():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        assert svc.list_tracked_type_ids(TEST_USER_ID) == [1]

        svc.track_item(TEST_USER_ID, 2, reason="test manual")
        assert set(svc.list_tracked_type_ids(TEST_USER_ID)) == {1, 2}

        svc.untrack_item(TEST_USER_ID, 1)
        assert svc.list_tracked_type_ids(TEST_USER_ID) == [2]

        svc.track_item(TEST_USER_ID, 1)
        deleted = svc.untrack_all_items(TEST_USER_ID)
        assert deleted == 2
        assert svc.list_tracked_type_ids(TEST_USER_ID) == []
    finally:
        safe_unlink(db_path)


def test_list_tracked_items_resolves_names():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        items = svc.list_tracked_items(TEST_USER_ID)

        assert items == [{"type_id": 1, "name": "Test Item A"}]
    finally:
        safe_unlink(db_path)


def test_get_opportunity_detail_returns_full_breakdown():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        detail = svc.get_opportunity_detail(1)

        assert detail is not None
        opportunity, confidence = detail
        assert opportunity.instrument_id == 1
        assert "components" in opportunity.score_breakdown
        assert 0 <= confidence <= 100
    finally:
        safe_unlink(db_path)


def test_exclude_caution_removes_caution_items_without_changing_scores():
    """
    Regresión de un caso real: ítems tipo SKIN con ROI de troll orders
    (1 sola orden, ROI en los millones de %) sacaban score alto pero
    estaban correctamente marcados caution_thin_order_book -- ensuciaban
    el top-N por score aunque el warning funcionara bien.
    exclude_caution=True debe sacarlos del ranking SIN tocar el score
    de los que quedan (es un filtro aparte, no una penalización mezclada
    en la matemática).
    """
    db_path = _make_temp_db_with_fixture()
    try:
        # Ítem 2 con order book fino a propósito (1 sola orden de venta)
        # para que caiga en CAUTION_THIN_ORDER_BOOK.
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM market_orders WHERE type_id = 2 AND is_buy_order = 0")
        conn.execute(
            "INSERT INTO market_orders (order_id, region_id, type_id, is_buy_order, price, "
            "volume_remain, volume_total, min_volume, duration, issued, location_id, "
            "order_range, fetched_at) VALUES (99999, ?, 2, 0, 10000, 1, 1, 1, 90, ?, 60003760, '', ?)",
            (REGION_ID, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

        svc = ApiServices(db_path=db_path, region_id=REGION_ID)

        unfiltered = svc.list_opportunities(scope="discovery", min_score=0, max_results=10)
        assert any(o.recommendation.is_caution for o, _ in unfiltered.opportunities), (
            "el fixture debería producir al menos un caution_* -- si no, el test no prueba nada"
        )

        filtered = svc.list_opportunities(scope="discovery", min_score=0, max_results=10, exclude_caution=True)
        assert not any(o.recommendation.is_caution for o, _ in filtered.opportunities)

        # Los que sobreviven al filtro deben tener EXACTAMENTE el mismo
        # score que sin filtrar -- el filtro no debe tocar la matemática.
        unfiltered_scores = {o.instrument_id: o.score for o, _ in unfiltered.opportunities}
        for o, _ in filtered.opportunities:
            assert o.score == unfiltered_scores[o.instrument_id]
    finally:
        safe_unlink(db_path)


def test_sort_by_alternate_field_does_not_truncate_before_reordering():
    """
    Regresión de un bug encontrado al implementar exclude_caution: antes,
    list_opportunities le pedía al use case `max_results * 3` como
    margen para poder reordenar por un campo distinto a score sin perder
    ítems del borde -- un parche heurístico, no una garantía. Ahora se
    reordena sobre el pool COMPLETO de evaluados, así que pedir
    max_results=1 pero ordenar por 'roi' debe devolver el de MAYOR roi
    de TODO el pool, no el de mayor roi entre los primeros 3.
    """
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        by_score = svc.list_opportunities(scope="discovery", min_score=0, max_results=10, sort_by="score")
        by_roi = svc.list_opportunities(scope="discovery", min_score=0, max_results=1, sort_by="roi")

        best_roi_overall = max(o.roi_percent for o, _ in by_score.opportunities)
        assert by_roi.opportunities[0][0].roi_percent == best_roi_overall
    finally:
        safe_unlink(db_path)


def test_get_opportunity_detail_returns_none_for_unknown_item():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        assert svc.get_opportunity_detail(9999) is None
    finally:
        safe_unlink(db_path)


def test_sync_status_reflects_never_seeded_state():
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        assert svc.needs_initial_seed() is True
        assert svc.get_sync_status() is None
    finally:
        safe_unlink(db_path)


def test_tracked_scope_without_user_id_raises_clear_error():
    """
    Regresión de multi-tenancy: antes de agregar usuarios, scope="tracked"
    tenía un usuario implícito único. Ahora una watchlist sin dueño no
    es un concepto válido -- pedirla sin user_id debe fallar claro, no
    devolver una lista vacía silenciosa ni explotar con un error críptico.
    """
    db_path = _make_temp_db_with_fixture()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        try:
            svc.list_opportunities(scope="tracked", min_score=0, max_results=10)
            assert False, "debería exigir user_id para scope='tracked'"
        except ValueError as e:
            assert "user_id" in str(e)
    finally:
        safe_unlink(db_path)


def test_two_users_have_independent_watchlists():
    """
    Prueba directa de aislamiento multi-tenant: el Usuario A trackea
    un ítem, el Usuario B no lo ve en su propia watchlist -- ni tracking
    ni untracking de uno afecta al otro.
    """
    db_path = _make_temp_db_with_fixture()
    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO users (id, eve_character_id, eve_character_name, created_at, last_login_at) "
            "VALUES (2, 888888, 'Other Pilot', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()

        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        USER_A, USER_B = TEST_USER_ID, 2

        svc.track_item(USER_B, 3, reason="usuario B")

        assert svc.list_tracked_type_ids(USER_A) == [1]
        assert svc.list_tracked_type_ids(USER_B) == [3]

        svc.untrack_all_items(USER_A)
        assert svc.list_tracked_type_ids(USER_A) == []
        assert svc.list_tracked_type_ids(USER_B) == [3], "destrackear todo del usuario A no debe afectar al B"
    finally:
        safe_unlink(db_path)
