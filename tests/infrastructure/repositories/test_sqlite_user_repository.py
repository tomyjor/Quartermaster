"""Tests para SQLiteUserRepository -- login/re-login vía EVE SSO."""

import sqlite3
import tempfile
from pathlib import Path

from infrastructure.repositories.sqlite_user_repository import SQLiteUserRepository
from _winsafe import safe_unlink

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eve_character_id INTEGER NOT NULL UNIQUE,
    eve_character_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL
);
"""


def _make_db() -> Path:
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fd.close()
    db_path = Path(fd.name)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    return db_path


def test_first_login_creates_user():
    db_path = _make_db()
    try:
        repo = SQLiteUserRepository(db_path=db_path)
        user = repo.create_or_update_login(eve_character_id=123, eve_character_name="Test Pilot")

        assert user.eve_character_id == 123
        assert user.eve_character_name == "Test Pilot"
        assert user.id is not None
    finally:
        safe_unlink(db_path)


def test_second_login_same_character_does_not_duplicate():
    db_path = _make_db()
    try:
        repo = SQLiteUserRepository(db_path=db_path)
        u1 = repo.create_or_update_login(eve_character_id=123, eve_character_name="Test Pilot")
        u2 = repo.create_or_update_login(eve_character_id=123, eve_character_name="Test Pilot")

        assert u1.id == u2.id
    finally:
        safe_unlink(db_path)


def test_character_rename_is_reflected():
    db_path = _make_db()
    try:
        repo = SQLiteUserRepository(db_path=db_path)
        u1 = repo.create_or_update_login(eve_character_id=123, eve_character_name="Old Name")
        u2 = repo.create_or_update_login(eve_character_id=123, eve_character_name="New Name")

        assert u1.id == u2.id
        assert repo.get_by_id(u1.id).eve_character_name == "New Name"
    finally:
        safe_unlink(db_path)


def test_different_characters_get_different_users():
    db_path = _make_db()
    try:
        repo = SQLiteUserRepository(db_path=db_path)
        u1 = repo.create_or_update_login(eve_character_id=123, eve_character_name="Pilot A")
        u2 = repo.create_or_update_login(eve_character_id=456, eve_character_name="Pilot B")

        assert u1.id != u2.id
    finally:
        safe_unlink(db_path)


def test_get_by_id_and_get_by_eve_character_id_return_none_when_missing():
    db_path = _make_db()
    try:
        repo = SQLiteUserRepository(db_path=db_path)
        assert repo.get_by_id(9999) is None
        assert repo.get_by_eve_character_id(9999) is None
    finally:
        safe_unlink(db_path)
