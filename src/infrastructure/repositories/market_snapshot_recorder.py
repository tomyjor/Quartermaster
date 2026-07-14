"""
Infrastructure: MarketSnapshotRecorder

Escribe en `market_order_snapshots` -- tabla que ya existía en el
schema pero nadie la usaba (0 filas en producción, código muerto). La
idea original era exactamente la correcta: guardar el estado del order
book de Jita en el tiempo para poder medir movimiento REAL ahí, no
solo confiar en `market_history` (que ESI solo entrega a nivel de
región -- ver `SQLiteMarketRepository.get_daily_volume`).

Nace de un reporte real: ítems con `liquidez 100` cuyas órdenes de
compra del usuario seguían casi intactas un día después. La causa
raíz: `daily_volume` (mitad de la fórmula de liquidez) es regional, así
que un ítem puede parecer líquido por actividad en OTRAS estaciones de
La Forge, mientras que en Jita 4-4 específicamente casi no se mueve.
La profundidad del book (`total_sell_volume_remain`) ya está bien
filtrada a Jita desde v1.4 -- lo que falta es un volumen TAMBIÉN
filtrado a Jita, y esto es la base para construirlo: comparando cómo
cambia `total_volume_remain` entre snapshots consecutivos, se puede
derivar cuánto se movió de verdad en Jita, sin depender de la región
entera.

⚠️ Necesita DÍAS de snapshots acumulados para ser útil -- una sola
corrida no alcanza para calcular ningún delta. Hasta entonces,
`get_jita_turnover_proxy()` devuelve None explícito (nunca inventa un
número con un solo punto de datos).
"""

import sqlite3
from shared.db import connect_db
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from shared.paths import DEFAULT_DB_PATH

JITA_STATION_ID = 60003760


class MarketSnapshotRecorder:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_snapshot(
        self, region_id: int, station_id: int = JITA_STATION_ID, snapshot_date: Optional[str] = None,
    ) -> int:
        """
        Guarda un snapshot de HOY (o `snapshot_date` si se pasa, para
        tests) del estado del book en `station_id` (default Jita, mismo
        comportamiento de siempre para callers que no pasan nada
        nuevo), uno por type_id con orden activa. `INSERT OR REPLACE`
        -- si ya existe un snapshot para el mismo (region_id, type_id,
        fecha), lo pisa; correr esto más de una vez el mismo día no
        duplica ni acumula basura.

        Se llama al final de cada Smart Auto-Seed (ver
        `SmartAutoSeedJob.run`) -- así se acumula un punto por día sin
        tener que agregar un job separado.

        v2 (modularización multi-hub): antes `station_id` estaba
        hardcodeado a Jita DENTRO de la query -- correr esto para
        cualquier otro hub hubiera seguido snapshoteando la estación de
        Jita sin importar qué `region_id` se pasara. Ahora es un
        parámetro real, coherente con el resto del repositorio.

        Devuelve la cantidad de type_ids snapshoteados.
        """
        snapshot_date = snapshot_date or date.today().isoformat()

        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                type_id,
                SUM(CASE WHEN is_buy_order = 1 THEN 1 ELSE 0 END) AS buy_order_count,
                SUM(CASE WHEN is_buy_order = 0 THEN 1 ELSE 0 END) AS sell_order_count,
                MAX(CASE WHEN is_buy_order = 1 THEN price END) AS best_buy_price,
                MIN(CASE WHEN is_buy_order = 0 THEN price END) AS best_sell_price,
                SUM(volume_remain) AS total_volume_remain
            FROM market_orders
            WHERE region_id = ? AND location_id = ?
            GROUP BY type_id
            """,
            (region_id, station_id),
        ).fetchall()

        conn.executemany(
            """
            INSERT OR REPLACE INTO market_order_snapshots
            (region_id, type_id, snapshot_date, buy_order_count, sell_order_count,
             best_buy_price, best_sell_price, total_volume_remain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (region_id, r["type_id"], snapshot_date, r["buy_order_count"], r["sell_order_count"],
                 r["best_buy_price"], r["best_sell_price"], r["total_volume_remain"])
                for r in rows
            ],
        )
        conn.commit()
        conn.close()
        return len(rows)

    def get_jita_turnover_proxy(
        self, region_id: int, type_id: int, lookback_days: int = 7,
    ) -> Optional[float]:
        """
        Estima cuánto se movió REALMENTE en Jita para este ítem,
        comparando `total_volume_remain` entre el snapshot más antiguo
        y el más reciente disponibles dentro de `lookback_days`. Una
        caída de volumen remanente (sin que se hayan agregado más
        órdenes) es evidencia de ventas/compras reales ejecutándose --
        a diferencia de `daily_volume` (regional), esto es 100% Jita.

        Devuelve None si hay menos de 2 snapshots en la ventana -- no
        hay forma honesta de estimar un delta con un solo punto. El
        caller debe tratar None como "sin evidencia todavía", no como 0.

        ⚠️ Es una ESTIMACIÓN, no un conteo exacto de trades: si entre
        snapshots también se cancelan o agregan órdenes nuevas, eso se
        mezcla con las que se ejecutaron de verdad. Con snapshots
        diarios y suficientes días acumulados, el ruido de
        cancelaciones puntuales se diluye -- pero es una señal
        complementaria, no un reemplazo exacto del volumen real.
        """
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

        conn = self._connect()
        rows = conn.execute(
            """
            SELECT snapshot_date, total_volume_remain FROM market_order_snapshots
            WHERE region_id = ? AND type_id = ? AND snapshot_date >= ?
            ORDER BY snapshot_date ASC
            """,
            (region_id, type_id, cutoff),
        ).fetchall()
        conn.close()

        if len(rows) < 2:
            return None

        oldest, newest = rows[0], rows[-1]
        if oldest["total_volume_remain"] is None or newest["total_volume_remain"] is None:
            return None

        delta = oldest["total_volume_remain"] - newest["total_volume_remain"]
        # Delta negativo (el book CRECIÓ, no se vendió nada neto) se
        # reporta como 0 -- "no hay evidencia de turnover", no un
        # número negativo sin sentido para una fórmula de liquidez.
        return max(0.0, float(delta))
