"""
Presentation/API: router de oportunidades.

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`. La
lógica real está en `ApiServices` (sí testeada); este archivo es
deliberadamente delgado.
"""

from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from presentation.api.dependencies import get_services, get_optional_current_user
from presentation.api.services import ApiServices
from presentation.api.schemas import OpportunitiesPageSchema, OpportunitySchema
from domain.value_objects.user import User

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("", response_model=OpportunitiesPageSchema)
def list_opportunities(
    scope: Literal["discovery", "tracked"] = "discovery",
    min_score: float = Query(0.0, ge=0, le=100),
    max_results: int = Query(50, ge=1, le=500),
    sort_by: Literal["score", "roi", "liquidity"] = "score",
    sort_desc: bool = True,
    discovery_limit: int = Query(
        30000, ge=1, le=50000,
        description="Máximo de ítems activos a evaluar en scope=discovery. "
                     "30000 cubre la región completa de Jita hoy (~19.000 ítems activos) con margen.",
    ),
    exclude_caution: bool = Query(
        False,
        description="Si es true, saca del ranking cualquier ítem con recomendación "
                     "caution_* (order book fino, liquidez fantasma, sin volumen, riesgo alto). "
                     "El score no se toca -- es un filtro aparte, no una penalización.",
    ),
    user: Optional[User] = Depends(get_optional_current_user),
    services: ApiServices = Depends(get_services),
):
    """
    scope="discovery" (default): todo lo que tenga order book activo en
    la región, sin depender de la watchlist personal -- esto es lo que
    alimenta el dashboard "de entrada" (ver
    docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §5). Requiere haber
    corrido al menos un Smart Auto-Seed (`POST /api/sync/seed`).
    NO requiere login -- es inteligencia de mercado pública.

    scope="tracked": solo la watchlist personal del usuario logueado.
    SÍ requiere `Authorization: Bearer <token>` -- 401 si falta.
    """
    if scope == "tracked" and user is None:
        raise HTTPException(
            status_code=401,
            detail="scope='tracked' requiere estar logueado -- mandá 'Authorization: Bearer <token>'.",
        )

    try:
        page = services.list_opportunities(
            scope=scope, min_score=min_score, max_results=max_results,
            sort_by=sort_by, sort_desc=sort_desc, discovery_limit=discovery_limit,
            exclude_caution=exclude_caution,
            user_id=user.id if user else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return OpportunitiesPageSchema(
        opportunities=[OpportunitySchema.from_domain(o, confidence) for o, confidence in page.opportunities],
        total_evaluated=page.total_evaluated,
        total_with_data=page.total_with_data,
        scope=page.scope,
    )


@router.get("/{type_id}", response_model=OpportunitySchema)
def get_opportunity(type_id: int, services: ApiServices = Depends(get_services)):
    detail = services.get_opportunity_detail(type_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"type_id {type_id} sin order book completo en la región (falta buy o sell)."
        )
    opportunity, confidence = detail
    return OpportunitySchema.from_domain(opportunity, confidence)
