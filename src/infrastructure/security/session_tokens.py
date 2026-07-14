"""
Infrastructure/Security: session_tokens

Emite y verifica JWTs de SESIÓN propios de Quartermaster -- NO son los
tokens de EVE SSO (esos se cifran y guardan aparte, ver
`token_encryption.py`). Estos son los que el frontend (Streamlit,
NiceGUI, o cualquier cliente futuro) manda en cada request para probar
"soy el usuario X, ya me autentiqué antes" -- evita que cada request
tenga que ir y volver contra el servidor de EVE.

Firmados con HS256 (simétrico, misma clave firma y verifica) usando
`QUARTERMASTER_SESSION_SECRET` del entorno -- clave DISTINTA de
`QUARTERMASTER_ENCRYPTION_KEY` a propósito: son dos superficies de
ataque distintas (una protege tokens de EVE en reposo, esta protege la
sesión activa), comprometer una no debería comprometer la otra.

Vida corta por diseño (`SESSION_TTL_HOURS`, default 24h) -- si un token
de sesión se filtra, la ventana de daño es acotada. No hay refresh
automático todavía (Fase 2 de esto: renovar sesión sin re-loguear).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt


class SessionTokenError(Exception):
    """Clave faltante, token expirado, o token inválido/manipulado."""
    pass


SESSION_TTL_HOURS = 24
ALGORITHM = "HS256"


def _get_secret() -> str:
    secret = os.environ.get("QUARTERMASTER_SESSION_SECRET")
    if not secret:
        raise SessionTokenError(
            "Falta QUARTERMASTER_SESSION_SECRET en el entorno. Generá una con "
            "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"` y configurala "
            "antes de arrancar la API -- sin esto no se pueden emitir ni verificar sesiones."
        )
    return secret


def issue_session_token(user_id: int, eve_character_name: str) -> str:
    """
    Emite un JWT de sesión para un usuario ya autenticado (después de
    un login exitoso vía EVE SSO). El frontend lo guarda y lo manda en
    cada request subsiguiente (header `Authorization: Bearer <token>`).
    """
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "character_name": eve_character_name,
        "iat": now,
        "exp": now + timedelta(hours=SESSION_TTL_HOURS),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_session_token(token: str) -> dict:
    """
    Verifica y decodifica un JWT de sesión. Levanta `SessionTokenError`
    con un mensaje claro si expiró o es inválido -- el caller (endpoint
    protegido de la API) debería traducir esto a un 401, no a un 500.
    """
    secret = _get_secret()
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise SessionTokenError("La sesión expiró -- hay que volver a loguearse.")
    except jwt.InvalidTokenError as e:
        raise SessionTokenError(f"Token de sesión inválido: {e}")
