"""
Presentation/API: schemas

Modelos Pydantic para servir Value Objects de dominio por HTTP. Es
traducción mecánica -- ninguna decisión de negocio vive acá, eso está
en `services.py` y, más abajo, en el dominio.

⚠️ NO EJECUTADO: este archivo requiere `pydantic` (v2), que no está
instalado en el entorno donde se escribió. Sintaxis revisada a mano
contra Pydantic v2 (BaseModel + ConfigDict), pero correlo vos con
`pip install -e ".[api]"` y avisame qué falla si algo no importa limpio.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from shared.eta import format_duration_hours
from domain.services.opportunity_explainer import OpportunityExplainer


class MoneySchema(BaseModel):
    amount: float
    currency: str = "ISK"

    model_config = ConfigDict(from_attributes=True)


class LiquiditySchema(BaseModel):
    daily_volume: float
    liquidity_score: float
    depth_score: float

    model_config = ConfigDict(from_attributes=True)


class RiskSchema(BaseModel):
    overall_risk_score: float
    risk_level: str

    model_config = ConfigDict(from_attributes=True)


class ExplanationSchema(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    neutral_factors: List[str]
    liquidity_interpretation: str
    risk_interpretation: str
    insights: List[str]


class OpportunitySchema(BaseModel):
    type_id: int
    type_name: str
    region_id: int
    buy_price: float
    sell_price: float
    roi_percent: float
    score: float
    confidence: float
    liquidity: LiquiditySchema
    risk: RiskSchema
    recommendation: str
    recommendation_reason: str
    sell_order_count: int
    buy_order_count: int
    score_breakdown: Dict[str, Any]
    estimated_exit_hours: float
    estimated_exit_position_size: float
    estimated_exit_human: Optional[str] = None
    explanation: ExplanationSchema

    @classmethod
    def from_domain(cls, opportunity, confidence: float) -> "OpportunitySchema":
        """
        Traduce un `domain.value_objects.opportunity.Opportunity` (más
        anidados como Money/Liquidity/Risk) a este schema. Centralizado
        acá para que los routers no reimplementen la traducción cada uno.

        `confidence` viene aparte porque vive en `AnalysisResult`, no en
        `Opportunity` -- ver changelog en `ApiServices.OpportunitiesPage`.

        `explanation` se genera acá mismo con `OpportunityExplainer`
        (domain service, no lógica de presentación) -- ver
        docs/ROADMAP_Y_PENDIENTES.md, mejora de UX/calidad de análisis.

        ⚠️ Traducción de vocabulario deliberada: el dominio (Etapa 1 de
        la generalización, ver docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md)
        habla `instrument_id`/`instrument_name`/`market_id`, pero este
        schema sigue exponiendo `type_id`/`type_name`/`region_id` en el
        JSON -- a propósito, para no romper el contrato de la API ni las
        UIs (Streamlit, NiceGUI) en el mismo movimiento que generaliza el
        dominio. Renombrar el contrato público es un paso aparte,
        deliberadamente pospuesto.
        """
        explanation = OpportunityExplainer().explain(opportunity)
        return cls(
            type_id=opportunity.instrument_id,
            type_name=opportunity.instrument_name,
            region_id=opportunity.market_id,
            buy_price=opportunity.buy_price.amount,
            sell_price=opportunity.sell_price.amount,
            roi_percent=opportunity.roi_percent,
            score=opportunity.score,
            confidence=confidence,
            liquidity=LiquiditySchema(
                daily_volume=opportunity.liquidity.daily_volume,
                liquidity_score=opportunity.liquidity.liquidity_score,
                depth_score=opportunity.liquidity.depth_score,
            ),
            risk=RiskSchema(
                overall_risk_score=opportunity.risk.overall_risk_score,
                risk_level=opportunity.risk.risk_level,
            ),
            recommendation=opportunity.recommendation.value,
            recommendation_reason=opportunity.recommendation_reason,
            sell_order_count=opportunity.sell_order_count,
            buy_order_count=opportunity.buy_order_count,
            score_breakdown=opportunity.score_breakdown,
            estimated_exit_hours=opportunity.estimated_exit_hours,
            estimated_exit_position_size=opportunity.estimated_exit_position_size,
            estimated_exit_human=format_duration_hours(opportunity.estimated_exit_hours),
            explanation=ExplanationSchema(
                summary=explanation.summary,
                strengths=explanation.strengths,
                weaknesses=explanation.weaknesses,
                neutral_factors=explanation.neutral_factors,
                liquidity_interpretation=explanation.liquidity_interpretation,
                risk_interpretation=explanation.risk_interpretation,
                insights=explanation.insights,
            ),
        )


class OpportunitiesPageSchema(BaseModel):
    opportunities: List[OpportunitySchema]
    total_evaluated: int
    total_with_data: int
    scope: str


class TrackedItemSchema(BaseModel):
    type_id: int
    name: str


class TrackItemRequest(BaseModel):
    reason: Optional[str] = None


class UntrackManyRequest(BaseModel):
    type_ids: List[int]


class UntrackResultSchema(BaseModel):
    deleted: int


class SearchResultSchema(BaseModel):
    id: int
    name: str


class CategorySchema(BaseModel):
    category_id: int
    name: str
    item_count: int


class GroupSchema(BaseModel):
    group_id: int
    name: str
    item_count: int


class CatalogTypeSchema(BaseModel):
    id: int
    name: str


class SyncStatusSchema(BaseModel):
    region_id: int
    phase: str
    detail: Optional[str] = None
    total: Optional[int] = None
    done: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: str
    error: Optional[str] = None
    eta_seconds: Optional[float] = None
    eta_human: Optional[str] = None


class SeedResultSchema(BaseModel):
    order_count: int
    active_type_id_count: int
    history_success: int
    history_failed: int


class SeedTriggerResponse(BaseModel):
    """Respuesta inmediata al disparar un seed -- el trabajo real corre
    en background, esto solo confirma que se encoló."""
    status: str
    message: str
