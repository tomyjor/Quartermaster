"""
Infrastructure: EVEProvider

Primera implementación real de `domain.ports.market_data_provider.MarketDataProvider`.
ENVUELVE los importadores existentes (`MarketOrdersImporter`,
`MarketHistoryImporter`) por composición -- no los reescribe, no
cambia su lógica interna en absoluto. El único trabajo acá es traducir
la firma del port a las llamadas que esos importadores ya exponían.

Por qué por composición y no por herencia/rename: los importadores ya
están probados en producción (Smart Auto-Seed corriendo real, más de
una corrida). Envolver en vez de tocar minimiza el riesgo de este paso
-- exactamente la disciplina que pide Etapa 2 en
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md ("el comportamiento hacia
afuera no cambia").

`SmartAutoSeedJob` TODAVÍA NO usa esto -- sigue llamando a los
importadores directo. Migrarlo es un paso aparte, deliberadamente
pospuesto (ver docstring del port).
"""

from typing import Callable, Dict, List, Optional

from domain.ports.market_data_provider import MarketDataProvider
from infrastructure.esi.market_orders_importer import MarketOrdersImporter
from infrastructure.esi.market_history_importer import MarketHistoryImporter


class EVEProvider(MarketDataProvider):
    provider_key = "eve_esi"

    def __init__(self, db_path: str = "database/trader.db"):
        self.db_path = db_path
        self._orders_importer = MarketOrdersImporter(db_path=db_path)
        self._history_importer = MarketHistoryImporter(db_path=db_path)

    def sync_full_market_orders(
        self,
        market_id: int,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> Dict:
        """Delega 1:1 a `MarketOrdersImporter.import_full_region` -- `market_id` acá ES el `region_id` de EVE."""
        return self._orders_importer.import_full_region(market_id, progress_callback=progress_callback)

    def sync_instrument_history(
        self,
        market_id: int,
        instrument_ids: List[int],
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None,
    ) -> Dict:
        """Delega 1:1 a `MarketHistoryImporter.import_bulk`."""
        return self._history_importer.import_bulk(
            market_id, instrument_ids, progress_callback=progress_callback
        )
