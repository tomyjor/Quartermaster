"""
Tests básicos para OpportunityEngine.
"""

from domain.value_objects.money import Money
from domain.value_objects.fee_profile import FeeProfile
from domain.value_objects.recommendation import RecommendationLevel
from domain.services.opportunity_engine import OpportunityEngine, OpportunityInput


TAX = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)


def _make_input(buy, sell, daily_volume=0.0, sell_remain=500_000.0,
                 sell_count=3, buy_count=3, buy_remain=0.0):
    return OpportunityInput(
        instrument_id=1, instrument_name="Test Item", market_id=10000002,
        buy_price=Money(int(buy * 100), currency="ISK"), sell_price=Money(int(sell * 100), currency="ISK"),
        daily_volume=daily_volume, total_sell_volume_remain=sell_remain,
        total_buy_volume_remain=buy_remain,
        sell_order_count=sell_count, buy_order_count=buy_count,
        fee_profile=TAX,
    )


def test_opportunity_engine_detects_opportunity():
    engine = OpportunityEngine()

    input_data = OpportunityInput(
        instrument_id=34,
        instrument_name="Tritanium",
        market_id=10000002,
        buy_price=Money(300, currency="ISK"),
        sell_price=Money(450, currency="ISK"),
        daily_volume=50000,
        total_sell_volume_remain=120000,
        sell_order_count=25,
        buy_order_count=40,
        fee_profile=TAX
    )

    result = engine.detect(input_data)

    assert result.is_valid
    assert result.value.score > 0
    assert result.value.risk is not None
    assert result.value.liquidity is not None


def test_roi_component_no_longer_saturates_for_high_roi_items():
    """
    Regresión del bug reportado: ROI de 292%, 1558% y 3559% (con la
    misma liquidez/condiciones) deben producir scores DIFERENTES, no el
    mismo valor colapsado. La fórmula log_v1 saturaba a partir de ~139%
    de ROI.
    """
    engine = OpportunityEngine()

    inputs = [
        _make_input(buy=100, sell=380),   # ROI moderado-alto
        _make_input(buy=100, sell=1650),  # ROI muy alto
        _make_input(buy=100, sell=3650),  # ROI extremo
    ]
    scores = [engine.detect(inp).value.score for inp in inputs]

    # Estrictamente creciente: a mayor ROI (con todo lo demás igual),
    # el score debe ser mayor.
    assert scores[0] < scores[1] < scores[2], scores

    # Y con separación real, no un empate por redondeo.
    assert scores[2] - scores[0] > 2.0, scores


def test_recommendation_requires_real_liquidity_not_just_high_score():
    """
    Regresión del bug del badge: un ítem con ROI extremo pero SIN
    evidencia de volumen diario (order book potencialmente fantasma)
    nunca debe recibir RecommendationLevel.BUY, sin importar cuán alto
    sea su ROI.
    """
    engine = OpportunityEngine()

    ghost_book = _make_input(buy=100, sell=3650, daily_volume=0, sell_remain=50_000_000)
    result = engine.detect(ghost_book)

    assert result.value.recommendation != RecommendationLevel.BUY
    assert result.value.recommendation == RecommendationLevel.CAUTION_NO_VOLUME_DATA


def test_implausible_spread_flagged_even_with_enough_orders_per_side():
    """
    Regresión de un caso real reportado por el usuario: "Arch Angel
    Nuclear S" tenía 4 órdenes de compra (mejor precio 1.1 ISK) y 19 de
    venta (mejor precio 78.69 ISK) -- spread de ~70x, ROI de 6581.8% --
    y pasaba sin ninguna advertencia porque 4 >= MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST (2).
    El conteo de órdenes mide profundidad, no si esas órdenes están en
    el mismo rango de precio -- hace falta un chequeo aparte.
    """
    engine = OpportunityEngine()

    # buy=1.1, sell=78.69 -> ratio ~71.5x, con suficientes órdenes de
    # cada lado (no debería disparar CAUTION_THIN_ORDER_BOOK) y CON
    # volumen diario real (no debería disparar CAUTION_NO_VOLUME_DATA) --
    # así el único motivo posible de la advertencia es el spread en sí.
    implausible = _make_input(
        buy=1.1, sell=78.69, daily_volume=50_000, sell_remain=1_000_000,
        sell_count=19, buy_count=4,
    )
    result = engine.detect(implausible)

    assert result.value.recommendation == RecommendationLevel.CAUTION_IMPLAUSIBLE_SPREAD
    assert result.value.recommendation != RecommendationLevel.BUY
    assert "72x" in result.value.recommendation_reason or "71x" in result.value.recommendation_reason


def test_wide_but_plausible_spread_with_real_depth_is_not_flagged():
    """
    Contraprueba: un ítem con spread ancho pero DENTRO del umbral
    plausible (ej. ~2x, no ~70x) y profundidad real de verdad en ambos
    lados no debería dispararse por este chequeo nuevo -- ver
    "Carbonized Lead M" en los datos reales que motivaron este fix
    (spread ~2x, liquidez limitada correctamente reflejada en el score,
    pero NO en la categoría de recomendación por spread implausible).
    """
    engine = OpportunityEngine()

    wide_but_real = _make_input(
        buy=6.52, sell=12.79, daily_volume=50_000, sell_remain=1_000_000,
        sell_count=9, buy_count=8,
    )
    result = engine.detect(wide_but_real)

    assert result.value.recommendation != RecommendationLevel.CAUTION_IMPLAUSIBLE_SPREAD


def test_recommendation_buy_requires_score_and_liquidity_together():
    """Con ROI decente, liquidez real y bajo riesgo, sí debe recomendar compra."""
    engine = OpportunityEngine()

    healthy = _make_input(
        buy=100, sell=220, daily_volume=20000, sell_remain=30_000_000,
        sell_count=20, buy_count=20,
    )
    result = engine.detect(healthy)

    assert result.value.recommendation == RecommendationLevel.BUY
    assert result.value.is_buy_recommended is True


def test_negative_roi_never_recommends_buy_even_with_perfect_everything_else():
    """
    Regresión de un hueco real encontrado revisando resultados de
    producción: _classify_recommendation no chequeaba explícitamente
    roi_percent > 0 en el gate de BUY. En la práctica RiskEngine ya
    penaliza el ROI bajo/negativo (profitability_risk = max(0, 50 - roi))
    lo suficiente como para que el score nunca llegue a 65 con ROI
    negativo -- pero eso era una protección incidental, no garantizada.
    Este test prueba el caso límite teórico (liquidez perfecta, salida
    instantánea, riesgo mínimo posible) para confirmar que ahora es
    imposible recomendar BUY con ROI negativo, sin depender de cómo
    interactúen el resto de los componentes.
    """
    engine = OpportunityEngine()
    tax_casi_sin_fees = FeeProfile(entry_fee_rate=0.001, exit_fee_rate=0.001)

    caso_limite = OpportunityInput(
        instrument_id=1, instrument_name="Caso límite ROI negativo", market_id=10000002,
        buy_price=Money(100000, currency="ISK"), sell_price=Money(99999, currency="ISK"),  # ROI apenas negativo
        daily_volume=1_000_000_000, total_sell_volume_remain=100_000_000,
        total_buy_volume_remain=100_000_000,
        sell_order_count=200, buy_order_count=200,
        fee_profile=tax_casi_sin_fees,
    )
    result = engine.detect(caso_limite)

    assert result.value.roi_percent < 0
    assert result.value.recommendation != RecommendationLevel.BUY


def test_score_breakdown_contributions_sum_to_final_score():
    """
    Chequeo de honestidad matemática: la suma de las contribuciones
    individuales del desglose debe coincidir con el score final (salvo
    un margen de redondeo de centésimas). Si esto falla, hay un bug de
    composición en OpportunityEngine.
    """
    engine = OpportunityEngine()
    result = engine.detect(_make_input(buy=100, sell=180, daily_volume=8000, sell_remain=10_000_000))

    breakdown = result.value.score_breakdown
    assert breakdown["formula_version"] == "log_v2"

    computed_sum = sum(c["contribution"] for c in breakdown["components"].values())
    assert abs(computed_sum - breakdown["final_score"]) < 0.5


def test_score_breakdown_always_present():
    engine = OpportunityEngine()
    result = engine.detect(_make_input(buy=100, sell=150))
    assert result.value.score_breakdown
    assert "components" in result.value.score_breakdown
    assert "recommendation" in result.value.score_breakdown


def test_extreme_roi_from_single_order_is_flagged_not_hidden():
    """
    Regresión del caso reportado: 'Carbonized Lead L' con buy=1.00 ISK,
    sell=30.00 ISK (ROI=2702%, matemáticamente correcto) mostrado sin
    ninguna advertencia cuando el precio estaba respaldado por una sola
    orden de cada lado. El ROI numérico NO se toca (sigue siendo
    2702% -- no se esconden ni se inventan datos), pero la recomendación
    debe marcarlo explícitamente como no confiable.
    """
    engine = OpportunityEngine()

    single_order_each_side = _make_input(
        buy=1.00, sell=30.00, daily_volume=84343.9, sell_remain=5_463_772,
        sell_count=1, buy_count=1,
    )
    result = engine.detect(single_order_each_side)

    assert result.value.roi_percent == 2702.0  # el número no se altera
    assert result.value.recommendation == RecommendationLevel.CAUTION_THIN_ORDER_BOOK
    assert result.value.recommendation != RecommendationLevel.BUY


def test_same_extreme_roi_with_real_order_depth_is_not_flagged_as_thin():
    """El mismo ROI extremo, pero con varias órdenes reales de cada lado,
    no debe caer en CAUTION_THIN_ORDER_BOOK (aunque puede caer en otra
    categoría según el resto del score)."""
    engine = OpportunityEngine()

    many_orders_each_side = _make_input(
        buy=1.00, sell=30.00, daily_volume=84343.9, sell_remain=5_463_772,
        sell_count=8, buy_count=8,
    )
    result = engine.detect(many_orders_each_side)

    assert result.value.recommendation != RecommendationLevel.CAUTION_THIN_ORDER_BOOK


def test_recommendation_reason_never_empty_for_any_category():
    """Todas las categorías de recomendación deben venir con una razón
    explicable -- ninguna debe dejar al usuario sin ningún mensaje
    (regresión: NEUTRAL antes no pintaba ningún badge en la UI)."""
    engine = OpportunityEngine()

    scenarios = [
        _make_input(buy=100, sell=110, sell_count=1, buy_count=1),        # thin order book
        _make_input(buy=100, sell=150, daily_volume=0),                    # no volume data
        _make_input(buy=100, sell=150, daily_volume=50, sell_remain=100),  # low liquidity
        _make_input(buy=100, sell=105, daily_volume=20000, sell_remain=30_000_000,
                     sell_count=20, buy_count=20),                          # likely neutral/high-risk
    ]
    for inp in scenarios:
        result = engine.detect(inp)
        assert result.value.recommendation_reason.strip() != ""
        assert result.value.recommendation is not None
