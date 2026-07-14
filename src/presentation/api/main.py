"""
Presentation/API: main

Entry point de la API FastAPI. Fase 1 de
docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md: extrae los use cases detrás
de endpoints HTTP, Streamlit se mantiene vivo pero pasa a consumir esta
API en vez de llamar a los use cases directo.

⚠️ NO EJECUTADO -- requiere `fastapi` + `uvicorn`. Ver nota en
`schemas.py`. Para correrlo (una vez instaladas las deps, ver
`pyproject.toml` -> `[project.optional-dependencies] api`):

    pip install -e ".[api]"
    uvicorn presentation.api.main:app --reload --app-dir src

Y probarlo con, por ejemplo:

    curl http://127.0.0.1:8000/api/sync/status
    curl -X POST http://127.0.0.1:8000/api/sync/seed
    curl "http://127.0.0.1:8000/api/opportunities?scope=discovery&max_results=5"

Documentación interactiva autogenerada en http://127.0.0.1:8000/docs
(Swagger UI, viene gratis con FastAPI).
"""

import time

# Carga .env ANTES que cualquier otro import del proyecto -- varios
# módulos (services.py, dependencies.py) leen os.environ.get(...) al
# momento de construirse (no de forma lazy), así que si esto corriera
# después de esos imports, las variables del .env llegarían tarde.
# No falla si no hay .env (por ejemplo, en un deploy donde las variables
# ya vienen seteadas por el sistema en vez de un archivo).
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from presentation.api.routers import opportunities, tracked_items, search, sync, auth, admin, catalog
from presentation.api.dependencies import get_services
from infrastructure.jobs.scheduler import build_scheduler
from infrastructure.observability.logging_setup import setup_logging, get_logger

# Configurar ANTES de crear la app -- todo lo que loguee cualquier
# módulo importado después de esta línea ya sale con handlers reales
# (consola + archivo rotativo). Ver changelog en logging_setup.py: antes
# de esto, los logger.info(...) que ya existían en el código no iban a
# ningún lado -- había loggers pero cero handlers configurados.
setup_logging()
logger = get_logger("api")

app = FastAPI(
    title="Quartermaster API",
    description="Decision Intelligence para trading en Jita (EVE Online) -- capa HTTP, Fase 1.",
    version="1.0.0",
)

# CORS abierto en desarrollo -- Streamlit (Fase 1) y, más adelante,
# NiceGUI (Fase 2) pueden correr en un puerto distinto al de la API.
# Restringir origins en producción si el deploy final expone esto más
# allá de localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Loguea cada request (método, path, status, duración) -- la base
    mínima de observabilidad para saber qué está pasando en producción
    sin tener que reproducir el problema en vivo. No loguea el usuario
    autenticado acá (el middleware corre antes de que se resuelvan las
    dependencies de FastAPI, no tiene acceso fácil al resultado de
    `get_current_user`) -- eventos específicos de usuario (logins,
    tracking) se loguean donde ocurren, ver `ApiServices`.
    """
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.1f",
            request.method, request.url.path, duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    log_level = logger.warning if response.status_code >= 400 else logger.info
    log_level(
        "request method=%s path=%s status=%s duration_ms=%.1f",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


app.include_router(opportunities.router)
app.include_router(tracked_items.router)
app.include_router(search.router)
app.include_router(sync.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(catalog.router)


@app.on_event("startup")
def trigger_initial_seed_if_needed() -> None:
    """
    Primera ejecución: si nunca se corrió un Smart Auto-Seed completo
    (`system_state.last_full_seed_at` ausente), lo dispara solo, en un
    thread separado para no bloquear el arranque del servidor. Ver
    `infrastructure/jobs/seed_job.py` y
    docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md §5.
    """
    services = get_services()
    if not services.needs_initial_seed():
        logger.info("Smart Auto-Seed ya corrió antes (last_full_seed_at presente), no se dispara de nuevo.")
        return

    import threading
    logger.info("Primera ejecución detectada -- disparando Smart Auto-Seed en background.")
    threading.Thread(target=services.run_seed_job, daemon=True).start()


@app.on_event("startup")
def start_periodic_scheduler() -> None:
    """Arranca el refresco periódico (order book cada 20 min, historial
    completo cada 12 hs -- ver `infrastructure/jobs/scheduler.py`)."""
    services = get_services()
    scheduler = build_scheduler(db_path=services.db_path, region_id=services.region_id)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler periódico arrancado.")


@app.on_event("shutdown")
def stop_periodic_scheduler() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler periódico detenido.")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
