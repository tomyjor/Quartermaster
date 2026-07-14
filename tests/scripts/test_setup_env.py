"""
Tests para scripts/setup_env.py -- genera y escribe secretos directo en
.env, sin copy-paste manual (fuente real de un bug: un '=' final del
base64 de QUARTERMASTER_ENCRYPTION_KEY cortado al copiar a mano).
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup_env.py"
ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / ".env.example"


def _load_script_module(project_root: Path):
    spec = importlib.util.spec_from_file_location("setup_env", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    # El script usa PROJECT_ROOT relativo a su propia ubicación real --
    # para testear con un .env temporal, se lo pisamos después de cargar.
    spec.loader.exec_module(mod)
    mod.PROJECT_ROOT = project_root
    mod.ENV_PATH = project_root / ".env"
    mod.ENV_EXAMPLE_PATH = project_root / ".env.example"
    return mod


def _make_fake_project(tmp_dir: Path):
    """Arma un proyecto fake con .env.example real y el módulo de encryption real, para probar de punta a punta."""
    real_project_root = Path(__file__).resolve().parents[2]
    (tmp_dir / ".env.example").write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    src_dir = tmp_dir / "src" / "infrastructure" / "security"
    src_dir.mkdir(parents=True)
    (tmp_dir / "src" / "__init__.py").touch()
    (tmp_dir / "src" / "infrastructure" / "__init__.py").touch()
    (src_dir / "__init__.py").touch()
    real_encryption_module = real_project_root / "src" / "infrastructure" / "security" / "token_encryption.py"
    (src_dir / "token_encryption.py").write_text(real_encryption_module.read_text(encoding="utf-8"), encoding="utf-8")


def test_creates_env_from_example_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        assert not (tmp_dir / ".env").exists()
        mod.main()
        assert (tmp_dir / ".env").exists()


def test_generates_all_auto_generatable_keys():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        mod.main()

        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        for key in ["QUARTERMASTER_SESSION_SECRET", "QUARTERMASTER_ENCRYPTION_KEY",
                    "QUARTERMASTER_ADMIN_KEY", "QUARTERMASTER_UI_STORAGE_SECRET"]:
            line = next(l for l in content.splitlines() if l.startswith(f"{key}="))
            value = line.split("=", 1)[1]
            assert value.strip() != "", f"{key} debería haberse generado"


def test_generated_encryption_key_is_valid_fernet_key():
    """Regresión directa del bug real -- la key generada tiene que andar de verdad con Fernet, no solo 'verse' generada."""
    from cryptography.fernet import Fernet

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        mod.main()

        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        line = next(l for l in content.splitlines() if l.startswith("QUARTERMASTER_ENCRYPTION_KEY="))
        key = line.split("=", 1)[1].strip()
        Fernet(key.encode())  # no debe lanzar


def test_never_overwrites_an_already_set_value():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        mod.main()
        content_before = (tmp_dir / ".env").read_text(encoding="utf-8")
        session_secret_before = next(
            l for l in content_before.splitlines() if l.startswith("QUARTERMASTER_SESSION_SECRET=")
        )

        mod.main()  # segunda corrida

        content_after = (tmp_dir / ".env").read_text(encoding="utf-8")
        session_secret_after = next(
            l for l in content_after.splitlines() if l.startswith("QUARTERMASTER_SESSION_SECRET=")
        )
        assert session_secret_before == session_secret_after


def test_leaves_eve_sso_credentials_empty_for_manual_completion():
    """EVE_SSO_CLIENT_ID/SECRET no se pueden generar solos -- deben quedar vacíos, no inventados."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        mod.main()

        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        for key in ["EVE_SSO_CLIENT_ID", "EVE_SSO_CLIENT_SECRET"]:
            line = next(l for l in content.splitlines() if l.startswith(f"{key}="))
            assert line.split("=", 1)[1].strip() == ""


def test_interactive_prompt_writes_eve_credentials_when_tty_available():
    """
    Simula una terminal interactiva real (sys.stdin.isatty() = True) y
    respuestas de usuario canned -- confirma que las credenciales de
    EVE se piden y se escriben directo en .env, mismo principio que las
    4 claves auto-generables (eliminar el paso de editar el archivo a
    mano).
    """
    import builtins

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        original_isatty = sys.stdin.isatty
        original_input = builtins.input
        sys.stdin.isatty = lambda: True
        responses = iter(["mi-client-id-real", "mi-client-secret-real"])
        builtins.input = lambda prompt="": next(responses)
        try:
            mod.main()
        finally:
            sys.stdin.isatty = original_isatty
            builtins.input = original_input

        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert "EVE_SSO_CLIENT_ID=mi-client-id-real" in content
        assert "EVE_SSO_CLIENT_SECRET=mi-client-secret-real" in content


def test_interactive_prompt_allows_skipping_with_empty_input():
    """Enter vacío -- no debe bloquear ni escribir nada, solo avisar que se salteó."""
    import builtins

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        original_isatty = sys.stdin.isatty
        original_input = builtins.input
        sys.stdin.isatty = lambda: True
        builtins.input = lambda prompt="": ""
        try:
            mod.main()
        finally:
            sys.stdin.isatty = original_isatty
            builtins.input = original_input

        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert "EVE_SSO_CLIENT_ID=\n" in content or content.rstrip().endswith("EVE_SSO_CLIENT_ID=")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _make_fake_project(tmp_dir)
        mod = _load_script_module(tmp_dir)

        mod.main()
        env_path = tmp_dir / ".env"
        content = env_path.read_text(encoding="utf-8").replace(
            "EVE_SSO_CLIENT_ID=", "EVE_SSO_CLIENT_ID=my-real-client-id"
        )
        env_path.write_text(content, encoding="utf-8")

        mod.main()  # no debería tocar el valor que el usuario ya puso

        final_content = env_path.read_text(encoding="utf-8")
        assert "EVE_SSO_CLIENT_ID=my-real-client-id" in final_content
