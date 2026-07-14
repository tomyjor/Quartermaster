"""
Test de integración del flujo de login completo (EVE SSO) a nivel
ApiServices -- URL de login, callback simulado (con un EveSSOClient
falso, sin red real), emisión de sesión, y verificación de que los
tokens quedan cifrados en reposo.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QUARTERMASTER_SESSION_SECRET", "test-secret-no-usar-en-produccion")
os.environ.setdefault("EVE_SSO_CLIENT_ID", "fake-client-id")
os.environ.setdefault("EVE_SSO_CLIENT_SECRET", "fake-client-secret")

from infrastructure.security.token_encryption import generate_key
os.environ.setdefault("QUARTERMASTER_ENCRYPTION_KEY", generate_key())

from presentation.api.services import ApiServices
from infrastructure.auth.eve_sso_client import TokenResponse, CharacterIdentity
from _winsafe import safe_unlink

REGION_ID = 10000002
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


class _FakeEveClient:
    def __init__(self, character_id: int, character_name: str):
        self.client_id = "fake-client-id"
        self._character_id = character_id
        self._character_name = character_name
        self.exchange_calls = []

    def exchange_code_for_token(self, code, code_verifier):
        self.exchange_calls.append((code, code_verifier))
        return TokenResponse(access_token="AT-fake", refresh_token="RT-fake", expires_in=1199)

    def decode_character_identity(self, access_token):
        return CharacterIdentity(character_id=self._character_id, character_name=self._character_name)


def _make_empty_multitenant_db() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute("INSERT OR IGNORE INTO regions (id, name) VALUES (?, 'The Forge')", (REGION_ID,))
    conn.commit()
    conn.close()
    return tmp_path


def test_full_login_flow_creates_user_and_issues_valid_session():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)

        url = svc.get_eve_login_url(redirect_uri="http://localhost:8000/api/auth/callback", frontend_redirect="http://localhost:8501/")
        assert "state=" in url
        state = url.split("state=")[1].split("&")[0]

        svc.eve_sso_client = _FakeEveClient(character_id=95465499, character_name="CCP Falcon")
        session_token, frontend_redirect = svc.handle_eve_callback(code="auth-code", state=state)
        assert frontend_redirect == "http://localhost:8501/"

        user = svc.get_user_from_session_token(session_token)
        assert user.eve_character_id == 95465499
        assert user.eve_character_name == "CCP Falcon"
    finally:
        safe_unlink(db_path)


def test_oauth_tokens_are_encrypted_at_rest_not_plaintext():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        url = svc.get_eve_login_url(redirect_uri="http://x/callback", frontend_redirect="http://frontend/")
        state = url.split("state=")[1].split("&")[0]
        svc.eve_sso_client = _FakeEveClient(character_id=1, character_name="X")

        svc.handle_eve_callback(code="c", state=state)

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT access_token_encrypted FROM oauth_tokens LIMIT 1").fetchone()
        conn.close()

        assert row is not None
        assert b"AT-fake" not in row[0]
    finally:
        safe_unlink(db_path)


def test_reusing_a_state_after_it_was_consumed_fails():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        url = svc.get_eve_login_url(redirect_uri="http://x/callback", frontend_redirect="http://frontend/")
        state = url.split("state=")[1].split("&")[0]
        svc.eve_sso_client = _FakeEveClient(character_id=1, character_name="X")

        svc.handle_eve_callback(code="c1", state=state)

        try:
            svc.handle_eve_callback(code="c2", state=state)
            assert False, "un state ya consumido no debería funcionar de nuevo"
        except ValueError:
            pass
    finally:
        safe_unlink(db_path)


def test_unknown_state_fails_clearly():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        svc.eve_sso_client = _FakeEveClient(character_id=1, character_name="X")

        try:
            svc.handle_eve_callback(code="c", state="state-que-nunca-existio")
            assert False, "un state desconocido no debería aceptarse"
        except ValueError:
            pass
    finally:
        safe_unlink(db_path)


def test_second_login_same_character_reuses_same_user_id():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        fake_client = _FakeEveClient(character_id=42, character_name="Repeat Pilot")

        url1 = svc.get_eve_login_url(redirect_uri="http://x/callback", frontend_redirect="http://f/")
        state1 = url1.split("state=")[1].split("&")[0]
        svc.eve_sso_client = fake_client
        token1, _ = svc.handle_eve_callback(code="c1", state=state1)
        user1 = svc.get_user_from_session_token(token1)

        url2 = svc.get_eve_login_url(redirect_uri="http://x/callback", frontend_redirect="http://f/")
        state2 = url2.split("state=")[1].split("&")[0]
        token2, _ = svc.handle_eve_callback(code="c2", state=state2)
        user2 = svc.get_user_from_session_token(token2)

        assert user1.id == user2.id
    finally:
        safe_unlink(db_path)


def test_login_without_eve_sso_configured_raises_clear_error():
    db_path = _make_empty_multitenant_db()
    try:
        svc = ApiServices(db_path=db_path, region_id=REGION_ID)
        svc.eve_sso_client = None  # simula que faltan las env vars

        try:
            svc.get_eve_login_url(redirect_uri="http://x/callback", frontend_redirect="http://f/")
            assert False, "debería exigir EVE SSO configurado"
        except ValueError as e:
            assert "EVE_SSO_CLIENT_ID" in str(e) or "EVE SSO" in str(e)
    finally:
        safe_unlink(db_path)
