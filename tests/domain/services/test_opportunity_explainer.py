"""
Tests para OpportunityExplainer -- construye una Opportunity sintética
con `OpportunityEngine.detect()` real (no mockeamos el score_breakdown a
mano, así los tests corren contra la forma real del dato) y verifican
que las explicaciones sean data-driven, no genéricas.
"""

from domain.value_objects.money import Money
from domain.value_objects.fee_profile import FeeProfile
from domain.services.opportunity_engine import OpportunityEngine, OpportunityInput
from domain.services.opportunity_explainer import OpportunityExplainer

TAX = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)


def _detect(**overrides):
    engine = OpportunityEngine()
    defaults = dict(
        instrument_id=1, instrument_name="Test Item", market_id=10000002,
        buy_price=Money(1000, currency="ISK"), sell_price=Money(1200, currency="ISK"),
        daily_volume=100000, total_sell_volume_remain=50000, total_buy_volume_remain=50000,
        sell_order_count=20, buy_order_count=20, fee_profile=TAX,
    )
    defaults.update(overrides)
    return engine.detect(OpportunityInput(**defaults)).value


def test_explanation_has_all_expected_sections():
    o = _detect()
    exp = OpportunityExplainer().explain(o)

    assert exp.summary
    assert exp.liquidity_interpretation
    assert exp.risk_interpretation
    assert isinstance(exp.strengths, list)
    assert isinstance(exp.weaknesses, list)
    assert isinstance(exp.insights, list) and len(exp.insights) >= 1


def test_high_liquidity_item_gets_different_text_than_low_liquidity_item():
    """
    Prueba explícita del requisito "no texto genérico": dos ítems con
    liquidez muy distinta deben producir interpretaciones de liquidez
    con contenido distinto, no la misma plantilla.
    """
    high_liq = _detect(
        instrument_id=1, daily_volume=5_000_000, total_sell_volume_remain=2_000_000,
        total_buy_volume_remain=2_000_000, sell_order_count=80, buy_order_count=80,
    )
    low_liq = _detect(
        instrument_id=2, daily_volume=50, total_sell_volume_remain=10,
        total_buy_volume_remain=10, sell_order_count=2, buy_order_count=2,
    )

    exp_high = OpportunityExplainer().explain(high_liq)
    exp_low = OpportunityExplainer().explain(low_liq)

    assert exp_high.liquidity_interpretation != exp_low.liquidity_interpretation
    assert "rápida" in exp_high.liquidity_interpretation or "alta" in exp_high.liquidity_interpretation
    assert any(
        marker in exp_low.liquidity_interpretation
        for marker in ("lenta", "baja", "inexistente", "no estimable")
    ), "la interpretacion de liquidez baja deberia reflejar eso de alguna forma"


def test_extreme_spread_is_not_mislabeled_as_healthy():
    """
    Regresión de un bug real encontrado probando contra datos de
    producción: un ítem con buy=1, sell=122.5 (spread ~12150%) recibía
    la etiqueta "saludable" porque el componente normalizado (log-scaled)
    trata cualquier spread grande como favorable para el ROI. Un spread
    de esa magnitud debe describirse como señal de mercado fino, no
    como algo genuinamente bueno.
    """
    o = _detect(
        buy_price=Money(100, currency="ISK"), sell_price=Money(12250, currency="ISK"),
    )
    exp = OpportunityExplainer().explain(o)
    all_text = " ".join(exp.strengths + exp.weaknesses + exp.neutral_factors)

    assert "saludable" not in all_text.lower() or "mercado fino" in all_text.lower(), (
        "un spread extremo no debe llamarse 'saludable' sin matizar"
    )


def test_thin_order_book_triggers_specific_insight():
    o = _detect(sell_order_count=1, buy_order_count=2)
    exp = OpportunityExplainer().explain(o)

    assert any("order book fino" in i.lower() or "pocas órdenes" in i.lower() for i in exp.insights)


def test_summary_references_actual_score_value():
    o = _detect()
    exp = OpportunityExplainer().explain(o)

    assert f"{o.score:.1f}" in exp.summary


def test_no_evidence_liquidity_is_described_as_unknown_not_zero():
    """Ítem sin ningún día de historial (daily_volume=0) debe describirse
    como 'sin evidencia', no como liquidez confirmada en cero."""
    o = _detect(daily_volume=0)
    exp = OpportunityExplainer().explain(o)

    assert "sin ningún día" in exp.liquidity_interpretation.lower() or "sin evidencia" in exp.liquidity_interpretation.lower() or "inexistente" in exp.liquidity_interpretation.lower()
