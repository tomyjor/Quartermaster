"""
Infrastructure/Observability: logging_setup

Hallazgo real revisando el proyecto: existían loggers
(`logging.getLogger("quartermaster.api")`, `"...scheduler"`) pero
NINGÚN handler configurado en ningún lado -- sin `logging.basicConfig()`
ni nada equivalente, todos los `logger.info(...)` que ya estaban en el
código no iban a ningún lado útil (el logger raíz de Python sin
handlers configurados descarta todo por debajo de WARNING en
silencio). Este módulo es la pieza que faltaba: configura handlers
reales una sola vez, al arrancar la API.

Dos destinos:
- **Consola** (stdout) -- mismo lugar donde ya escribe uvicorn, para
  que todo el output de una corrida quede junto en una sola terminal.
- **Archivo rotativo** (`logs/quartermaster.log`) -- persiste entre
  reinicios, no crece sin límite (rota a los 10MB, guarda hasta 5
  archivos viejos). Es lo que hace posible mirar "qué pasó ayer a la
  noche" sin haber estado mirando la terminal en el momento.

Formato estructurado (timestamp, nivel, logger, mensaje, +contexto
extra como user_id/request_id cuando está disponible) -- pensado para
poder buscar/filtrar log files a mano (grep) sin herramientas
adicionales, dado que hoy no hay ningún servicio de logging centralizado
(Sentry, Datadog, etc.) conectado. Si el proyecto crece a necesitar eso,
este es el único lugar a tocar para agregar un handler más.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from shared.paths import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "quartermaster.log"

#: 10MB por archivo, hasta 5 archivos viejos guardados (~50MB total como techo).
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configura logging estructurado para toda la app -- llamar UNA vez,
    al arrancar la API (ver `presentation/api/main.py`). Idempotente:
    llamarlo de nuevo no duplica handlers (importante porque
    `--reload` de uvicorn puede re-ejecutar el módulo de arranque).
    """
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger("quartermaster")
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    # No propagar al root logger de Python -- evita que librerías
    # externas (uvicorn, etc.) dupliquen el formato o interfieran.
    root_logger.propagate = False

    _configured = True
    root_logger.info("Logging configurado -- archivo: %s", LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """
    Atajo para obtener un logger bajo el namespace `quartermaster.*` --
    todos comparten los mismos handlers configurados por
    `setup_logging()`, sin que cada módulo tenga que saber de archivos
    ni de rotación.
    """
    return logging.getLogger(f"quartermaster.{name}")
