"""
Tests para EVEProvider -- primera implementación real de
domain.ports.market_data_provider.MarketDataProvider (Etapa 2 de la
generalización, ver docs/VISION.md).

Confirma que el adaptador delega 1:1 a los importadores existentes
(sin reescribirlos, sin cambiar su comportamiento) y que efectivamente
implementa el port -- ambas cosas son lo único que Etapa 2 promete.
"""

from domain.ports.market_data_provider import MarketDataProvider
from infrastructure.providers.eve_provider import EVEProvider


def test_eve_provider_implements_the_port():
    provider = EVEProvider(db_path="database/trader.db")
    assert isinstance(provider, MarketDataProvider)


def test_eve_provider_has_stable_provider_key():
    assert EVEProvider.provider_key == "eve_esi"


def test_sync_full_market_orders_delegates_with_exact_arguments():
    provider = EVEProvider(db_path="database/trader.db")
    calls = []

    class _FakeOrdersImporter:
        def import_full_region(self, region_id, progress_callback=None):
            calls.append(("orders", region_id, progress_callback))
            return {"order_count": 42}

    provider._orders_importer = _FakeOrdersImporter()
    cb = lambda a, b, c: None

    result = provider.sync_full_market_orders(10000002, progress_callback=cb)

    assert result == {"order_count": 42}
    assert calls == [("orders", 10000002, cb)]


def test_sync_instrument_history_delegates_with_exact_arguments():
    provider = EVEProvider(db_path="database/trader.db")
    calls = []

    class _FakeHistoryImporter:
        def import_bulk(self, region_id, type_ids, progress_callback=None):
            calls.append(("history", region_id, type_ids, progress_callback))
            return {"success": 3, "failed": []}

    provider._history_importer = _FakeHistoryImporter()

    result = provider.sync_instrument_history(10000002, [34, 35, 36])

    assert result == {"success": 3, "failed": []}
    assert calls == [("history", 10000002, [34, 35, 36], None)]


def test_cannot_instantiate_the_abstract_port_directly():
    """El port es un ABC -- confirma que sigue exigiendo que cualquier implementación futura defina los dos métodos."""
    try:
        MarketDataProvider()
        assert False, "MarketDataProvider no debería poder instanciarse directo, es un ABC"
    except TypeError:
        pass
