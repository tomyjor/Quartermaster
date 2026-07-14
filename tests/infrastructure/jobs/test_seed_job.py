"""
Tests para SmartAutoSeedJob (Fase 1: sync completo de región).

Usa clientes ESI falsos (sin red real) para verificar la orquestación
completa: fetch de toda la región sin filtrar por type_id, historial
acotado solo a los type_ids que resultaron con actividad real, y que
sync_status/system_state queden escritos correctamente en cada fase.
"""

import sqlite3
import tempfile
from pathlib import Path

import infrastructure.jobs.seed_job as seed_job_mod
from infrastructure.jobs.seed_job import SmartAutoSeedJob
from infrastructure.jobs.sync_status_repository import SyncStatusRepository
from _winsafe import safe_unlink

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"
REGION_ID = 10000002


def _make_temp_db() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute("INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')", (REGION_ID,))
    conn.commit()
    conn.close()
    return tmp_path


class _FakeOrdersClient:
    def __init__(self, orders, pages=1):
        self.orders = orders
        self.pages = pages
        self.calls = []

    def get(self, endpoint, params=None, on_page=None):
        self.calls.append((endpoint, params))
        if on_page:
            # Simula reportar progreso página por página, como hace
            # ESIClient.get() de verdad -- ver test que confirma que
            # sync_status se actualiza EN CADA página, no solo al final
            # (regresión del bug de "status congelado" visto en la
            # corrida real del usuario).
            chunk_size = max(1, len(self.orders) // self.pages)
            for i in range(self.pages):
                items_so_far = min((i + 1) * chunk_size, len(self.orders))
                on_page(i + 1, self.pages, items_so_far)
        return self.orders

    def close(self):
        pass


class _FakeHistoryClient:
    def __init__(self, history=None, fail_for=None):
        self.history = history or [
            {"date": "2026-07-01", "average": 5.0, "highest": 6.0, "lowest": 4.0,
             "volume": 1000, "order_count": 5}
        ]
        self.fail_for = fail_for or set()

    def get(self, endpoint, params=None):
        type_id = (params or {}).get("type_id")
        if type_id in self.fail_for:
            raise RuntimeError(f"fallo simulado para type_id {type_id}")
        return self.history

    def close(self):
        pass


def _patch_importers(monkeypatch_orders_client, monkeypatch_history_client):
    """Reemplaza los importadores por versiones que usan clientes fake, sin tocar ESI real."""
    orig_orders_importer = seed_job_mod.MarketOrdersImporter
    orig_history_importer = seed_job_mod.MarketHistoryImporter

    class PatchedOrdersImporter(orig_orders_importer):
        def __init__(self, db_path):
            super().__init__(db_path)
            self.client = monkeypatch_orders_client

    class PatchedHistoryImporter(orig_history_importer):
        def __init__(self, db_path):
            super().__init__(db_path)
            self.client = monkeypatch_history_client

    seed_job_mod.MarketOrdersImporter = PatchedOrdersImporter
    seed_job_mod.MarketHistoryImporter = PatchedHistoryImporter
    return orig_orders_importer, orig_history_importer


def _restore_importers(orig_orders_importer, orig_history_importer):
    seed_job_mod.MarketOrdersImporter = orig_orders_importer
    seed_job_mod.MarketHistoryImporter = orig_history_importer


def test_seed_job_fetches_full_region_without_type_id_filter():
    db_path = _make_temp_db()
    orig = _patch_importers(
        _FakeOrdersClient([
            {"order_id": i, "type_id": 100 + (i % 3), "is_buy_order": i % 2 == 0, "price": 5.0 + i,
             "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
             "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"}
            for i in range(1, 10)
        ]),
        _FakeHistoryClient(),
    )
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)

        result = job.run()

        assert result.order_count == 9
        assert result.active_type_id_count == 3  # type_ids 100, 101, 102
        assert result.history_success == 3
        assert result.history_failed == 0
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)


def test_seed_job_scopes_history_to_active_type_ids_only():
    """El historial NUNCA debe pedirse para más type_ids que los que
    resultaron con orden activa en el paso 1 -- ver changelog del módulo."""
    db_path = _make_temp_db()
    fake_orders_client = _FakeOrdersClient([
        {"order_id": 1, "type_id": 34, "is_buy_order": False, "price": 5.0,
         "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
         "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"},
    ])
    fake_history_client = _FakeHistoryClient()
    orig = _patch_importers(fake_orders_client, fake_history_client)
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)

        result = job.run()

        assert result.active_type_id_count == 1
        assert result.history_success == 1
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)


def test_seed_job_marks_sync_status_completed_and_records_last_seed_time():
    db_path = _make_temp_db()
    orig = _patch_importers(
        _FakeOrdersClient([
            {"order_id": 1, "type_id": 34, "is_buy_order": False, "price": 5.0,
             "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
             "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"},
        ]),
        _FakeHistoryClient(),
    )
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        assert status_repo.needs_initial_seed() is True

        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)
        job.run()

        final_status = status_repo.get_status(REGION_ID)
        assert final_status["phase"] == "completed"
        assert status_repo.needs_initial_seed() is False
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)


def test_seed_job_records_a_jita_specific_snapshot():
    """
    Regresión de un hallazgo real: `market_order_snapshots` existía en
    el schema desde hace tiempo pero nadie escribía ahí -- 0 filas en
    producción. Es la base para medir turnover ESPECÍFICO de Jita
    (a diferencia de `daily_volume`, que es regional). Confirma que
    cada corrida del seed deja al menos una fila.
    """
    db_path = _make_temp_db()
    orig = _patch_importers(
        _FakeOrdersClient([
            {"order_id": 1, "type_id": 34, "is_buy_order": False, "price": 5.0,
             "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
             "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"},
        ]),
        _FakeHistoryClient(),
    )
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)
        job.run()

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT type_id, total_volume_remain FROM market_order_snapshots").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0] == (34, 100)
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)


def test_seed_job_partial_history_failures_do_not_abort_the_whole_run():
    db_path = _make_temp_db()
    orig = _patch_importers(
        _FakeOrdersClient([
            {"order_id": 1, "type_id": 34, "is_buy_order": False, "price": 5.0,
             "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
             "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"},
            {"order_id": 2, "type_id": 35, "is_buy_order": False, "price": 5.0,
             "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
             "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"},
        ]),
        _FakeHistoryClient(fail_for={35}),
    )
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)

        result = job.run()

        assert result.history_success == 1
        assert result.history_failed == 1
        # El job completa igual, no aborta por un fallo parcial de historial.
        assert status_repo.get_status(REGION_ID)["phase"] == "completed"
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)


def test_seed_job_reports_incremental_progress_during_orders_pagination():
    """
    Regresión del bug visto en la corrida real: `sync_status` quedaba
    "congelado" (mismo `updated_at`) durante TODO el fetch del order
    book completo, sin forma de distinguir "sigue paginando" de "se
    colgó". Ahora debe actualizarse en CADA página, con `total`/`done`
    reflejando el progreso real.
    """
    db_path = _make_temp_db()
    # 5 páginas simuladas -- suficiente para ver varios updates intermedios.
    fake_orders_client = _FakeOrdersClient(
        [{"order_id": i, "type_id": 34, "is_buy_order": False, "price": 5.0,
          "volume_remain": 100, "volume_total": 100, "min_volume": 1, "duration": 90,
          "issued": "2026-07-01T00:00:00Z", "location_id": 60003760, "range": "region"}
         for i in range(1, 11)],
        pages=5,
    )
    orig = _patch_importers(fake_orders_client, _FakeHistoryClient())
    try:
        status_repo = SyncStatusRepository(db_path=db_path)
        seen_statuses = []

        # Envolvemos set_status para capturar cada actualización intermedia,
        # no solo el estado final.
        original_set_status = status_repo.set_status

        def spy_set_status(*args, **kwargs):
            original_set_status(*args, **kwargs)
            seen_statuses.append(status_repo.get_status(REGION_ID).copy())

        status_repo.set_status = spy_set_status

        job = SmartAutoSeedJob(db_path=db_path, region_id=REGION_ID, status_repo=status_repo)
        job.run()

        orders_phase_updates = [s for s in seen_statuses if s["phase"] == "orders"]
        # Debe haber más de UNA actualización durante "orders" (arranque +
        # al menos una página) -- si solo hubiera 1, volvimos al bug viejo.
        assert len(orders_phase_updates) >= 2, (
            f"Solo {len(orders_phase_updates)} actualización(es) durante 'orders' -- "
            "el status se está quedando congelado de nuevo."
        )
        # Y el progreso reportado debe ser creciente, no el mismo valor repetido.
        done_values = [s["done"] for s in orders_phase_updates if s["done"] is not None]
        assert len(set(done_values)) > 1, "El progreso ('done') no varía entre actualizaciones."
    finally:
        _restore_importers(*orig)
        safe_unlink(db_path)
