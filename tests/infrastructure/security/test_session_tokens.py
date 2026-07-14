"""Tests para session_tokens -- JWTs de sesión propios de Quartermaster."""

import os
import importlib

os.environ["QUARTERMASTER_SESSION_SECRET"] = "clave-de-test-no-usar-en-produccion"
import infrastructure.security.session_tokens as st
importlib.reload(st)


def test_issue_and_verify_roundtrip():
    token = st.issue_session_token(user_id=42, eve_character_name="Test Pilot")
    payload = st.verify_session_token(token)

    assert payload["user_id"] == 42
    assert payload["character_name"] == "Test Pilot"


def test_tampered_token_is_rejected():
    token = st.issue_session_token(user_id=1, eve_character_name="X")
    tampered = token[:-5] + "XXXXX"

    try:
        st.verify_session_token(tampered)
        assert False, "debería rechazar un token manipulado"
    except st.SessionTokenError:
        pass


def test_expired_token_is_rejected():
    original_ttl = st.SESSION_TTL_HOURS
    st.SESSION_TTL_HOURS = -1
    try:
        expired = st.issue_session_token(user_id=1, eve_character_name="X")
        try:
            st.verify_session_token(expired)
            assert False, "debería rechazar un token expirado"
        except st.SessionTokenError as e:
            assert "expiró" in str(e)
    finally:
        st.SESSION_TTL_HOURS = original_ttl


def test_missing_secret_raises_clear_error():
    del os.environ["QUARTERMASTER_SESSION_SECRET"]
    try:
        try:
            st.issue_session_token(user_id=1, eve_character_name="X")
            assert False, "debería exigir la clave"
        except st.SessionTokenError as e:
            assert "QUARTERMASTER_SESSION_SECRET" in str(e)
    finally:
        os.environ["QUARTERMASTER_SESSION_SECRET"] = "clave-de-test-no-usar-en-produccion"


def test_different_users_get_different_payloads():
    t1 = st.issue_session_token(user_id=1, eve_character_name="Pilot A")
    t2 = st.issue_session_token(user_id=2, eve_character_name="Pilot B")

    assert st.verify_session_token(t1)["user_id"] == 1
    assert st.verify_session_token(t2)["user_id"] == 2
