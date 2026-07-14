"""
Infrastructure: SQLiteTypeRepository
Implementación real del port TypeRepository, contra database/trader.db
(la base que ya tenés poblada con 52,744 types del SDE de CCP).
"""

import sqlite3
from shared.db import connect_db
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timezone

from domain.ports.type_repository import TypeRepository
from shared.paths import DEFAULT_DB_PATH

JITA_REGION_ID = 10000002


class SQLiteTypeRepository(TypeRepository):

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, table_name: str) -> bool:
        """Verifica si una tabla existe en la base de datos (para queries defensivas)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        conn.close()
        return row is not None

    def get(self, type_id: int) -> Optional[Dict]:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, name, group_id, category_id, market_group_id, "
            "volume, base_price, published FROM item_types WHERE id=?",
            (type_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_name(self, type_id: int) -> Optional[str]:
        item = self.get(type_id)
        return item["name"] if item else None

    def get_names_bulk(self) -> Dict[int, str]:
        """
        Nombre de TODOS los ítems del SDE, en una sola query.

        Usado por `DetectOpportunitiesUseCase` para evitar una conexión
        SQLite por ítem cuando hay que resolver nombres para miles de
        type_ids a la vez -- ver changelog en
        `SQLiteMarketRepository.get_market_snapshots_bulk` para el
        mismo problema del lado de market data. La tabla `item_types`
        es chica (~50k filas de texto), traerla completa es más rápido
        que miles de conexiones individuales.
        """
        conn = self._connect()
        rows = conn.execute("SELECT id, name FROM item_types").fetchall()
        conn.close()
        return {r["id"]: r["name"] for r in rows}

    def search(self, term: str, limit: int = 20) -> List[Dict]:
        """
        No es parte del port abstracto (el dominio no necesita "buscar",
        solo "obtener por id"), pero es un método de infraestructura
        práctico para poblar tracked_types desde un nombre en vez de un id
        a mano. Ver scripts/track_type.py y la GUI.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, name FROM item_types "
            "WHERE name LIKE ? AND published = 1 ORDER BY name LIMIT ?",
            (f"%{term.strip()}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def tracked_type_ids(self, user_id: int, region_id: int) -> List[int]:
        """
        v3 (modularización multi-hub): `region_id` ahora es obligatorio
        -- un type_id trackeado en Jita y el mismo type_id trackeado en
        Amarr son filas DISTINTAS (precios distintos, sentido distinto
        para el usuario). Listar "todo lo trackeado" sin especificar
        hub ya no es una operación válida.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT type_id FROM tracked_types WHERE user_id = ? AND region_id = ?",
            (user_id, region_id),
        ).fetchall()
        conn.close()
        return [r["type_id"] for r in rows]

    def track(self, user_id: int, type_id: int, region_id: int, reason: str | None = None) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR IGNORE INTO tracked_types (user_id, type_id, region_id, added_at, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, type_id, region_id, datetime.now(timezone.utc).isoformat(), reason),
        )
        conn.commit()
        conn.close()

    def untrack(self, user_id: int, type_id: int, region_id: int) -> None:
        """
        Elimina un type_id de la watchlist de ESTE usuario, en ESTE hub
        únicamente -- destrackear "Tritanium" en Jita no debe tocar el
        "Tritanium" trackeado en Amarr, son entradas independientes.

        v2 (multi-tenancy): antes tenía un flag `also_cleanup_orders`
        que borraba el snapshot de `market_orders` del ítem al
        destrackearlo -- tenía sentido cuando `tracked_types` era la
        ÚNICA fuente de "qué sincronizar". Desde el Smart Auto-Seed,
        `market_orders` es un recurso COMPARTIDO por todos los usuarios
        (alimenta Discovery para todo el mundo, no solo para quien
        trackeó el ítem) -- borrarlo cuando un usuario destrackea algo
        le rompería los datos a cualquier otro usuario mirando ese
        mismo ítem. Sacado por completo, no solo desactivado por
        default, para que no quede la tentación de reactivarlo sin
        pensar en esto de nuevo.
        """
        conn = self._connect()
        conn.execute(
            "DELETE FROM tracked_types WHERE user_id = ? AND type_id = ? AND region_id = ?",
            (user_id, type_id, region_id),
        )
        conn.commit()
        conn.close()

    def untrack_many(self, user_id: int, type_ids: list[int], region_id: int) -> int:
        """
        Elimina VARIOS type_ids de la watchlist de este usuario EN ESTE
        HUB, en una sola transacción SQL, sin loop Python.

        v1.1: antes, quitar varios ítems (o "todos") se hacía llamando
        untrack() en un loop -- una conexión SQLite nueva por ítem
        (open/execute/commit/close). Con watchlists grandes (cientos de
        ítems) ese loop podía tardar lo suficiente como para que el
        usuario, pensando que el botón no respondió, clickeara de nuevo
        mientras el loop anterior seguía corriendo. Streamlit cancela el
        script en curso y arranca uno nuevo ante cualquier interacción
        nueva, así que cada click de más cortaba el loop a la mitad --
        el síntoma visible era "borra de a tandas" en vez de todo junto.
        Con una sola sentencia SQL atómica, no hay Python loop que
        interrumpir: o se ejecuta completa, o no se ejecuta.

        Devuelve la cantidad de filas realmente borradas.
        """
        if not type_ids:
            return 0

        conn = self._connect()
        placeholders = ",".join("?" * len(type_ids))
        cursor = conn.execute(
            f"DELETE FROM tracked_types WHERE user_id = ? AND region_id = ? AND type_id IN ({placeholders})",
            (user_id, region_id, *type_ids),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    def untrack_all(self, user_id: int, region_id: int) -> int:
        """
        Elimina TODA la watchlist de este usuario EN ESTE HUB (y solo en
        este hub -- lo trackeado en otros hubs no se toca) en una sola
        transacción SQL. Ver `untrack_many` para el razonamiento
        completo del fix de atomicidad.
        Devuelve la cantidad de filas borradas.
        """
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM tracked_types WHERE user_id = ? AND region_id = ?", (user_id, region_id)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    def is_tracked(self, user_id: int, type_id: int, region_id: int) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM tracked_types WHERE user_id = ? AND type_id = ? AND region_id = ?",
            (user_id, type_id, region_id),
        ).fetchone()
        conn.close()
        return row is not None


    # ============================================================
    # NUEVOS MÉTODOS PARA NAVEGACIÓN POR CATEGORÍA / GRUPO (EVE SDE)
    # ============================================================

    def get_distinct_categories(self) -> List[Dict]:
        """Devuelve TODAS las categorías con items publicados.
        Usa nombres reales de la tabla 'categories' si existe, sino usa nombre de item como fallback."""
        conn = self._connect()

        if self._table_exists("categories"):
            query = """
                SELECT 
                    it.category_id,
                    COUNT(*) as item_count,
                    COALESCE(cat.name, 
                        (SELECT name FROM item_types i2 
                         WHERE i2.category_id = it.category_id AND i2.published=1 
                         ORDER BY LENGTH(i2.name) ASC LIMIT 1)
                    ) as name
                FROM item_types it
                LEFT JOIN categories cat ON cat.id = it.category_id
                WHERE it.published = 1 AND it.category_id IS NOT NULL
                GROUP BY it.category_id
                ORDER BY it.category_id ASC
            """
        else:
            # Fallback seguro si todavía no se importó el SDE
            query = """
                SELECT 
                    category_id,
                    COUNT(*) as item_count,
                    MIN(name) as name
                FROM item_types
                WHERE published = 1 AND category_id IS NOT NULL
                GROUP BY category_id
                ORDER BY category_id ASC
            """

        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_groups_by_category(self, category_id: int) -> List[Dict]:
        """Grupos dentro de una categoría. Usa nombres reales si la tabla 'groups' existe."""
        conn = self._connect()

        if self._table_exists("groups"):
            query = """
                SELECT 
                    it.group_id,
                    COUNT(*) as item_count,
                    COALESCE(grp.name,
                        (SELECT name FROM item_types i2 
                         WHERE i2.group_id = it.group_id AND i2.published=1 
                         ORDER BY LENGTH(i2.name) ASC LIMIT 1)
                    ) as name
                FROM item_types it
                LEFT JOIN groups grp ON grp.id = it.group_id
                WHERE it.published = 1 AND it.category_id = ?
                GROUP BY it.group_id
                ORDER BY it.group_id ASC
            """
            params = (category_id,)
        else:
            query = """
                SELECT 
                    group_id,
                    COUNT(*) as item_count,
                    MIN(name) as name
                FROM item_types
                WHERE published = 1 AND category_id = ?
                GROUP BY group_id
                ORDER BY group_id ASC
            """
            params = (category_id,)

        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_types_in_group(self, group_id: int, limit: int = 40) -> List[Dict]:
        """Items de un grupo específico (útil para mostrar en UI y trackear)."""
        conn = self._connect()
        rows = conn.execute("""
            SELECT id, name, volume, base_price
            FROM item_types
            WHERE group_id = ? AND published = 1
            ORDER BY name
            LIMIT ?
        """, (group_id, limit)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_category_name(self, category_id: int) -> str:
        """Nombre representativo de categoría (usando un item como proxy)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT name FROM item_types WHERE category_id = ? AND published=1 LIMIT 1",
            (category_id,)
        ).fetchone()
        conn.close()
        return row["name"] if row else f"Category {category_id}"
