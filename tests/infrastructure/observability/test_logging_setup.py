"""
Tests para logging_setup -- stdlib puro, sin dependencias externas, se
puede probar de verdad (escritura real a archivo temporal).
"""

import logging
import tempfile
import importlib
from pathlib import Path

import shared.paths as paths
import infrastructure.observability.logging_setup as ls


def _fresh_logging_module(tmp_root: Path):
    """Reconfigura el módulo apuntando a una carpeta temporal, para no ensuciar el proyecto real."""
    importlib.reload(ls)
    ls.LOG_DIR = tmp_root / "logs"
    ls.LOG_FILE = ls.LOG_DIR / "quartermaster.log"
    ls._configured = False
    return ls


def test_setup_creates_log_file_and_writes_formatted_entries():
    tmp_root = Path(tempfile.mkdtemp())
    mod = _fresh_logging_module(tmp_root)

    mod.setup_logging(level=logging.INFO)
    logger = mod.get_logger("test_module")
    logger.info("mensaje de prueba")

    assert mod.LOG_FILE.exists()
    content = mod.LOG_FILE.read_text()
    assert "mensaje de prueba" in content
    assert "quartermaster.test_module" in content
    assert "INFO" in content


def test_setup_is_idempotent_does_not_duplicate_handlers():
    tmp_root = Path(tempfile.mkdtemp())
    mod = _fresh_logging_module(tmp_root)

    mod.setup_logging()
    root_logger = logging.getLogger("quartermaster")
    handlers_before = len(root_logger.handlers)

    mod.setup_logging()
    handlers_after = len(root_logger.handlers)

    assert handlers_before == handlers_after


def test_get_logger_returns_namespaced_logger():
    tmp_root = Path(tempfile.mkdtemp())
    mod = _fresh_logging_module(tmp_root)
    mod.setup_logging()

    logger = mod.get_logger("my_module")

    assert logger.name == "quartermaster.my_module"


def test_log_rotation_settings_are_reasonable():
    """No corre una rotación real (sería lento), solo confirma que los límites son sensatos."""
    assert ls.MAX_BYTES > 0
    assert ls.BACKUP_COUNT >= 1
