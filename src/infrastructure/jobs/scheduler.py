"""
Infrastructure/Jobs: scheduler

Wiring de APScheduler para refresco periódico -- reemplaza a Celery+Redis
(ver docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §4 para el razonamiento:
este proyecto no tiene el perfil de carga que justifica un broker
distribuido). Corre en el mismo proceso que la API, sin dependencias
externas nuevas.

⚠️ NO EJECUTADO -- requiere `apscheduler`. Ver nota en `schemas.py`.

Dos jobs periódicos, con frecuencias distintas a propósito:
- Order book: barato (un solo fetch paginado por región, ver
  `MarketOrdersImporter.import_full_region`), se puede refrescar seguido.
- Historial de volumen: caro (1 request por type_id activo), se
  refresca con mucha menor frecuencia -- el volumen diario no cambia
  significativamente cada pocos minutos, refrescarlo tan seguido como
  el order book sería desperdiciar rate limit de ESI sin beneficio real.
"""

import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from infrastructure.jobs.seed_job import SmartAutoSeedJob, JITA_REGION_ID
from infrastructure.esi.market_orders_importer import MarketOrdersImporter
from infrastructure.jobs.sync_status_repository import SyncStatusRepository
from shared.paths import DEFAULT_DB_PATH

logger = logging.getLogger("quartermaster.scheduler")

#: Minutos entre refrescos del order book completo (barato, sync único paginado).
ORDERS_REFRESH_INTERVAL_MINUTES = 20

#: Horas entre refrescos completos de historial de volumen (caro, 1 req/ítem activo).
HISTORY_REFRESH_INTERVAL_HOURS = 12


def _refresh_orders_only(db_path: Path, region_id: int) -> None:
    """
    Refresco liviano: solo el order book (rápido, barato). No toca
    historial -- eso lo hace el job de refresco completo, con mucha
    menor frecuencia.
    """
    status_repo = SyncStatusRepository(db_path=db_path)
    status_repo.set_status(
        region_id=region_id, phase="orders",
        detail="Refresco periódico de order book...", reset_started_at=True,
    )

    def on_page(page: int, total_pages: int, orders_so_far: int) -> None:
        status_repo.set_status(
            region_id=region_id, phase="orders",
            detail=f"Refresco periódico: página {page}/{total_pages} ({orders_so_far} órdenes)",
            total=total_pages, done=page,
        )

    importer = MarketOrdersImporter(db_path=str(db_path))
    try:
        result = importer.import_full_region(region_id, progress_callback=on_page)
        status_repo.mark_completed(
            region_id,
            detail=f"Refresco periódico: {result['order_count']} órdenes, "
                   f"{len(result['distinct_type_ids'])} ítems activos.",
        )
    except Exception as e:
        status_repo.mark_error(region_id, str(e))
        logger.exception("Falló el refresco periódico de order book")
    finally:
        importer.close()


def _refresh_full_seed(db_path: Path, region_id: int) -> None:
    """Refresco completo (order book + historial). Ver SmartAutoSeedJob."""
    job = SmartAutoSeedJob(db_path=db_path, region_id=region_id)
    try:
        job.run()
    except Exception:
        logger.exception("Falló el refresco periódico completo (order book + historial)")


def build_scheduler(
    db_path: Path = DEFAULT_DB_PATH,
    region_id: int = JITA_REGION_ID,
) -> BackgroundScheduler:
    """
    Arma (pero no arranca) el scheduler con los dos jobs periódicos.
    El caller (`main.py`, en el evento de startup) es responsable de
    llamar `.start()` y, al apagar, `.shutdown()`.
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _refresh_orders_only,
        trigger="interval",
        minutes=ORDERS_REFRESH_INTERVAL_MINUTES,
        args=[db_path, region_id],
        id="refresh_orders_only",
        replace_existing=True,
        max_instances=1,  # nunca dos refrescos de orders superpuestos
    )

    scheduler.add_job(
        _refresh_full_seed,
        trigger="interval",
        hours=HISTORY_REFRESH_INTERVAL_HOURS,
        args=[db_path, region_id],
        id="refresh_full_seed",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
