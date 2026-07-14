"""
Presentation/API: router de autenticación (EVE SSO).

⚠️ NO EJECUTADO -- requiere `fastapi`. Ver nota en `schemas.py`. Además,
el intercambio real de tokens contra login.eveonline.com nunca se probó
contra el servidor real en este entorno (sin red) -- ver docstring
completo en `infrastructure/auth/eve_sso_client.py`.

Requiere configurar en el entorno antes de arrancar la API:
    EVE_SSO_CLIENT_ID / EVE_SSO_CLIENT_SECRET   (de developers.eveonline.com)
    QUARTERMASTER_SESSION_SECRET                (python -c "import secrets; print(secrets.token_urlsafe(32))")
    QUARTERMASTER_ENCRYPTION_KEY                (python -c "from infrastructure.security.token_encryption import generate_key; print(generate_key())")
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from presentation.api.dependencies import get_services, get_current_user
from presentation.api.services import ApiServices
from domain.value_objects.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: Debe coincidir EXACTO con la URL de callback configurada en
#: developers.eveonline.com para esta aplicación.
CALLBACK_PATH = "/api/auth/callback"


@router.get("/login")
def login(
    frontend_redirect: str = Query(
        ..., description="A dónde volver una vez que el login termine (la URL de Streamlit/NiceGUI)."
    ),
    services: ApiServices = Depends(get_services),
):
    """
    Redirige al usuario a EVE SSO para iniciar sesión. El frontend que
    quiera ofrecer "Login con EVE" debe apuntar un link/botón acá,
    pasando su propia URL en `frontend_redirect` para saber a dónde
    volver.
    """
    # ⚠️ Esta URL de callback debe coincidir exacto con la registrada en
    # developers.eveonline.com. Hardcodeada a localhost:8000 por ahora
    # -- si la API corre en otro host/puerto en producción, esto debería
    # venir de una variable de entorno en vez de estar fijo acá.
    callback_url = f"http://127.0.0.1:8000{CALLBACK_PATH}"
    try:
        authorize_url = services.get_eve_login_url(
            redirect_uri=callback_url, frontend_redirect=frontend_redirect
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return RedirectResponse(authorize_url)


@router.get("/callback")
def callback(
    code: str = Query(...),
    state: str = Query(...),
    services: ApiServices = Depends(get_services),
):
    """
    EVE SSO redirige acá después de que el usuario aprueba (o si algo
    sale mal, con un `error` en vez de `code` -- no cubierto todavía,
    ver nota abajo). Intercambia el code por tokens, resuelve la
    identidad, y manda al browser de vuelta al frontend con el token de
    sesión como query param.

    ⚠️ Pendiente: manejar explícitamente el caso en que el usuario
    CANCELA el login en la pantalla de EVE (viene `error=access_denied`
    en vez de `code`) -- hoy eso rompería con un error de FastAPI poco
    claro (falta el parámetro `code` requerido) en vez de un mensaje
    entendible. Anotado para la primera vez que se pruebe con el flujo
    real.
    """
    try:
        session_token, frontend_redirect = services.handle_eve_callback(code=code, state=state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    separator = "&" if "?" in frontend_redirect else "?"
    return RedirectResponse(f"{frontend_redirect}{separator}session_token={session_token}")


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """Info del usuario autenticado -- el frontend la usa para confirmar que la sesión sigue viva."""
    return {
        "user_id": user.id,
        "eve_character_id": user.eve_character_id,
        "eve_character_name": user.eve_character_name,
    }
