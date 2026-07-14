"""
Tests para ROIEngine.
"""

import pytest
from domain.value_objects.money import Money
from domain.value_objects.fee_profile import FeeProfile
from domain.services.roi_engine import ROIEngine, ROIInput


def test_roi_engine_basic_calculation():
    engine = ROIEngine()

    tax = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)
    input_data = ROIInput(
        buy_price=Money(10000, currency="ISK"),   # 100 ISK
        sell_price=Money(15000, currency="ISK"),  # 150 ISK
        fee_profile=tax
    )

    result = engine.calculate(input_data)

    assert result.is_valid
    assert result.value.roi_percent > 0
    assert result.value.total_capital_required.amount_minor > 10000  # Incluye broker fee de compra


def test_roi_engine_negative_profit():
    engine = ROIEngine()

    tax = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)
    input_data = ROIInput(
        buy_price=Money(20000, currency="ISK"),
        sell_price=Money(18000, currency="ISK"),
        fee_profile=tax
    )

    result = engine.calculate(input_data)

    assert result.value.roi_percent < 0
