"""
Presentation: api_client

Cliente HTTP compartido hacia la API FastAPI -- lo usan tanto Streamlit
(`streamlit_app/`) como NiceGUI (`ui/`, Fase 2). Vive en `presentation/`
directo (no dentro de `streamlit_app/`) porque ninguna capa de UI debe
depender de los internals de la otra -- ambas son clientes intercambiables
del mismo backend. Ver docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §6.

Deliberadamente devuelve dicts (el JSON crudo parseado), no objetos de
dominio -- ninguna UI debería importar nada de `domain.*` ni
`infrastructure.*` después de la migración a API.

Cada función maneja errores de conexión de forma explícita (¿está
corriendo `uvicorn`?) en vez de dejar que la UI muestre un traceback
crudo de `requests` -- ver `ApiConnectionError`.
"""

import requests
from typing import List, Optional, Dict, Any
from urllib.parse import quote

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30


class ApiConnectionError(Exception):
    """Se levanta cuando la API no responde -- típicamente porque uvicorn no está corriendo."""
    pass


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        #: Token de sesión (JWT propio, emitido por /api/auth/callback
        #: tras un login exitoso) -- None si nadie inició sesión
        #: todavía. Ver `set_session_token`/`clear_session_token`.
        self.session_token: Optional[str] = None

    def set_session_token(self, token: str) -> None:
        """La UI llama esto después de recibir `session_token` en la URL de retorno del login."""
        self.session_token = token

    def clear_session_token(self) -> None:
        """Logout -- del lado del cliente solamente (no hay invalidación server-side de sesiones todavía)."""
        self.session_token = None

    @property
    def is_authenticated(self) -> bool:
        return self.session_token is not None

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, headers=headers, **kwargs)
        except requests.exceptions.ConnectionError as e:
            raise ApiConnectionError(
                f"No se pudo conectar a la API en {self.base_url}. "
                "¿Está corriendo `python -m uvicorn presentation.api.main:app --app-dir src`? "
                f"(detalle técnico: {e})"
            )
        except requests.exceptions.Timeout as e:
            raise ApiConnectionError(
                f"La API en {self.base_url} no respondió en {self.timeout}s. "
                f"(detalle técnico: {e})"
            )
        response.raise_for_status()
        return response

    def health_check(self) -> bool:
        try:
            self._request("GET", "/api/health")
            return True
        except (ApiConnectionError, requests.exceptions.HTTPError):
            return False

    # ------------------------------------------------------------------
    # Autenticación (EVE SSO)
    # ------------------------------------------------------------------

    def get_login_url(self, frontend_redirect: str) -> str:
        """
        URL a la que la UI debe mandar al browser (no un fetch -- una
        redirección real, `<a href=...>` o `st.link_button`/`ui.link`)
        para iniciar el login. `frontend_redirect` es la URL de esta
        misma UI, a la que EVE SSO va a devolver al browser (con
        `?session_token=...` agregado) una vez que el login termine.
        """
        return f"{self.base_url}/api/auth/login?frontend_redirect={quote(frontend_redirect, safe='')}"

    def get_me(self) -> Optional[Dict[str, Any]]:
        """
        Info del usuario autenticado, o None si no hay sesión válida
        (sin token, token expirado, o token inválido) -- nunca levanta
        una excepción por esto, es un chequeo normal, no un error.
        """
        if not self.session_token:
            return None
        try:
            response = self._request("GET", "/api/auth/me")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                return None
            raise
        return response.json()

    # ------------------------------------------------------------------
    # Oportunidades
    # ------------------------------------------------------------------

    def get_opportunities(
        self,
        scope: str = "discovery",
        min_score: float = 0.0,
        max_results: int = 50,
        sort_by: str = "score",
        sort_desc: bool = True,
        discovery_limit: int = 30000,
        exclude_caution: bool = False,
    ) -> Dict[str, Any]:
        """Devuelve el dict crudo de OpportunitiesPageSchema: {opportunities, total_evaluated, total_with_data, scope}."""
        response = self._request("GET", "/api/opportunities", params={
            "scope": scope, "min_score": min_score, "max_results": max_results,
            "sort_by": sort_by, "sort_desc": sort_desc,
            "discovery_limit": discovery_limit, "exclude_caution": exclude_caution,
        })
        return response.json()

    def get_opportunity(self, type_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = self._request("GET", f"/api/opportunities/{type_id}")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        return response.json()

    # ------------------------------------------------------------------
    # Tracked items
    # ------------------------------------------------------------------

    def list_tracked(self) -> List[Dict[str, Any]]:
        """Devuelve [{"type_id": int, "name": str}, ...] -- con nombres resueltos."""
        response = self._request("GET", "/api/tracked-items")
        return response.json()

    def track_item(self, type_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        """202: el tracking se confirma inmediato, el import corre en background del lado del server."""
        response = self._request("POST", f"/api/tracked-items/{type_id}", json={"reason": reason})
        return response.json()

    def untrack_item(self, type_id: int) -> None:
        self._request("DELETE", f"/api/tracked-items/{type_id}")

    def untrack_many(self, type_ids: List[int]) -> int:
        response = self._request("POST", "/api/tracked-items/batch/untrack", json={"type_ids": type_ids})
        return response.json()["deleted"]

    def untrack_all(self) -> int:
        response = self._request("DELETE", "/api/tracked-items")
        return response.json()["deleted"]

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------

    def search_items(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        response = self._request("GET", "/api/items/search", params={"q": query, "limit": limit})
        return response.json()

    def list_categories(self) -> List[Dict[str, Any]]:
        response = self._request("GET", "/api/catalog/categories")
        return response.json()

    def list_groups(self, category_id: int) -> List[Dict[str, Any]]:
        response = self._request("GET", f"/api/catalog/categories/{category_id}/groups")
        return response.json()

    def list_types_in_group(self, group_id: int, limit: int = 40) -> List[Dict[str, Any]]:
        response = self._request("GET", f"/api/catalog/groups/{group_id}/types", params={"limit": limit})
        return response.json()

    # ------------------------------------------------------------------
    # Sync / Smart Auto-Seed
    # ------------------------------------------------------------------

    def get_sync_status(self) -> Optional[Dict[str, Any]]:
        try:
            response = self._request("GET", "/api/sync/status")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        return response.json()

    def trigger_seed(self) -> Dict[str, Any]:
        response = self._request("POST", "/api/sync/seed")
        return response.json()
