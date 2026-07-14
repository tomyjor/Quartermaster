"""
Presentation/API: router de búsqueda de items del SDE.

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`.
"""

from typing import List
from fastapi import APIRouter, Depends, Query

from presentation.api.dependencies import get_services
from presentation.api.services import ApiServices
from presentation.api.schemas import SearchResultSchema

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/search", response_model=List[SearchResultSchema])
def search_items(
    q: str = Query(..., min_length=2, description="Parte del nombre a buscar"),
    limit: int = Query(20, ge=1, le=100),
    services: ApiServices = Depends(get_services),
):
    results = services.search_items(q.strip(), limit=limit)
    return [SearchResultSchema(id=r["id"], name=r["name"]) for r in results]
