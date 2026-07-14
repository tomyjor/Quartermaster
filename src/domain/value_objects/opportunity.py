"""
Value Object: Opportunity
Representa una oportunidad de mercado ya analizada por OpportunityEngine.

Es deliberadamente un objeto de datos "tonto": toda la lógica de cálculo
(score, desglose, recomendación) vive en los motores de dominio, nunca
acá ni en la capa de presentación. Esto mantiene el Value Object como una
simple fotografía inmutable y consistente de un análisis ya hecho -- dos
instancias con los mismos campos son, por definición, la misma
oportunidad.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from domain.value_objects.money import Money
from domain.value_objects.risk import Risk
from domain.value_objects.liquidity import Liquidity
from domain.value_objects.recommendation import RecommendationLevel


@dataclass(frozen=True)
class Opportunity:
    """
    Resultado final e inmutable del análisis de una oportunidad de
    trading. Vocabulario generalizado (ver
    docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md) -- `instrument_id` /
    `market_id` en vez de `type_id` / `region_id` (nombres tomados
    directo de EVE Online): el concepto de "un instrumento tradeable
    dentro de un mercado" no es específico de EVE.
    """

    instrument_id: int
    instrument_name: str
    market_id: int

    buy_price: Money
    sell_price: Money

    roi_percent: float
    liquidity: Liquidity
    risk: Risk

    score: float = 0.0
    notes: Optional[str] = None

    #: Cantidad de órdenes de venta / compra activas detrás del mejor
    #: precio usado para ROI. Existen para que la UI pueda mostrar POR
    #: QUÉ un ROI puede no ser confiable (ver
    #: RecommendationLevel.CAUTION_THIN_ORDER_BOOK) sin tener que
    #: adivinar -- el número crudo está siempre disponible, no solo el
    #: veredicto derivado.
    sell_order_count: int = 0
    buy_order_count: int = 0

    #: Desglose completo y verificable del cálculo del score. Cada
    #: componente en `score_breakdown["components"]` incluye su valor
    #: crudo (0-100), su peso y su contribución real (raw_value * weight);
    #: la suma de todas las "contribution" es, por construcción, igual a
    #: `score` (con un margen de redondeo de centésimas). Ver
    #: `OpportunityEngine._build_score_breakdown`.
    score_breakdown: Dict[str, Any] = field(default_factory=dict)

    #: Recomendación calculada por el dominio (no por la UI). La capa de
    #: presentación solo debe leer estos dos campos para pintar el badge
    #: correspondiente -- nunca reimplementar sus propios umbrales.
    recommendation: RecommendationLevel = RecommendationLevel.NEUTRAL
    recommendation_reason: str = ""

    #: Horas estimadas para vender `estimated_exit_position_size`
    #: unidades, calculado por `ExitTimeEngine`. Antes se calculaba y se
    #: usaba SOLO para derivar el componente de score correspondiente,
    #: después se descartaba -- nunca llegaba como número crudo hasta
    #: acá. Es una estimación sobre una posición de REFERENCIA, NO
    #: sobre la posición real del usuario (que el sistema no conoce
    #: todavía, no hay tracking de portfolio) -- la UI debe dejar esto
    #: claro, no presentarlo como "tu" tiempo de venta.
    estimated_exit_hours: float = 0.0

    #: Cuántas unidades es esa "posición de referencia" -- v2: dejó de
    #: ser un número fijo (100) para todos los ítems. Hallazgo real del
    #: usuario: 100 unidades de un misil no es representativo de cómo
    #: se comercia en la práctica (se vende en bulk); ahora se deriva
    #: del tamaño promedio de las órdenes de venta activas en el book
    #: (ver `OpportunityEngine._reference_position_size`), con un piso
    #: de 100. Se expone acá para que la UI muestre el número REAL
    #: usado, no un "100u" hardcodeado que ya no sería cierto para
    #: ítems con lotes más grandes.
    estimated_exit_position_size: float = 100.0

    @property
    def is_buy_recommended(self) -> bool:
        """Azúcar sintáctica para la capa de presentación."""
        return self.recommendation.is_positive
