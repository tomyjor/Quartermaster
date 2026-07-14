"""
Infrastructure/Jobs: SmartAutoSeedJob

Bootstrap automático (primera ejecución, o refresh manual completo):

1. Sync COMPLETO del order book de la región en una sola pasada
   (`MarketOrdersImporter.import_full_region`, sin muestreo, sin
   depender de qué esté trackeado a mano).
2. Historial de volumen SOLO para los type_ids que el paso 1 reveló con
   orden activa -- nunca para el catálogo `published=1` completo (que
   puede ser de decenas de miles de ítems, la gran mayoría sin ninguna
   actividad real en Jita). Este scoping natural es gratis: sale
   directo del resultado del paso 1, no hay que adivinar ni samplear.

Ver docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §5 para el diseño
completo. Esta clase es pura orquestación -- no decide reglas de
negocio, solo coordina los importadores existentes y reporta progreso
vía SyncStatusRepository para que la API pueda exponerlo sin bloquear.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from infrastructure.esi.market_orders_importer import MarketOrdersImporter
from infrastructure.esi.market_history_importer import MarketHistoryImporter
from infrastructure.jobs.sync_status_repository import SyncStatusRepository
from infrastructure.repositories.market_snapshot_recorder import MarketSnapshotRecorder
from shared.paths import DEFAULT_DB_PATH

JITA_REGION_ID = 10000002
JITA_STATION_ID = 60003760


@dataclass(frozen=True)
class SeedResult:
    order_count: int
    active_type_id_count: int
    history_success: int
    history_failed: int


class SmartAutoSeedJob:
    """
    Orquesta el bootstrap completo. Se puede correr:
    - Automáticamente al arrancar la API si `SyncStatusRepository.needs_initial_seed()`
      es True (primera vez).
    - Manualmente desde un endpoint (`POST /api/sync/seed`) para forzar
      un refresh completo.
    """

    #: Concurrencia para el import de historial (1 request por type_id,
    #: no hay forma de evitarlo -- ver changelog de MarketOrdersImporter).
    HISTORY_WORKERS = 6

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        region_id: int = JITA_REGION_ID,
        station_id: int = JITA_STATION_ID,
        status_repo: Optional[SyncStatusRepository] = None,
    ):
        self.db_path = db_path
        self.region_id = region_id
        #: v2 (modularización multi-hub): usado solo para el snapshot
        #: de MarketSnapshotRecorder -- el import de órdenes en sí
        #: (`MarketOrdersImporter.import_full_region`) trae TODA la
        #: región desde ESI (ESI no permite filtrar por estación en el
        #: fetch), el filtrado por estación pasa a la hora de LEER, no
        #: de importar. Ver docstring de `run()`.
        self.station_id = station_id
        self.status_repo = status_repo or SyncStatusRepository(db_path=db_path)

    def run(self) -> SeedResult:
        self.status_repo.set_status(
            region_id=self.region_id,
            phase="orders",
            detail="Importando order book completo de la región...",
            reset_started_at=True,
        )

        orders_importer = MarketOrdersImporter(db_path=str(self.db_path))

        def on_orders_page(page: int, total_pages: int, orders_so_far: int) -> None:
            self.status_repo.set_status(
                region_id=self.region_id,
                phase="orders",
                detail=f"Página {page}/{total_pages} ({orders_so_far} órdenes traídas hasta ahora)",
                total=total_pages,
                done=page,
            )

        try:
            orders_result = orders_importer.import_full_region(self.region_id, progress_callback=on_orders_page)
        except Exception as e:
            self.status_repo.mark_error(self.region_id, str(e))
            raise
        finally:
            orders_importer.close()

        active_type_ids = sorted(orders_result["distinct_type_ids"])

        # Un snapshot de Jita por corrida -- ver docstring de
        # MarketSnapshotRecorder: es la base para medir turnover
        # ESPECÍFICO de Jita en el tiempo, a diferencia de
        # `daily_volume` (regional, limitación real de ESI). No bloquea
        # el resto del seed si falla -- es un dato complementario, no
        # crítico para que el sync termine bien.
        try:
            MarketSnapshotRecorder(db_path=self.db_path).record_snapshot(self.region_id, self.station_id)
        except Exception:
            pass  # complementario -- un fallo acá no debe tumbar el seed completo.

        self.status_repo.set_status(
            region_id=self.region_id,
            phase="history",
            detail=f"Importando historial de volumen para {len(active_type_ids)} ítems con actividad real...",
            total=len(active_type_ids),
            done=0,
        )

        def on_history_progress(done: int, total: int, type_id: int, error: Optional[str]) -> None:
            self.status_repo.set_status(
                region_id=self.region_id,
                phase="history",
                detail=f"{done}/{total} ítems procesados",
                total=total,
                done=done,
            )

        history_importer = MarketHistoryImporter(db_path=str(self.db_path))
        try:
            history_result = history_importer.import_bulk(
                self.region_id,
                active_type_ids,
                progress_callback=on_history_progress,
                max_workers=self.HISTORY_WORKERS,
            )
        except Exception as e:
            self.status_repo.mark_error(self.region_id, str(e))
            raise
        finally:
            history_importer.close()

        result = SeedResult(
            order_count=orders_result["order_count"],
            active_type_id_count=len(active_type_ids),
            history_success=history_result["success"],
            history_failed=len(history_result["failed"]),
        )

        self.status_repo.mark_completed(
            self.region_id,
            detail=(
                f"{result.order_count} órdenes, {result.active_type_id_count} ítems activos, "
                f"historial: {result.history_success} ok / {result.history_failed} fallidos"
            ),
        )
        self.status_repo.set_last_full_seed_at(datetime.now(timezone.utc))

        return result
