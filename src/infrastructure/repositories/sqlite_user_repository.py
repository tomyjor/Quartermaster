"""
Infrastructure: SQLiteUserRepository
Implementación real del port UserRepository, contra database/trader.db
(tabla `users`, ver migración v4 -- multi-tenancy).
"""

import sqlite3
from shared.db import connect_db
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from domain.ports.user_repository import UserRepository
from domain.value_objects.user import User
from shared.paths import DEFAULT_DB_PATH


class SQLiteUserRepository(UserRepository):
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_by_id(self, user_id: int) -> Optional[User]:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, eve_character_id, eve_character_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        return User(**dict(row)) if row else None

    def get_by_eve_character_id(self, eve_character_id: int) -> Optional[User]:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, eve_character_id, eve_character_name FROM users WHERE eve_character_id = ?",
            (eve_character_id,),
        ).fetchone()
        conn.close()
        return User(**dict(row)) if row else None

    def create_or_update_login(self, eve_character_id: int, eve_character_name: str) -> User:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()

        existing = conn.execute(
            "SELECT id FROM users WHERE eve_character_id = ?", (eve_character_id,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE users SET eve_character_name = ?, last_login_at = ? WHERE id = ?",
                (eve_character_name, now, existing["id"]),
            )
            user_id = existing["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO users (eve_character_id, eve_character_name, created_at, last_login_at) "
                "VALUES (?, ?, ?, ?)",
                (eve_character_id, eve_character_name, now, now),
            )
            user_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return User(id=user_id, eve_character_id=eve_character_id, eve_character_name=eve_character_name)
