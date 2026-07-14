"""
Infrastructure: SQLiteMarketRepository
Implementación real del port MarketRepository, contra
database/trader.db (tablas market_orders y market_history, pobladas por
el importador de ESI).

--------------------------------------------------------------------------
CHANGELOG v1.3 -> v1.4 (fix: "Jita" analizaba La Forge ENTERA, no Jita)
--------------------------------------------------------------------------
Encontrado comparando manualmente contra el cliente real del juego: un
comprador visible en "Kisogo VII - AIR Laboratories" (con alcance
"Región") aparecía mezclado en el análisis de "Jita" sin ninguna
distinción. Causa: `region_id=10000002` es el ID de **La Forge**, la
región completa (decenas de sistemas, cientos de estaciones) -- Jita es
UN sistema dentro de esa región, y "Jita 4-4" (Jita IV - Moon 4 -
Caldari Navy Assembly Plant, `location_id=60003760`) es UNA estación
dentro de ese sistema, la que concentra la inmensa mayoría del trading
real. `location_id` se guardaba en cada orden desde el principio (viene
de ESI tal cual), pero NUNCA se filtraba en ninguna query -- todo el
"análisis de Jita" en realidad promediaba/mezclaba órdenes de toda la
región. Medido contra datos reales: ~13.6% de las órdenes de una
muestra chica NO estaban en Jita 4-4 (con el sync completo de región,
probablemente bastante más).

Esto probablemente explica una porción de los "order books fantasma"
que se venían investigando: no todos eran órdenes aisladas/trolls,
algunos eran órdenes reales pero de otra punta del mapa, imposibles de
ejecutar convenientemente por alguien operando específicamente en Jita.

v1.4 filtra por `location_id = JITA_STATION_ID` en todas las queries que
tienen esa columna disponible (todo lo que viene de `market_orders`).
`market_history` es la única excepción real: ESI no tiene un endpoint de
historial por estación, solo por región -- `daily_volume` sigue siendo
inevitablemente regional, no hay forma de acotarlo más sin que ESI lo
permita. Documentado explícitamente en `get_daily_volume`.

Decisión de diseño deliberada: si no hay órdenes o historia para un
type_id/región, los métodos devuelven None / 0.0 explícitamente, NUNCA
un valor por defecto inventado (el use case anterior hacía
`item.get("daily_volume", 50000)` -- eso es exactamente el tipo de dato
fabricado que el RFC-000 prohíbe). Es responsabilidad del caller decidir
qué hacer con la ausencia de evidencia (típicamente: excluir el ítem del
análisis, no fingar que tiene volumen).
"""

import sqlite3
from shared.db import connect_db
from pathlib import Path
from typing import Optional

from domain.ports.market_repository import MarketRepository, MarketSnapshot
from domain.value_objects.money import Money
from shared.paths import DEFAULT_DB_PATH


class SQLiteMarketRepository(MarketRepository):

    #: Jita IV - Moon 4 - Caldari Navy Assembly Plant -- la estación
    #: real donde pasa la inmensa mayoría del trading de "Jita" (lo que
    #: cualquier jugador quiere decir cuando dice "precio de Jita"). Ver
    #: changelog v1.4 del módulo: antes NADA filtraba por acá, se
    #: analizaba la región de La Forge completa.
    JITA_STATION_ID = 60003760

    #: Cantidad de días recientes de market_history sobre los que se
    #: promedia get_daily_volume(). v1.1: antes se usaba solo el día más
    #: reciente, una muestra ruidosa -- un solo día atípicamente alto o
    #: bajo distorsionaba directamente el score de liquidez del ítem
    #: (ver LiquidityEngine v1.4). Promediar una ventana da una lectura
    #: más estable sin dejar de ser honesto: si hay menos de N días de
    #: historia, se promedia sobre los que haya; si no hay ninguno, se
    #: sigue devolviendo 0.0 explícito.
    DAILY_VOLUME_WINDOW_DAYS = 7

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_current_snapshot(
        self, type_id: int, region_id: int, location_id: int = JITA_STATION_ID
    ) -> Optional[MarketSnapshot]:
        conn = self._connect()
        best_sell = conn.execute(
            "SELECT MIN(price) AS p FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=0",
            (type_id, region_id, location_id),
        ).fetchone()["p"]
        best_buy = conn.execute(
            "SELECT MAX(price) AS p FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=1",
            (type_id, region_id, location_id),
        ).fetchone()["p"]
        conn.close()

        # Sin las dos puntas del order book no hay spread real -- no
        # inventamos una de las dos, devolvemos None y que el caller decida.
        if best_sell is None or best_buy is None:
            return None

        daily_volume = self.get_daily_volume(type_id, region_id)

        return MarketSnapshot(
            type_id=type_id,
            buy_price=Money(int(best_buy * 100), currency="ISK"),
            sell_price=Money(int(best_sell * 100), currency="ISK"),
            daily_volume=daily_volume,
        )

    def get_daily_volume(self, type_id: int, region_id: int) -> float:
        """
        Volumen diario "representativo" para liquidez, promediado sobre
        los últimos `DAILY_VOLUME_WINDOW_DAYS` días disponibles de
        market_history (ver docstring de la constante). 0.0 explícito si
        no hay ningún día de historia -- "no hay evidencia de volumen
        reciente", nunca "asumimos un volumen típico".

        ⚠️ Esto es REGIONAL (La Forge entera), no de Jita específicamente
        -- a diferencia de los métodos basados en `market_orders`
        (que sí filtran por `JITA_STATION_ID` desde v1.4), ESI no tiene
        un endpoint de historial de volumen por estación, solo por
        región. Es una limitación real de la API de ESI, no una que
        podamos evitar acá -- el volumen diario puede estar levemente
        sobreestimado respecto al que realmente pasa por Jita 4-4 si hay
        trading significativo en otras estaciones de la región para ese
        ítem.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT volume FROM market_history "
            "WHERE type_id=? AND region_id=? ORDER BY date DESC LIMIT ?",
            (type_id, region_id, self.DAILY_VOLUME_WINDOW_DAYS),
        ).fetchall()
        conn.close()

        volumes = [r["volume"] for r in rows if r["volume"] is not None]
        if not volumes:
            return 0.0
        return sum(volumes) / len(volumes)

    def order_counts(
        self, type_id: int, region_id: int, location_id: int = JITA_STATION_ID
    ) -> tuple[int, int]:
        """(sell_order_count, buy_order_count). Método de infraestructura,
        no forma parte del port abstracto -- lo necesita el use case para
        alimentar CompetitionEngine."""
        conn = self._connect()
        sell_count = conn.execute(
            "SELECT COUNT(*) AS n FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=0",
            (type_id, region_id, location_id),
        ).fetchone()["n"]
        buy_count = conn.execute(
            "SELECT COUNT(*) AS n FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=1",
            (type_id, region_id, location_id),
        ).fetchone()["n"]
        conn.close()
        return sell_count, buy_count

    def total_sell_volume_remain(
        self, type_id: int, region_id: int, location_id: int = JITA_STATION_ID
    ) -> float:
        """Suma de volume_remain de las órdenes de VENTA activas en Jita 4-4."""
        conn = self._connect()
        row = conn.execute(
            "SELECT COALESCE(SUM(volume_remain), 0) AS v FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=0",
            (type_id, region_id, location_id),
        ).fetchone()
        conn.close()
        return float(row["v"])

    def total_buy_volume_remain(
        self, type_id: int, region_id: int, location_id: int = JITA_STATION_ID
    ) -> float:
        """
        Suma de volume_remain de las órdenes de COMPRA activas en Jita 4-4.

        Análogo a total_sell_volume_remain. Necesario para que
        CompetitionEngine reciba un `total_buy_volume` real -- antes
        OpportunityEngine lo pasaba hardcodeado en 0.0, lo que dejaba a
        `market_density` ciego a la mitad del order book.
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT COALESCE(SUM(volume_remain), 0) AS v FROM market_orders "
            "WHERE type_id=? AND region_id=? AND location_id=? AND is_buy_order=1",
            (type_id, region_id, location_id),
        ).fetchone()
        conn.close()
        return float(row["v"])

    def get_active_type_ids(
        self, region_id: int, limit: int = 30000, location_id: int = JITA_STATION_ID
    ) -> list[int]:
        """
        type_ids con order book bidireccional (compra Y venta) activo en
        Jita 4-4 específicamente, ordenados por más recientemente
        actualizados primero.

        v1.4: filtra por `location_id` (Jita 4-4) además de `region_id`
        -- ver changelog del módulo. Antes cubría La Forge entera.

        Formaliza como método de repositorio lo que antes era SQL inline
        en el Discovery mode de `app.py` (GROUP BY/HAVING). Con el sync
        completo de región (`MarketOrdersImporter.import_full_region`),
        esta consulta es la fuente de verdad de "qué tiene actividad real
        en Jita ahora mismo" -- ya no depende de qué esté trackeado a
        mano, cubre todo lo que el último sync haya traído.
        """
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT type_id, MAX(fetched_at) as last_fetch
            FROM market_orders
            WHERE region_id = ? AND location_id = ?
            GROUP BY type_id
            HAVING SUM(CASE WHEN is_buy_order = 1 THEN 1 ELSE 0 END) > 0
               AND SUM(CASE WHEN is_buy_order = 0 THEN 1 ELSE 0 END) > 0
            ORDER BY last_fetch DESC
            LIMIT ?
            """,
            (region_id, location_id, limit),
        ).fetchall()
        conn.close()
        return [r["type_id"] for r in rows]

    def get_market_snapshots_bulk(
        self, region_id: int, location_id: int = JITA_STATION_ID
    ) -> dict:
        """
        Order book agregado (mejor precio, conteos de órdenes, volumen
        remanente, volumen diario promedio) para TODOS los type_ids con
        actividad en Jita 4-4 específicamente, en un puñado de queries de
        agregación -- no una consulta por ítem.

        v1.4: filtra por `location_id` (Jita 4-4) en las queries de
        `market_orders` -- ver changelog del módulo. `daily_volume` sigue
        siendo regional (limitación real de ESI, ver `get_daily_volume`).

        v1.2 (fix de escala): `DetectOpportunitiesUseCase` hacía ~5-6
        conexiones SQLite POR ÍTEM (snapshot, daily_volume, order_counts,
        total_sell/buy_volume_remain, más el nombre desde
        TypeRepository). A la escala de 40 ítems trackeados a mano eso
        era imperceptible; con el sync completo de región (Smart
        Auto-Seed, ~19.000 ítems activos en una corrida real), eran
        decenas de miles de conexiones para un solo request HTTP --
        perceptiblemente lento / percibido como colgado en la práctica.
        Esto reemplaza eso con un puñado de queries `GROUP BY type_id`;
        el caller filtra en memoria a los type_ids que realmente
        necesita (rápido, sin I/O extra).

        Devuelve {type_id: {buy_price: Money, sell_price: Money,
        sell_order_count, buy_order_count, total_sell_volume_remain,
        total_buy_volume_remain, daily_volume}}. Ítems sin book
        bidireccional en Jita 4-4 (falta buy o sell ahí) NO aparecen en
        el resultado -- mismo criterio de exclusión que
        `get_current_snapshot`.
        """
        conn = self._connect()

        order_rows = conn.execute(
            """
            SELECT
                type_id,
                MIN(CASE WHEN is_buy_order = 0 THEN price END) AS best_sell,
                MAX(CASE WHEN is_buy_order = 1 THEN price END) AS best_buy,
                SUM(CASE WHEN is_buy_order = 0 THEN 1 ELSE 0 END) AS sell_order_count,
                SUM(CASE WHEN is_buy_order = 1 THEN 1 ELSE 0 END) AS buy_order_count,
                SUM(CASE WHEN is_buy_order = 0 THEN volume_remain ELSE 0 END) AS total_sell_volume_remain,
                SUM(CASE WHEN is_buy_order = 1 THEN volume_remain ELSE 0 END) AS total_buy_volume_remain
            FROM market_orders
            WHERE region_id = ? AND location_id = ?
            GROUP BY type_id
            """,
            (region_id, location_id),
        ).fetchall()

        snapshots = {}
        for r in order_rows:
            if r["best_sell"] is None or r["best_buy"] is None:
                continue  # sin book bidireccional en Jita 4-4 -- mismo criterio que get_current_snapshot
            snapshots[r["type_id"]] = {
                "buy_price": Money(int(round(r["best_buy"] * 100)), currency="ISK"),
                "sell_price": Money(int(round(r["best_sell"] * 100)), currency="ISK"),
                "sell_order_count": r["sell_order_count"],
                "buy_order_count": r["buy_order_count"],
                "total_sell_volume_remain": float(r["total_sell_volume_remain"] or 0.0),
                "total_buy_volume_remain": float(r["total_buy_volume_remain"] or 0.0),
                "daily_volume": 0.0,
            }

        # Promedio de los últimos DAILY_VOLUME_WINDOW_DAYS días por
        # type_id, en una sola query con window function (mismo criterio
        # que get_daily_volume, pero para todos los ítems a la vez).
        # Sigue siendo REGIONAL -- ver docstring de get_daily_volume.
        history_rows = conn.execute(
            """
            SELECT type_id, AVG(volume) AS avg_volume FROM (
                SELECT type_id, volume,
                       ROW_NUMBER() OVER (PARTITION BY type_id ORDER BY date DESC) AS rn
                FROM market_history
                WHERE region_id = ?
            )
            WHERE rn <= ?
            GROUP BY type_id
            """,
            (region_id, self.DAILY_VOLUME_WINDOW_DAYS),
        ).fetchall()

        for r in history_rows:
            if r["type_id"] in snapshots:
                snapshots[r["type_id"]]["daily_volume"] = float(r["avg_volume"] or 0.0)

        conn.close()
        return snapshots
