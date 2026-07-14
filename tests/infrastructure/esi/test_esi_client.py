"""
Tests para ESIClient: reintentos ante errores transitorios y el
callback de progreso por página (`on_page`).

Usa una sesión HTTP falsa (sin red real) -- mismo patrón que el resto
del proyecto para testear I/O externo sin depender de conectividad.
"""

import requests

from infrastructure.esi.esi_client import ESIClient


class _FakeResponse:
    def __init__(self, status_code, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else []
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def mount(self, *a, **k):
        pass

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def close(self):
        pass


def _client_with_fast_retries():
    client = ESIClient()
    client.RETRY_BACKOFF_SECONDS = 0.01  # no esperar de verdad en tests
    return client


def test_retries_on_transient_5xx_then_succeeds():
    client = _client_with_fast_retries()
    client.session = _FakeSession([
        _FakeResponse(502),
        _FakeResponse(200, json_data=[{"a": 1}], headers={"X-Pages": "1"}),
    ])
    data = client.get("/markets/10000002/orders/", {"type_id": 34})
    assert data == [{"a": 1}]
    assert client.session.calls == 2


def test_fails_after_exhausting_retries_on_persistent_error():
    client = _client_with_fast_retries()
    client.session = _FakeSession([_FakeResponse(502)] * client.MAX_RETRIES)
    try:
        client.get("/markets/10000002/orders/", {"type_id": 34})
        assert False, "debería haber lanzado HTTPError"
    except requests.exceptions.HTTPError:
        pass
    assert client.session.calls == client.MAX_RETRIES


def test_does_not_retry_non_transient_4xx():
    client = _client_with_fast_retries()
    client.session = _FakeSession([_FakeResponse(404)])
    try:
        client.get("/markets/10000002/orders/", {"type_id": 999999999})
        assert False, "debería haber lanzado HTTPError"
    except requests.exceptions.HTTPError:
        pass
    assert client.session.calls == 1, "un 404 no es transitorio, no debería reintentar"


def test_on_page_callback_fires_once_per_page_with_real_progress():
    """
    Regresión del bug de "status congelado": una petición sin `type_id`
    (fetch de región completa) puede ser cientos de páginas -- sin este
    callback, el caller no tiene forma de reportar progreso hasta que
    TODO el fetch termine. Confirma que se llama una vez por página,
    con el conteo acumulado de items correcto en cada llamada.
    """
    client = _client_with_fast_retries()
    client.session = _FakeSession([
        _FakeResponse(200, json_data=[{"order_id": i} for i in range(1, 6)], headers={"X-Pages": "3"}),
        _FakeResponse(200, json_data=[{"order_id": i} for i in range(6, 11)], headers={"X-Pages": "3"}),
        _FakeResponse(200, json_data=[{"order_id": i} for i in range(11, 13)], headers={"X-Pages": "3"}),
    ])

    progress = []
    result = client.get("/markets/10000002/orders/", on_page=lambda page, total, count: progress.append((page, total, count)))

    assert len(result) == 12
    assert progress == [(1, 3, 5), (2, 3, 10), (3, 3, 12)]


def test_on_page_is_optional_and_does_not_break_normal_calls():
    """Los callers que no pasan on_page (la mayoría del código existente)
    no deben verse afectados por el parámetro nuevo."""
    client = _client_with_fast_retries()
    client.session = _FakeSession([
        _FakeResponse(200, json_data=[{"order_id": 1}], headers={"X-Pages": "1"}),
    ])
    result = client.get("/markets/10000002/orders/", {"type_id": 34})
    assert result == [{"order_id": 1}]
