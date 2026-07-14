"""
Domain Value Object: TradeHub

Registro de los hubs de trading reales que la herramienta soporta.
Curado a propósito -- EVE tiene ~100 regiones, la enorme mayoría sin
actividad comercial real. Modularizar "por región" no significa
soportar las 100; significa que el sistema deje de asumir una única
región hardcodeada (Jita) y pueda operar sobre cualquiera de los
handful de hubs donde realmente se comercia en volumen.

Cada hub es (region_id, station_id) -- NUNCA solo region_id. La
lección de la sesión donde se encontró el bug de "Jita vs. The Forge
entera" aplica igual acá: cada hub tiene que anclarse a SU estación
principal específica, nunca a la región completa, o se repite el mismo
error de mezclar order books de lugares que no están conectados sin
transporte.

IDs verificados contra fuentes independientes reales (Adam4EVE --
listado de estaciones sacado directo del SDE de CCP --, DOTLAN
EveMaps, zkillboard, y las URLs de mercado de EVE Workbench, que
codifican region_id/station_id en la ruta): los 5 hubs confirmados
exactos, region_id + station_id coinciden en las 4 fuentes cruzadas.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class TradeHub:
    key: str  # identificador corto y estable, ej. "jita" -- usado en URLs/API, nunca cambia aunque el nombre de display sí
    display_name: str
    region_id: int
    region_name: str
    station_id: int
    station_name: str


#: Los 5 hubs de trading de mayor volumen de EVE Online. Jita primero y
#: marcado como default -- es el que ya existía, mantiene el
#: comportamiento actual sin cambios para quien no elija otro
#: explícitamente.
TRADE_HUBS: Dict[str, TradeHub] = {
    "jita": TradeHub(
        key="jita", display_name="Jita",
        region_id=10000002, region_name="The Forge",
        station_id=60003760, station_name="Jita IV - Moon 4 - Caldari Navy Assembly Plant",
    ),
    "amarr": TradeHub(
        key="amarr", display_name="Amarr",
        region_id=10000043, region_name="Domain",
        station_id=60008494, station_name="Amarr VIII (Oris) - Emperor Family Academy",
    ),
    "dodixie": TradeHub(
        key="dodixie", display_name="Dodixie",
        region_id=10000032, region_name="Sinq Laison",
        station_id=60011866, station_name="Dodixie IX - Moon 20 - Federation Navy Assembly Plant",
    ),
    "rens": TradeHub(
        key="rens", display_name="Rens",
        region_id=10000030, region_name="Heimatar",
        station_id=60004588, station_name="Rens VI - Moon 8 - Brutor Tribe Treasury",
    ),
    "hek": TradeHub(
        key="hek", display_name="Hek",
        region_id=10000042, region_name="Metropolis",
        station_id=60005686, station_name="Hek VIII - Moon 12 - Boundless Creation Factory",
    ),
}

DEFAULT_HUB_KEY = "jita"


def get_hub(key: Optional[str]) -> TradeHub:
    """
    Devuelve el TradeHub para `key`, o el default (Jita) si `key` es
    None -- nunca None silencioso ni KeyError críptico. `key` inválido
    (no está en TRADE_HUBS) sí levanta ValueError explícito: preferible
    a asumir un hub cualquiera cuando el caller pidió uno que no existe.
    """
    if key is None:
        return TRADE_HUBS[DEFAULT_HUB_KEY]
    if key not in TRADE_HUBS:
        valid = ", ".join(sorted(TRADE_HUBS.keys()))
        raise ValueError(f"Hub de trading desconocido: {key!r}. Válidos: {valid}")
    return TRADE_HUBS[key]


def get_hub_by_region_id(region_id: int) -> Optional[TradeHub]:
    """Búsqueda inversa -- útil cuando el caller solo tiene un region_id (ej. de una fila de la DB) y necesita el hub completo."""
    for hub in TRADE_HUBS.values():
        if hub.region_id == region_id:
            return hub
    return None
