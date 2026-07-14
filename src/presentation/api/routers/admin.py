"""
Presentation/API: router de administración (observabilidad básica).

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`.

Protegido con `QUARTERMASTER_ADMIN_KEY` (ver `dependencies.require_admin_key`)
-- no es un sistema de roles, es un secreto compartido. Suficiente para
"solo quien hostea esto puede ver las stats", no para múltiples admins
con acceso revocable individualmente.
"""

from fastapi import APIRouter, Depends

from presentation.api.dependencies import get_services, require_admin_key
from presentation.api.services import ApiServices

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", dependencies=[Depends(require_admin_key)])
def get_stats(services: ApiServices = Depends(get_services)):
    """
    Panorama básico: usuarios totales, cuántos tienen watchlist,
    logins recientes, estado del último sync. Pensado para chequear
    rápido "¿está vivo, hay gente usándolo?" sin tener que leer los
    archivos de log a mano -- ver `infrastructure/observability/logging_setup.py`
    para los logs detallados, esto es solo el resumen.
    """
    return services.get_admin_stats()
