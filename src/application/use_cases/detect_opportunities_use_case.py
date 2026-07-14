"""
Application Use Case: DetectOpportunitiesUseCase

Orquesta la obtención de datos de mercado (vía los ports de dominio) y la
evaluación de cada type_id a través de OpportunityEngine. No contiene
lógica de negocio propia -- solo coordina repositorios + motor y arma un
reporte legible de qué se evaluó, qué se excluyó y por qué.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from domain.ports.market_repository import MarketRepository
from domain.ports.type_repository import TypeRepository
from domain.services.opportunity_engine import OpportunityEngine, OpportunityInput
from domain.value_objects.fee_profile import FeeProfile


@dataclass
class DetectOpportunitiesRequest:
    type_ids: List[int]
    region_id: int
    fee_profile: FeeProfile
    #: v2 (modularización multi-hub): antes ninguna llamada al
    #: repositorio de acá pasaba `location_id` explícito -- todas
    #: confiaban en el default de `SQLiteMarketRepository`
    #: (JITA_STATION_ID hardcodeado). Ver changelog de
    #: `ApiServices.__init__` para el riesgo concreto que esto evita
    #: (región de un hub emparejada con estación de otro).
    station_id: int = 60003760  # Jita, mismo default que siempre -- no rompe callers existentes


@dataclass
class DetectOpportunitiesResult:
    opportunities: list = field(default_factory=list)
    skipped: List[Tuple[int, str]] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    # Ranking completo (TODO lo que tuvo evidencia suficiente), ordenado por score desc,
    # SIN filtrar por min_score. Existe para que el modo Discovery pueda mostrar
    # "las mejores disponibles" aunque ninguna supere el umbral.
    ranked_all: list = field(default_factory=list)


class DetectOpportunitiesUseCase:
    def __init__(
        self,
        market_repository: MarketRepository,
        type_repository: TypeRepository,
        opportunity_engine: OpportunityEngine,
    ):
        self.market_repository = market_repository
        self.type_repository = type_repository
        self.opportunity_engine = opportunity_engine

    def execute(
        self,
        request: DetectOpportunitiesRequest,
        min_score: float = 55.0,
        max_results: int = 50,
    ) -> DetectOpportunitiesResult:
        """
        Evalúa cada type_id de la request y devuelve las oportunidades con
        score >= min_score (hasta max_results), además del ranking
        completo sin filtrar (`ranked_all`, usado por el modo Discovery
        como fallback) y la lista de ítems excluidos con motivo.

        v1.1 (fix de escala): usa `get_market_snapshots_bulk` /
        `get_names_bulk` si el repo los soporta -- un puñado de queries
        agregadas para TODOS los ítems, en vez de ~5-6 conexiones SQLite
        POR ÍTEM. A la escala de una watchlist manual (decenas de
        ítems) esto no se notaba; con Discovery post Smart Auto-Seed
        (miles de ítems activos en Jita) el patrón viejo significaba
        decenas de miles de conexiones para un solo request -- lento al
        punto de parecer colgado. Mantiene un fallback por ítem para
        repos que no implementen los métodos bulk (compatibilidad con
        el Port abstracto).
        """
        raw_results = []
        skipped: List[Tuple[int, str]] = []

        names_by_id: dict = {}
        if hasattr(self.type_repository, "get_names_bulk"):
            names_by_id = self.type_repository.get_names_bulk()

        snapshots_by_id: dict = {}
        if hasattr(self.market_repository, "get_market_snapshots_bulk"):
            snapshots_by_id = self.market_repository.get_market_snapshots_bulk(request.region_id, location_id=request.station_id)

        for type_id in request.type_ids:
            name = names_by_id.get(type_id)
            if name is None:
                type_info = self.type_repository.get(type_id)
                if type_info is None:
                    skipped.append((type_id, "type_id no existe en SDE"))
                    continue
                name = type_info.get("name", f"Type-{type_id}")

            snap = snapshots_by_id.get(type_id)
            if snap is None:
                snap = self._fetch_snapshot_single_item(type_id, request.region_id, request.station_id)
                if snap is None:
                    skipped.append((type_id, "sin order book completo (falta buy o sell)"))
                    continue

            if snap["sell_order_count"] == 0 and snap["buy_order_count"] == 0:
                skipped.append((type_id, "order book vacío"))
                continue

            opportunity_input = OpportunityInput(
                instrument_id=type_id,
                instrument_name=name,
                market_id=request.region_id,
                buy_price=snap["buy_price"],
                sell_price=snap["sell_price"],
                daily_volume=snap["daily_volume"],
                total_sell_volume_remain=snap["total_sell_volume_remain"],
                total_buy_volume_remain=snap["total_buy_volume_remain"],
                sell_order_count=snap["sell_order_count"],
                buy_order_count=snap["buy_order_count"],
                fee_profile=request.fee_profile,
            )

            try:
                result = self.opportunity_engine.detect(opportunity_input)
                raw_results.append(result)
            except Exception as e:
                skipped.append((type_id, f"error en motores: {str(e)}"))

        raw_results.sort(key=lambda r: r.value.score, reverse=True)

        filtered = [r for r in raw_results if r.value.score >= min_score]
        top = filtered[:max_results]

        summary = {
            "type_ids_evaluados": len(request.type_ids),
            "con_evidencia_suficiente": len(raw_results),
            "oportunidades": len(top),
            "min_score_usado": min_score,
        }

        return DetectOpportunitiesResult(
            opportunities=top,
            skipped=skipped,
            summary=summary,
            ranked_all=raw_results,
        )

    def _fetch_snapshot_single_item(self, type_id: int, region_id: int, station_id: int) -> Optional[dict]:
        """
        Fallback por ítem (1 conexión + varias queries), solo para repos
        que NO implementan `get_market_snapshots_bulk`. En el camino
        normal (SQLite real) esto no se llama nunca -- ver docstring de
        `execute()`.
        """
        snapshot = self.market_repository.get_current_snapshot(type_id, region_id, location_id=station_id)
        if snapshot is None:
            return None

        sell_count = buy_count = 0
        total_sell_remain = total_buy_remain = 0.0
        if hasattr(self.market_repository, "order_counts"):
            sell_count, buy_count = self.market_repository.order_counts(type_id, region_id, location_id=station_id)
        if hasattr(self.market_repository, "total_sell_volume_remain"):
            total_sell_remain = self.market_repository.total_sell_volume_remain(type_id, region_id, location_id=station_id)
        if hasattr(self.market_repository, "total_buy_volume_remain"):
            total_buy_remain = self.market_repository.total_buy_volume_remain(type_id, region_id, location_id=station_id)

        return {
            "buy_price": snapshot.buy_price,
            "sell_price": snapshot.sell_price,
            "daily_volume": snapshot.daily_volume,
            "sell_order_count": sell_count,
            "buy_order_count": buy_count,
            "total_sell_volume_remain": total_sell_remain,
            "total_buy_volume_remain": total_buy_remain,
        }
