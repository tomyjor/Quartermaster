"""
Infrastructure/Auth: eve_sso_client

Cliente OAuth2 para EVE SSO (login.eveonline.com) -- Authorization Code
flow con PKCE, según la especificación oficial de CCP.

⚠️ IMPORTANTE sobre qué está verificado y qué no: `build_authorize_url`,
`generate_pkce_pair`, y el parseo del JWT están probados de verdad
(son criptografía/parsing puro, sin red). El intercambio real de
código por tokens (`exchange_code_for_token`, `refresh_access_token`)
y la verificación de firma contra el JWKS de EVE SOLO están probados
con una sesión HTTP falsa (mismo patrón que `ESIClient`) -- la
primera vez que hablan con el servidor real de CCP es cuando el
usuario lo pruebe con credenciales reales, no acá.

Para usar esto hace falta registrar una aplicación en
https://developers.eveonline.com -- ahí se obtiene `client_id` y
`client_secret`, y se define la URL de callback (debe coincidir
exacto con la configurada acá, CCP la valida estricto).

Scopes: para el caso de uso actual (identificar quién sos, nada de
leer tu wallet/órdenes personales todavía) alcanza con NO pedir ningún
scope de ESI -- el login solo ya te da `sub`/`name` en el JWT. Si en el
futuro hace falta leer datos del personaje (órdenes, wallet, etc.), ahí
sí se agregan scopes específicos de ESI a `AUTHORIZE_SCOPES`.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional, List

import requests
import jwt

AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
JWKS_URL = "https://login.eveonline.com/oauth/jwks"

#: Vacío a propósito -- ver docstring del módulo. Login-only, sin
#: acceso a datos personales del personaje todavía.
DEFAULT_SCOPES: List[str] = []


class EveSSOError(Exception):
    """Error de configuración, de red, o de respuesta inesperada de EVE SSO."""
    pass


@dataclass(frozen=True)
class PKCEPair:
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int  # segundos


@dataclass(frozen=True)
class CharacterIdentity:
    character_id: int
    character_name: str


def generate_pkce_pair() -> PKCEPair:
    """
    PKCE (RFC 7636): un secreto (`code_verifier`) que solo nosotros
    conocemos, y su hash (`code_challenge`) que sí viaja en la URL de
    autorización. EVE valida en el intercambio de token que quien pide
    el token conoce el secreto original -- protege contra que alguien
    intercepte el `code` de la URL de callback y lo cambie por un token
    él mismo.
    """
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEPair(code_verifier=verifier, code_challenge=challenge)


def build_authorize_url(
    client_id: str, redirect_uri: str, state: str, code_challenge: str,
    scopes: Optional[List[str]] = None,
) -> str:
    """
    URL a la que redirigir al usuario para que inicie sesión en EVE y
    autorice la aplicación. `state` debe ser un valor random generado
    por nosotros y verificado al volver (protege contra CSRF) -- NO
    reusar el mismo `state` entre logins distintos.
    """
    scopes = scopes if scopes is not None else DEFAULT_SCOPES
    params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


class EveSSOClient:
    def __init__(self, client_id: str, client_secret: str, session: Optional[requests.Session] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()

    def exchange_code_for_token(self, code: str, code_verifier: str) -> TokenResponse:
        """
        Intercambia el `code` recibido en el callback por tokens de
        acceso/refresh. ⚠️ NO PROBADO contra el servidor real de EVE en
        este entorno (sin red) -- ver docstring del módulo.
        """
        response = self._post_token(
            {"grant_type": "authorization_code", "code": code, "code_verifier": code_verifier}
        )
        return TokenResponse(
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
            expires_in=response["expires_in"],
        )

    def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Renueva el access_token usando el refresh_token guardado. ⚠️ NO PROBADO contra el servidor real."""
        response = self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        return TokenResponse(
            access_token=response["access_token"],
            refresh_token=response.get("refresh_token", refresh_token),
            expires_in=response["expires_in"],
        )

    def _post_token(self, data: dict) -> dict:
        auth = (self.client_id, self.client_secret)
        try:
            response = self.session.post(
                TOKEN_URL, data=data, auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            raise EveSSOError(f"No se pudo contactar a EVE SSO: {e}")

        if response.status_code != 200:
            raise EveSSOError(f"EVE SSO devolvió {response.status_code}: {response.text[:200]}")
        return response.json()

    #: EVE acepta el 'iss' del JWT en dos formas -- ver
    #: docs.esi.evetech.net/docs/sso/validating_eve_jwt.html: "Your
    #: application should handle looking for both the host name and
    #: the URI". Desde nov. 2023 EVE emite el segundo (con esquema);
    #: antes emitía el primero -- hay que aceptar los dos.
    ACCEPTED_ISSUERS = ("login.eveonline.com", "https://login.eveonline.com")

    def decode_character_identity(self, access_token: str, verify_signature: bool = True) -> CharacterIdentity:
        """
        Decodifica el JWT de acceso para extraer quién es el personaje
        -- `sub` viene con forma "CHARACTER:EVE:<id>", `name` es el
        nombre del personaje. Con `verify_signature=True` (default),
        valida la firma contra el JWKS público de EVE antes de confiar
        en el contenido -- necesario en producción, requiere red para
        traer el JWKS. `verify_signature=False` es solo para tests con
        tokens fabricados a mano.

        Bug real encontrado en el primer login real con credenciales
        de EVE: `jwt.decode(..., issuer="login.eveonline.com")`
        rechazaba el token con `InvalidIssuerError`. El 'iss' real del
        token es `"https://login.eveonline.com"` (con esquema, desde
        el cambio de EVE de nov. 2023) -- el string hardcodeado acá
        estaba desactualizado. `issuer=` de PyJWT solo acepta UN string
        (no una lista), así que la validación de 'iss' se hace acá a
        mano, contra `ACCEPTED_ISSUERS`, en vez de delegarla a PyJWT.
        """
        if verify_signature:
            signing_key = self._get_signing_key(access_token)
            payload = jwt.decode(
                access_token, signing_key, algorithms=["RS256"], audience="EVE Online",
            )
            if payload.get("iss") not in self.ACCEPTED_ISSUERS:
                raise EveSSOError(
                    f"Issuer inesperado en el JWT de EVE: {payload.get('iss')!r} "
                    f"(esperaba uno de {self.ACCEPTED_ISSUERS!r})"
                )
        else:
            payload = jwt.decode(access_token, options={"verify_signature": False})

        sub = payload.get("sub", "")
        if not sub.startswith("CHARACTER:EVE:"):
            raise EveSSOError(f"Formato de 'sub' inesperado en el JWT de EVE: {sub!r}")
        character_id = int(sub.split(":")[-1])
        character_name = payload.get("name", "")
        if not character_name:
            raise EveSSOError("El JWT de EVE no incluye el nombre del personaje ('name').")

        return CharacterIdentity(character_id=character_id, character_name=character_name)

    def _get_signing_key(self, token: str):
        """
        Bug real encontrado en producción (primer login real con
        credenciales de EVE): `PyJWKClient` NUNCA aceptó un kwarg
        `session` -- ni en la versión mínima pinneada (2.7) ni en
        versiones más nuevas. Es una confusión mía con el patrón de
        otras librerías que sí aceptan inyectar una `requests.Session`
        propia; `PyJWKClient` maneja su propio fetching HTTP
        internamente (solo toma `uri`, `headers`, `timeout`, etc., ver
        su firma real). Sacado el kwarg inválido -- no hacía nada útil,
        solo rompía la construcción del cliente en cualquier versión de
        PyJWT instalada.
        """
        try:
            jwks_client = jwt.PyJWKClient(JWKS_URL)
            return jwks_client.get_signing_key_from_jwt(token).key
        except Exception as e:
            raise EveSSOError(f"No se pudo verificar la firma del token contra el JWKS de EVE: {e}")
