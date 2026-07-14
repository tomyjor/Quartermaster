"""
Tests para el Value Object Money.
"""

import pytest
from domain.value_objects.money import Money


def test_money_creation():
    m = Money(15000, currency="ISK")  # 150 ISK
    assert m.amount_minor == 15000
    assert m.amount == 150.0
    assert str(m) == "150.00 ISK"


def test_money_addition():
    m1 = Money(10000, currency="ISK")
    m2 = Money(2500, currency="ISK")
    result = m1 + m2
    assert result.amount_minor == 12500


def test_money_allows_negative_amounts():
    """
    Money permite valores negativos DELIBERADAMENTE (ver docstring de
    Money.__post_init__): son necesarios para representar pérdidas netas,
    p.ej. ROIEngine.net_profit cuando sell_price < buy_price + fees (ver
    test_roi_engine_negative_profit). Este test reemplaza a uno anterior
    (`test_money_cannot_be_negative`) que aserteaba justo lo contrario y
    fallaba contra el comportamiento real -- quedó desactualizado de una
    decisión de diseño posterior y nunca se corrigió.
    """
    m = Money(-500, currency="ISK")
    assert m.amount_minor == -500
    assert m.amount == -5.0


def test_money_requires_currency():
    with pytest.raises(ValueError):
        Money(1000, currency="")


def test_money_has_no_silent_default_currency():
    """
    Regresión de un acoplamiento real encontrado: `currency` tenía
    default `"ISK"`, así que construir un Money sin pensar en la moneda
    asumía EVE en silencio -- no rompía nada, simplemente mentía en los
    datos. Ahora es un TypeError explícito, no un valor inventado.
    """
    with pytest.raises(TypeError):
        Money(1000)
