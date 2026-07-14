"""
Presentation/API: router de sync / Smart Auto-Seed.

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException

from presentation.api.dependencies import get_services
from presentation.api.services import ApiServices
from presentation.api.schemas import SyncStatusSchema, SeedTriggerResponse

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusSchema)
def get_status(services: ApiServices = Depends(get_services)):
    status = services.get_sync_status()
    if status is None:
        raise HTTPException(
            status_code=404,
            detail="Todavía no se corrió ningún sync. Disparalo con POST /api/sync/seed."
        )
    return SyncStatusSchema(**status)


@router.post("/seed", response_model=SeedTriggerResponse, status_code=202)
def trigger_seed(
    background_tasks: BackgroundTasks,
    services: ApiServices = Depends(get_services),
):
    """
    Dispara el Smart Auto-Seed (sync completo de región + historial
    acotado a lo que tenga actividad real -- ver
    `infrastructure/jobs/seed_job.py`). Corre en BackgroundTask: este
    endpoint responde inmediato con 202, el progreso real se consulta
    con GET /api/sync/status.

    Puede tardar minutos (el order book completo es rápido, el
    historial es 1 request por ítem activo -- ver estimaciones honestas
    en docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §7).

    Si ya hay una corrida en curso (p.ej. el auto-seed de arranque
    todavía no terminó), NO encola una segunda -- devuelve
    status="already_running" en vez de duplicar trabajo contra ESI.
    """
    if services.is_seed_running():
        current_status = services.get_sync_status()
        detail = current_status.get("detail") if current_status else None
        return SeedTriggerResponse(
            status="already_running",
            message=f"Ya hay un Smart Auto-Seed en curso ({detail or 'sin detalle'}). "
                    "Consultá GET /api/sync/status para ver el progreso.",
        )

    background_tasks.add_task(services.run_seed_job)
    return SeedTriggerResponse(
        status="started",
        message="Smart Auto-Seed encolado. Consultá el progreso en GET /api/sync/status.",
    )
