"""
Presentation/API: router de watchlist personal (tracked items).

v2 (multi-tenancy): TODOS los endpoints requieren estar logueado
(`Depends(get_current_user)`) -- una watchlist sin dueño ya no es un
concepto válido. Cada endpoint usa `user.id` para que cada quien vea y
modifique SOLO su propia watchlist, nunca la de otro.

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from typing import List

from presentation.api.dependencies import get_services, get_current_user
from presentation.api.services import ApiServices
from presentation.api.schemas import (
    TrackItemRequest, UntrackManyRequest, UntrackResultSchema, TrackedItemSchema
)
from domain.value_objects.user import User
from infrastructure.esi.market_orders_importer import MarketOrdersImporter
from infrastructure.esi.market_history_importer import MarketHistoryImporter

router = APIRouter(prefix="/api/tracked-items", tags=["tracked-items"])


@router.get("", response_model=List[TrackedItemSchema])
def list_tracked(
    user: User = Depends(get_current_user),
    services: ApiServices = Depends(get_services),
):
    """
    Con nombres resueltos (no solo type_ids) -- para que la UI pueda
    mostrar una lista legible sin pedir el análisis completo de cada
    ítem solo para leer un nombre.
    """
    return [TrackedItemSchema(**item) for item in services.list_tracked_items(user.id)]


def _import_single_item(db_path, region_id: int, type_id: int) -> None:
    """
    Se corre como BackgroundTask -- el request de POST /track responde
    inmediato (a diferencia del botón viejo de Streamlit que bloqueaba
    la UI entera esperando dos llamadas ESI secuenciales). El cliente
    consulta el progreso general vía GET /api/sync/status si necesita
    saber cuándo terminó.

    Nota: esto trae datos de mercado COMPARTIDOS (market_orders no
    tiene dueño) -- no hace falta que sea "del" usuario que trackeó,
    cualquier usuario que trackee el mismo ítem se beneficia del mismo
    import, no se duplica el trabajo por usuario.
    """
    orders_importer = MarketOrdersImporter(db_path=str(db_path))
    orders_importer.import_type_orders(region_id, type_id)
    orders_importer.close()

    history_importer = MarketHistoryImporter(db_path=str(db_path))
    history_importer.import_type_history(region_id, type_id)
    history_importer.close()


@router.post("/{type_id}", status_code=202)
def track_item(
    type_id: int,
    body: TrackItemRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    services: ApiServices = Depends(get_services),
):
    """
    202 Accepted: el tracking se confirma inmediato, el import de
    órdenes+historial corre en background. Este es el fix directo del
    bug de "botón colgado" que tenía la versión Streamlit -- acá el
    cliente HTTP nunca espera bloqueado a que termine ESI.
    """
    services.track_item(user.id, type_id, reason=body.reason)
    background_tasks.add_task(_import_single_item, services.db_path, services.region_id, type_id)
    return {"status": "tracking", "type_id": type_id, "import": "en progreso en background"}


@router.delete("/{type_id}")
def untrack_item(
    type_id: int,
    user: User = Depends(get_current_user),
    services: ApiServices = Depends(get_services),
):
    services.untrack_item(user.id, type_id)
    return {"status": "ok"}


@router.post("/batch/untrack", response_model=UntrackResultSchema)
def untrack_many(
    body: UntrackManyRequest,
    user: User = Depends(get_current_user),
    services: ApiServices = Depends(get_services),
):
    deleted = services.untrack_many_items(user.id, body.type_ids)
    return UntrackResultSchema(deleted=deleted)


@router.delete("", response_model=UntrackResultSchema)
def untrack_all(
    user: User = Depends(get_current_user),
    services: ApiServices = Depends(get_services),
):
    """
    Elimina TODA la watchlist de este usuario en una sola sentencia SQL
    atómica (ver `SQLiteTypeRepository.untrack_all`) -- no un loop por
    ítem, que era la causa del bug de "borra de a tandas" en la versión
    Streamlit. Solo afecta al usuario autenticado, nunca a otros.
    """
    deleted = services.untrack_all_items(user.id)
    return UntrackResultSchema(deleted=deleted)
