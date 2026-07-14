"""
Domain Port: MarketDataProvider

Etapa 2 de la generalización (ver docs/VISION.md y
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md §4/§7). Hasta ahora,
`infrastructure/esi/*` era "la" fuente de datos de mercado -- este port
la convierte en UNA implementación concreta de una abstracción
explícita, la primera de varias posibles (EVE ESI, Steam Community
Market, Binance, etc.).

Deliberadamente NO inventa una interfaz "ideal" desde cero -- las dos
firmas de acá abajo son un calco directo de lo que
`MarketOrdersImporter.import_full_region` y
`MarketHistoryImporter.import_bulk` YA hacían en producción (ver
`infrastructure/providers/eve_provider.py` para la implementación que
las envuelve sin reescribirlas). Diseñar el port a partir de un
comportamiento real que ya funciona, en vez de imaginar uno "genérico"
de antemano, es a propósito -- ver la trampa documentada en
ARCHITECTURE_V4_GENERIC_PLATFORM.md §5/§8: generalizar antes de tener
un segundo proveedor real casi siempre termina generalizando mal el
único caso que se conoce.

Comportamiento hacia afuera: SIN CAMBIOS. `SmartAutoSeedJob` sigue
usando los importadores directo por ahora -- migrarlo a consumir este
port es un paso aparte, deliberadamente pospuesto (ver
docs/ROADMAP_Y_PENDIENTES.md) para no mezclar "introducir la
abstracción" con "migrar el orquestador" en el mismo cambio.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional


class MarketDataProvider(ABC):
    """
    Fuente de datos de mercado para UN market_id -- hoy solo existe
    `EVEProvider` (envuelve infrastructure/esi/*). Cualquier proveedor
    futuro (Steam, Binance) implementa esta misma interfaz.
    """

    #: Identificador corto y estable del proveedor, ej. "eve_esi" --
    #: útil para logging/debugging cuando haya más de uno activo.
    provider_key: str

    @abstractmethod
    def sync_full_market_orders(
        self,
        market_id: int,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> Dict:
        """
        Trae el order book COMPLETO de `market_id` en una sola pasada
        paginada -- equivalente exacto a lo que hoy hace
        `MarketOrdersImporter.import_full_region`. `progress_callback`
        recibe (página_actual, total_páginas, órdenes_traídas_hasta_ahora).
        """
        raise NotImplementedError

    @abstractmethod
    def sync_instrument_history(
        self,
        market_id: int,
        instrument_ids: List[int],
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None,
    ) -> Dict:
        """
        Trae el historial de volumen de una lista de instrumentos --
        equivalente exacto a lo que hoy hace
        `MarketHistoryImporter.import_bulk`.
        """
        raise NotImplementedError
