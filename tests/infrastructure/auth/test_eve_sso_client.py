"""
Tests para EveSSOClient -- cubre todo lo que se puede probar sin red
real (PKCE, construcción de URL, formato de requests, decodificación
de JWT). El intercambio real contra login.eveonline.com NO está
probado acá -- ver docstring de infrastructure/auth/eve_sso_client.py.
"""

import hashlib
import base64
import jwt as pyjwt

from infrastructure.auth.eve_sso_client import (
    EveSSOClient, EveSSOError, generate_pkce_pair, build_authorize_url
)


def _make_rs256_token(iss: str, client_id: str = "abc123"):
    """
    Genera un JWT RS256 real (clave RSA generada en el momento) --
    usado para probar la validación completa de `decode_character_identity`
    con `verify_signature=True`, sin depender de red real.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = {
        "iss": iss, "aud": [client_id, "EVE Online"],
        "sub": "CHARACTER:EVE:95465499", "name": "CCP Falcon",
    }
    token = pyjwt.encode(payload, private_key, algorithm="RS256")
    return token, private_key.public_key()


def _decode_with_mocked_jwks(client, token, public_key):
    import infrastructure.auth.eve_sso_client as eve_sso_module

    class _FakeSigningKey:
        def __init__(self, key):
            self.key = key

    class _FakePyJWKClient:
        def __init__(self, uri, **kwargs):
            pass

        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey(public_key)

    original = eve_sso_module.jwt.PyJWKClient
    eve_sso_module.jwt.PyJWKClient = _FakePyJWKClient
    try:
        return client.decode_character_identity(token, verify_signature=True)
    finally:
        eve_sso_module.jwt.PyJWKClient = original


def test_decode_accepts_issuer_without_url_scheme():
    """Forma vieja del 'iss' (antes de nov. 2023) -- debe seguir aceptándose."""
    client = EveSSOClient(client_id="abc123", client_secret="s")
    token, public_key = _make_rs256_token(iss="login.eveonline.com")

    identity = _decode_with_mocked_jwks(client, token, public_key)

    assert identity.character_id == 95465499
    assert identity.character_name == "CCP Falcon"


def test_decode_accepts_issuer_with_url_scheme():
    """
    Regresión del bug real encontrado en el primer login real: el 'iss'
    real de EVE (desde nov. 2023) es "https://login.eveonline.com", con
    esquema -- el código antes solo aceptaba la forma sin esquema y
    rechazaba el token real con InvalidIssuerError.
    """
    client = EveSSOClient(client_id="abc123", client_secret="s")
    token, public_key = _make_rs256_token(iss="https://login.eveonline.com")

    identity = _decode_with_mocked_jwks(client, token, public_key)

    assert identity.character_id == 95465499
    assert identity.character_name == "CCP Falcon"


def test_decode_rejects_unrelated_issuer():
    """Un 'iss' que no es ninguna de las dos formas válidas de EVE debe rechazarse -- la validación manual no debe volverse permisiva de más."""
    client = EveSSOClient(client_id="abc123", client_secret="s")
    token, public_key = _make_rs256_token(iss="https://not-eve-online.example.com")

    try:
        _decode_with_mocked_jwks(client, token, public_key)
        assert False, "debería rechazar un issuer que no es de EVE"
    except EveSSOError as e:
        assert "Issuer inesperado" in str(e)


def test_get_signing_key_constructs_pyjwkclient_with_only_valid_kwargs():
    """
    Regresión de un bug real (primer login real del usuario contra EVE):
    `PyJWKClient(JWKS_URL, session=self.session)` -- `session` NUNCA fue
    un kwarg válido de `PyJWKClient.__init__` en ninguna versión de
    PyJWT (confusión con el patrón de otras librerías que sí aceptan
    inyectar una `requests.Session`). Los tests de arriba usan
    `verify_signature=False`, así que nunca ejercitaban este método --
    por eso el bug llegó hasta un login real sin que ningún test lo
    cazara. Este test llama `_get_signing_key` directo, con
    `jwt.PyJWKClient` mockeado (no hay red real acá), y verifica
    específicamente que la construcción no reciba un kwarg `session`.
    """
    import infrastructure.auth.eve_sso_client as eve_sso_module

    captured_kwargs = {}

    class _FakeSigningKey:
        key = "fake-key-bytes"

    class _FakePyJWKClient:
        def __init__(self, uri, **kwargs):
            captured_kwargs.update(kwargs)
            self.uri = uri

        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey()

    original_pyjwkclient = eve_sso_module.jwt.PyJWKClient
    eve_sso_module.jwt.PyJWKClient = _FakePyJWKClient
    try:
        client = EveSSOClient(client_id="x", client_secret="y")
        key = client._get_signing_key("fake.jwt.token")
        assert key == "fake-key-bytes"
        assert "session" not in captured_kwargs, (
            "PyJWKClient nunca aceptó 'session' -- pasarlo rompe la construcción "
            "en cualquier versión real de PyJWT, incluso si acá el mock no lo rechaza."
        )
    finally:
        eve_sso_module.jwt.PyJWKClient = original_pyjwkclient


class _FakeResponse:
    def __init__(self, status_code, json_data, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or str(json_data)

    def json(self):
        return self._json


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, data=None, auth=None, headers=None, timeout=None):
        self.calls.append((url, data, auth))
        return self.response


def test_pkce_challenge_matches_sha256_of_verifier():
    pair = generate_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(pair.code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    assert pair.code_challenge == expected


def test_pkce_pairs_are_random_each_time():
    pair1 = generate_pkce_pair()
    pair2 = generate_pkce_pair()

    assert pair1.code_verifier != pair2.code_verifier
    assert pair1.code_challenge != pair2.code_challenge


def test_authorize_url_contains_required_oauth_params():
    url = build_authorize_url(
        client_id="abc123", redirect_uri="http://localhost:8000/api/auth/callback",
        state="random-state", code_challenge="some-challenge",
    )

    assert "response_type=code" in url
    assert "client_id=abc123" in url
    assert "code_challenge=some-challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=random-state" in url


def test_exchange_code_for_token_sends_correct_request():
    client = EveSSOClient(client_id="abc", client_secret="secret", session=_FakeSession(
        _FakeResponse(200, {"access_token": "AT123", "refresh_token": "RT456", "expires_in": 1199})
    ))

    result = client.exchange_code_for_token(code="auth-code", code_verifier="verifier")

    assert result.access_token == "AT123"
    assert result.refresh_token == "RT456"
    _, data, auth = client.session.calls[0]
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "auth-code"
    assert data["code_verifier"] == "verifier"
    assert auth == ("abc", "secret")


def test_eve_sso_error_response_raises_clear_exception():
    client = EveSSOClient(client_id="abc", client_secret="secret", session=_FakeSession(
        _FakeResponse(400, {"error": "invalid_grant"}, text="invalid_grant")
    ))

    try:
        client.exchange_code_for_token(code="bad", code_verifier="x")
        assert False, "debería levantar EveSSOError"
    except EveSSOError as e:
        assert "400" in str(e)


def test_refresh_token_sends_correct_request():
    client = EveSSOClient(client_id="abc", client_secret="secret", session=_FakeSession(
        _FakeResponse(200, {"access_token": "AT-NEW", "refresh_token": "RT-NEW", "expires_in": 1199})
    ))

    result = client.refresh_access_token(refresh_token="RT-OLD")

    assert result.access_token == "AT-NEW"
    data = client.session.calls[0][1]
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "RT-OLD"


def test_decode_character_identity_extracts_id_and_name():
    client = EveSSOClient(client_id="abc", client_secret="secret")
    fake_token = pyjwt.encode(
        {"sub": "CHARACTER:EVE:95465499", "name": "CCP Falcon"},
        "any-secret", algorithm="HS256",
    )

    identity = client.decode_character_identity(fake_token, verify_signature=False)

    assert identity.character_id == 95465499
    assert identity.character_name == "CCP Falcon"


def test_decode_character_identity_rejects_unexpected_sub_format():
    client = EveSSOClient(client_id="abc", client_secret="secret")
    fake_token = pyjwt.encode({"sub": "not-a-character-sub", "name": "X"}, "s", algorithm="HS256")

    try:
        client.decode_character_identity(fake_token, verify_signature=False)
        assert False, "debería rechazar un 'sub' con formato inesperado"
    except EveSSOError:
        pass


def test_decode_character_identity_requires_name_claim():
    client = EveSSOClient(client_id="abc", client_secret="secret")
    fake_token = pyjwt.encode({"sub": "CHARACTER:EVE:123"}, "s", algorithm="HS256")

    try:
        client.decode_character_identity(fake_token, verify_signature=False)
        assert False, "debería exigir el claim 'name'"
    except EveSSOError:
        pass
