"""
Presentation/API: dependencies

Wiring de dependencias al estilo FastAPI (`Depends(...)`). Un solo lugar
donde se decide cómo se construye `ApiServices` para cada request --
mismo espíritu que la inyección manual que ya hacía `app.py` de
Streamlit (`get_repos()` con `@st.cache_resource`), adaptado al patrón
de FastAPI.

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, Header, HTTPException

from presentation.api.services import ApiServices
from domain.value_objects.user import User
from infrastructure.security.session_tokens import SessionTokenError
from shared.paths import DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH

# Instancia única reutilizada entre requests. v2 (multi-tenancy):
# ApiServices SÍ guarda estado mutable propio ahora (`_oauth_pending`,
# el mapeo state->code_verifier del login en curso) -- a propósito,
# necesita sobrevivir entre el request de /login y el de /callback.
# Compartir esta instancia es lo que hace que eso funcione; construir
# una nueva por request rompería el flujo de login.
_services = ApiServices(db_path=DB_PATH)


def get_services() -> ApiServices:
    return _services


def get_current_user(
    authorization: Optional[str] = Header(None),
    services: ApiServices = Depends(get_services),
) -> User:
    """
    Dependency para endpoints que requieren estar logueado. Espera
    `Authorization: Bearer <session_token>` -- el token que devolvió
    `POST /api/auth/callback` (o que el frontend guardó de un login
    anterior). 401 si falta el header, el token es inválido, o expiró
    -- nunca un 500 por esto, que quede claro para el frontend que debe
    volver a loguear al usuario.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Falta el header 'Authorization: Bearer <token>' -- iniciá sesión primero.",
        )
    token = authorization[len("Bearer "):].strip()
    try:
        return services.get_user_from_session_token(token)
    except SessionTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def get_optional_current_user(
    authorization: Optional[str] = Header(None),
    services: ApiServices = Depends(get_services),
) -> Optional[User]:
    """
    Igual que `get_current_user`, pero devuelve `None` en vez de 401
    cuando no hay sesión -- para endpoints donde loguearse es opcional
    (ej. `GET /api/opportunities`: `scope=discovery` es público,
    `scope=tracked` sí necesita saber quién sos; el router decide qué
    hacer con `None` según el `scope` pedido).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):].strip()
    try:
        return services.get_user_from_session_token(token)
    except (SessionTokenError, ValueError):
        return None


def require_admin_key(x_admin_key: Optional[str] = Header(None)) -> None:
    """
    Gate simple para endpoints de administración (hoy: solo
    `/api/admin/stats`) -- NO es un sistema de roles, todavía no existe
    ese concepto (`users` no tiene ninguna columna de rol/permiso). Es
    un secreto compartido: quien conoce `QUARTERMASTER_ADMIN_KEY` puede
    ver las stats, nadie más. Suficiente para "solo yo, el que lo hostea,
    puedo ver esto" -- no alcanza si en algún momento hay varios admins
    con necesidad de revocar acceso individual, eso sí necesitaría un
    rol real en `users`.
    """
    expected = os.environ.get("QUARTERMASTER_ADMIN_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Panel de admin no configurado -- falta QUARTERMASTER_ADMIN_KEY en el entorno.",
        )
    if x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Clave de admin inválida.")
