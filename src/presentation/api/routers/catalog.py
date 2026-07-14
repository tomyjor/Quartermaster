"""
Presentation/API: router de navegación del catálogo (Categoría → Grupo → Ítems).

Nuevo -- estos datos (categorías/grupos del SDE) existían como métodos
del repositorio desde hace tiempo, pero solo Streamlit los usaba (con
acceso directo a la base). NiceGUI consume todo vía HTTP -- sin este
router, el explorador de Categoría → Grupo no se podía portar.
"""

from typing import List
from fastapi import APIRouter, Depends

from presentation.api.dependencies import get_services
from presentation.api.services import ApiServices
from presentation.api.schemas import CategorySchema, GroupSchema, CatalogTypeSchema

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/categories", response_model=List[CategorySchema])
def list_categories(services: ApiServices = Depends(get_services)):
    rows = services.list_categories()
    return [
        CategorySchema(category_id=r["category_id"], name=r["name"], item_count=r["item_count"])
        for r in rows
    ]


@router.get("/categories/{category_id}/groups", response_model=List[GroupSchema])
def list_groups(category_id: int, services: ApiServices = Depends(get_services)):
    rows = services.list_groups_by_category(category_id)
    return [
        GroupSchema(group_id=r["group_id"], name=r["name"], item_count=r["item_count"])
        for r in rows
    ]


@router.get("/groups/{group_id}/types", response_model=List[CatalogTypeSchema])
def list_types_in_group(group_id: int, limit: int = 40, services: ApiServices = Depends(get_services)):
    rows = services.list_types_in_group(group_id, limit=limit)
    return [CatalogTypeSchema(id=r["id"], name=r["name"]) for r in rows]
