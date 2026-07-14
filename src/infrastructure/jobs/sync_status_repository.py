"""
Infrastructure: SyncStatusRepository

Persiste el progreso de los jobs de sync (`sync_status`) y estado global
del sistema (`system_state`, key-value genérico -- hoy solo
`last_full_seed_at`). Es lo que le permite a la API reportar progreso
sin bloquear: el job en background escribe acá, un endpoint de solo
lectura (`GET /api/sync/status`) lo lee y lo devuelve.

Deliberadamente puro sqlite3 -- sin dependencias del stack nuevo
(FastAPI/APScheduler), así se puede testear sin tenerlas instaladas.
"""

import sqlite3
from shared.db import connect_db
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from shared.paths import DEFAULT_DB_PATH


class SyncStatusRepository:

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # sync_status: progreso del job en curso, por región
    # ------------------------------------------------------------------

    def set_status(
        self,
        region_id: int,
        phase: str,
        detail: Optional[str] = None,
        total: Optional[int] = None,
        done: Optional[int] = None,
        error: Optional[str] = None,
        reset_started_at: bool = False,
    ) -> None:
        """
        Actualiza (o crea) el estado de sync de una región. `phase` es
        uno de: 'idle' | 'orders' | 'history' | 'completed' | 'error'.

        `reset_started_at=True` marca el arranque de un job nuevo (se
        usa al iniciar una corrida, no en cada actualización de
        progreso intermedia).
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()

        existing = conn.execute(
            "SELECT started_at FROM sync_status WHERE region_id = ?", (region_id,)
        ).fetchone()

        started_at = now if (reset_started_at or existing is None) else existing["started_at"]

        conn.execute(
            """
            INSERT INTO sync_status
                (region_id, phase, detail, total, done, started_at, updated_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(region_id) DO UPDATE SET
                phase = excluded.phase,
                detail = excluded.detail,
                total = excluded.total,
                done = excluded.done,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                error = excluded.error
            """,
            (region_id, phase, detail, total, done, started_at, now, error),
        )
        conn.commit()
        conn.close()

    def get_status(self, region_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM sync_status WHERE region_id = ?", (region_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def mark_error(self, region_id: int, error: str) -> None:
        self.set_status(region_id, phase="error", detail=None, error=error)

    def mark_completed(self, region_id: int, detail: Optional[str] = None) -> None:
        self.set_status(region_id, phase="completed", detail=detail, error=None)

    # ------------------------------------------------------------------
    # system_state: key-value genérico
    # ------------------------------------------------------------------

    def get_state(self, key: str) -> Optional[str]:
        conn = self._connect()
        row = conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO system_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_last_full_seed_at(self) -> Optional[str]:
        return self.get_state("last_full_seed_at")

    def set_last_full_seed_at(self, when: Optional[datetime] = None) -> None:
        when = when or datetime.now(timezone.utc)
        self.set_state("last_full_seed_at", when.isoformat())

    def needs_initial_seed(self) -> bool:
        """
        True si nunca se corrió un Smart Auto-Seed completo -- señal para
        que el arranque de la API lo dispare automáticamente.
        """
        return self.get_last_full_seed_at() is None
