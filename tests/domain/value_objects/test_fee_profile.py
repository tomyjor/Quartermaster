"""
Tests para FeeProfile (antes TaxProfile -- ver
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md, generalización de vocabulario).
"""

import pytest
from domain.value_objects.fee_profile import FeeProfile


def test_fee_profile_creation():
    fees = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)
    assert fees.entry_fee_rate == 0.03
    assert fees.total_sell_fee_rate == 0.066


def test_fee_profile_invalid_rate():
    with pytest.raises(ValueError):
        FeeProfile(entry_fee_rate=1.5, exit_fee_rate=0.0)
