"""
Tests para ApiClient (cliente HTTP de Streamlit hacia la API FastAPI).

Usa una sesión HTTP falsa (sin red real) -- mismo patrón que
`tests/infrastructure/esi/test_esi_client.py`. No requiere que la API
esté corriendo.
"""

import requests

from presentation.api_client import ApiClient, ApiConnectionError


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


class _FakeSession:
    def __init__(self, response_or_exc):
        self.response_or_exc = response_or_exc
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        if isinstance(self.response_or_exc, Exception):
            raise self.response_or_exc
        return self.response_or_exc


def test_get_opportunities_parses_response_and_sends_correct_params():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {
        "opportunities": [{"type_id": 1}], "total_evaluated": 1,
        "total_with_data": 1, "scope": "discovery",
    }))

    data = client.get_opportunities(scope="discovery", exclude_caution=True, sort_by="roi")

    assert data["opportunities"][0]["type_id"] == 1
    method, url, kwargs = client.session.calls[0]
    assert method == "GET"
    assert url.endswith("/api/opportunities")
    assert kwargs["params"]["exclude_caution"] is True
    assert kwargs["params"]["sort_by"] == "roi"


def test_connection_error_raises_clear_actionable_message_not_raw_traceback():
    """
    Regresión de la experiencia real del usuario: sin esto, un
    ConnectionError de `requests` se ve en Streamlit como un traceback
    crudo. El mensaje debe decir explícitamente qué hacer (correr
    uvicorn), no solo "connection refused".
    """
    client = ApiClient()
    client.session = _FakeSession(requests.exceptions.ConnectionError("refused"))

    try:
        client.get_opportunities()
        assert False, "debería haber lanzado ApiConnectionError"
    except ApiConnectionError as e:
        assert "uvicorn" in str(e)
        assert "127.0.0.1:8000" in str(e)


def test_get_opportunity_404_returns_none_not_exception():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(404, {"detail": "no encontrado"}))

    result = client.get_opportunity(999999)

    assert result is None


def test_get_sync_status_404_returns_none_not_exception():
    """404 en /api/sync/status significa 'nunca corrió un seed' -- no es un error."""
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(404, {"detail": "sin sync todavía"}))

    result = client.get_sync_status()

    assert result is None


def test_track_item_sends_reason_in_json_body():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(202, {"status": "tracking", "type_id": 34}))

    resp = client.track_item(34, reason="búsqueda manual")

    assert resp["status"] == "tracking"
    _, _, kwargs = client.session.calls[0]
    assert kwargs["json"] == {"reason": "búsqueda manual"}


def test_untrack_all_returns_deleted_count():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"deleted": 40}))

    deleted = client.untrack_all()

    assert deleted == 40
    method, url, _ = client.session.calls[0]
    assert method == "DELETE"
    assert url.endswith("/api/tracked-items")


def test_health_check_returns_false_on_connection_error_instead_of_raising():
    client = ApiClient()
    client.session = _FakeSession(requests.exceptions.ConnectionError("refused"))

    assert client.health_check() is False


def test_health_check_returns_true_on_200():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"status": "ok"}))

    assert client.health_check() is True


def test_no_authorization_header_sent_before_login():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"opportunities": []}))

    client.get_opportunities(scope="discovery")

    _, _, kwargs = client.session.calls[0]
    assert "Authorization" not in kwargs["headers"]


def test_authorization_header_sent_after_login():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"opportunities": []}))

    client.set_session_token("fake-jwt")
    assert client.is_authenticated
    client.get_opportunities(scope="tracked")

    _, _, kwargs = client.session.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer fake-jwt"


def test_logout_clears_token_and_stops_sending_header():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"opportunities": []}))
    client.set_session_token("fake-jwt")

    client.clear_session_token()

    assert not client.is_authenticated
    client.get_opportunities(scope="discovery")
    _, _, kwargs = client.session.calls[0]
    assert "Authorization" not in kwargs["headers"]


def test_get_login_url_includes_frontend_redirect():
    client = ApiClient()

    url = client.get_login_url(frontend_redirect="http://localhost:8501/")

    assert url.startswith("http://127.0.0.1:8000/api/auth/login?")
    assert "frontend_redirect=" in url


def test_get_me_returns_none_without_token_no_request_made():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {"should": "not be called"}))

    result = client.get_me()

    assert result is None
    assert client.session.calls == [], "no debería hacer ningún request sin token"


def test_get_me_returns_none_on_401_instead_of_raising():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(401, {"detail": "expired"}))
    client.set_session_token("expired-token")

    assert client.get_me() is None


def test_get_me_returns_user_info_with_valid_session():
    client = ApiClient()
    client.session = _FakeSession(_FakeResponse(200, {
        "user_id": 1, "eve_character_id": 123, "eve_character_name": "Test Pilot",
    }))
    client.set_session_token("valid-token")

    me = client.get_me()

    assert me["eve_character_name"] == "Test Pilot"
