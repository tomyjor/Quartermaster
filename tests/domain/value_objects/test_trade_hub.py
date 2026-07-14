"""
Tests para el registro de TradeHub. Los 5 hubs (region_id + station_id)
están verificados contra fuentes independientes reales -- ver
docstring de domain/value_objects/trade_hub.py.
"""

import pytest

from domain.value_objects.trade_hub import get_hub, get_hub_by_region_id, TRADE_HUBS, DEFAULT_HUB_KEY


def test_default_hub_is_jita_preserving_current_behavior():
    """Sin argumento, debe devolver Jita -- preserva el comportamiento de antes de la modularización."""
    hub = get_hub(None)
    assert hub.key == "jita"
    assert hub.region_id == 10000002
    assert hub.station_id == 60003760


def test_all_five_hubs_have_unique_region_and_station_ids():
    region_ids = [h.region_id for h in TRADE_HUBS.values()]
    station_ids = [h.station_id for h in TRADE_HUBS.values()]
    assert len(TRADE_HUBS) == 5
    assert len(set(region_ids)) == 5, "hay region_id duplicados entre hubs"
    assert len(set(station_ids)) == 5, "hay station_id duplicados entre hubs"


def test_get_hub_by_valid_key():
    hub = get_hub("amarr")
    assert hub.display_name == "Amarr"
    assert hub.key == "amarr"


def test_get_hub_by_invalid_key_raises_clear_error():
    with pytest.raises(ValueError):
        get_hub("no-existe")


def test_get_hub_by_region_id_reverse_lookup():
    hub = get_hub_by_region_id(10000002)
    assert hub is not None
    assert hub.key == "jita"


def test_get_hub_by_region_id_returns_none_for_unknown_region():
    assert get_hub_by_region_id(999999) is None


def test_default_hub_key_points_to_a_real_hub():
    assert DEFAULT_HUB_KEY in TRADE_HUBS
