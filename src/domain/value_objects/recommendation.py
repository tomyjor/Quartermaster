"""
Value Object: RecommendationLevel

Clasificación normativa de una Opportunity en una acción sugerida para
el trader.

Vive en el dominio -- no en la capa de presentación -- porque "¿cuándo es
seguro recomendar una compra?" es una regla de negocio, no un detalle de
UI. Antes de este cambio, `app.py` (Streamlit) reimplementaba sus propios
umbrales hardcodeados (`score >= 65 and liquidity_score >= 12`) para
decidir el badge "Compra recomendada". Eso es exactamente el tipo de
acoplamiento que Clean Architecture prohíbe: una regla de negocio
filtrada a la capa de presentación, imposible de testear sin levantar
Streamlit y fácil de desincronizar del resto del scoring.

Ahora la clasificación la calcula OpportunityEngine (ver
`OpportunityEngine._classify_recommendation`) y la capa de presentación
se limita a leer `Opportunity.recommendation` / `.recommendation_reason`
y pintar el badge correspondiente.
"""

from enum import Enum


class RecommendationLevel(str, Enum):
    """
    Nivel de recomendación calculado por OpportunityEngine para una
    Opportunity ya evaluada.

    Hereda de `str` para que sea trivialmente serializable (JSON, session
    state de Streamlit, etc.) y comparable con literales de texto sin
    conversiones extra.
    """

    #: Score alto Y liquidez real confirmada (turnover diario > 0 y
    #: liquidity_score por encima del umbral). La única categoría que
    #: debe mostrarse como "Compra recomendada".
    BUY = "buy"

    #: No hay señales destacadas en ningún sentido; ni para recomendar
    #: ni para advertir explícitamente.
    NEUTRAL = "neutral"

    #: Hay algo de volumen diario registrado, pero el liquidity_score
    #: resultante sigue siendo muy bajo -- posible order book fantasma
    #: (mucha profundidad ofertada, poco movimiento real).
    CAUTION_LOW_LIQUIDITY = "caution_low_liquidity"

    #: daily_volume == 0: no hay NINGUNA evidencia de volumen diario
    #: negociado (típicamente porque no se importó market_history, o
    #: porque el ítem de verdad no se comercia). No se puede confirmar
    #: ni descartar liquidez real todavía.
    CAUTION_NO_VOLUME_DATA = "caution_no_volume_data"

    #: overall_risk_score por encima del umbral de precaución.
    CAUTION_HIGH_RISK = "caution_high_risk"

    #: El mejor precio de compra y/o venta usado para calcular ROI está
    #: respaldado por muy pocas órdenes activas (menos de
    #: OpportunityEngine.MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST de algún
    #: lado). Un ROI calculado sobre una sola orden puede ser una orden
    #: aislada, un error de tipeo, o una orden vieja sin cancelar -- no
    #: es representativo de un precio de mercado real. Independiente de
    #: liquidity_score: un ítem puede tener buena profundidad TOTAL en
    #: el book y aun así tener su mejor precio puntual sostenido por una
    #: única orden atípica.
    CAUTION_THIN_ORDER_BOOK = "caution_thin_order_book"

    #: El spread entre mejor compra y mejor venta es implausible (ver
    #: OpportunityEngine.MAX_PLAUSIBLE_SPREAD_RATIO) AUNQUE haya
    #: suficientes órdenes de cada lado para pasar el chequeo de
    #: CAUTION_THIN_ORDER_BOOK. Encontrado con datos reales: un ítem con
    #: 4 órdenes de compra (mejor precio 1.1 ISK) y 19 de venta (mejor
    #: precio 78.69 ISK) -- un spread de ~70x -- no disparaba ninguna
    #: advertencia porque el conteo de órdenes por sí solo no capta
    #: "compradores y vendedores en mundos de precio completamente
    #: distintos". El conteo mide profundidad, no coherencia de precio.
    CAUTION_IMPLAUSIBLE_SPREAD = "caution_implausible_spread"

    @property
    def is_positive(self) -> bool:
        """True solo para la recomendación de compra activa."""
        return self is RecommendationLevel.BUY

    @property
    def is_caution(self) -> bool:
        """True para cualquier variante que deba mostrarse como advertencia."""
        return self.value.startswith("caution_")
