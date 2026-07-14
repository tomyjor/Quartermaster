"""
Genera y ESCRIBE directo en `.env` los secretos que se pueden generar
solos, sin copy-paste manual.

Hallazgo real: el usuario tuvo un bug con `QUARTERMASTER_ENCRYPTION_KEY`
porque al copiar el valor generado a mano, el `=` final del base64
quedó cortado (típico de copiar con doble-click, que no toma
caracteres de puntuación como parte de la "palabra"). Este script
elimina el copy-paste por completo para las 4 claves que se pueden
generar automáticamente -- las escribe directo en el archivo.

Lo que SÍ sigue necesitando que el usuario lo complete a mano:
`EVE_SSO_CLIENT_ID` / `EVE_SSO_CLIENT_SECRET` -- esos vienen de
registrar una app en developers.eveonline.com, no hay forma de
generarlos localmente.

Uso:
    python scripts/setup_env.py

Seguro de correr varias veces -- NUNCA pisa un valor que ya esté
seteado, solo completa los que están vacíos. Si `.env` no existe
todavía, lo crea a partir de `.env.example`.
"""

import re
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

#: Claves que este script puede generar solo -- todas usan
#: `secrets.token_urlsafe(32)`, incluida QUARTERMASTER_ENCRYPTION_KEY:
#: no hace falta el formato específico de Fernet acá porque
#: `token_encryption.py` ya sabe derivar una key Fernet válida a partir
#: de cualquier string suficientemente random (ver ese módulo) -- pero
#: para no depender de esa lógica y mantener este script simple, se usa
#: la MISMA función que ya generaba la key manualmente
#: (`infrastructure.security.token_encryption.generate_key`).
AUTO_GENERATABLE_KEYS = {
    "QUARTERMASTER_SESSION_SECRET": lambda: secrets.token_urlsafe(32),
    "QUARTERMASTER_ADMIN_KEY": lambda: secrets.token_urlsafe(24),
    "QUARTERMASTER_UI_STORAGE_SECRET": lambda: secrets.token_urlsafe(32),
}


def _generate_encryption_key() -> str:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from infrastructure.security.token_encryption import generate_key
    return generate_key()


def _parse_env_lines(text: str) -> list[str]:
    return text.splitlines()


def main() -> None:
    if not ENV_PATH.exists():
        if not ENV_EXAMPLE_PATH.exists():
            print("❌ No existe .env ni .env.example -- no hay nada de qué partir.")
            sys.exit(1)
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print("📄 .env no existía -- creado a partir de .env.example.")

    lines = _parse_env_lines(ENV_PATH.read_text(encoding="utf-8"))
    generators = dict(AUTO_GENERATABLE_KEYS)
    generators["QUARTERMASTER_ENCRYPTION_KEY"] = _generate_encryption_key

    generated_count = 0
    for i, line in enumerate(lines):
        match = re.match(r"^([A-Z_]+)=(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key in generators and not value.strip():
            new_value = generators[key]()
            lines[i] = f"{key}={new_value}"
            print(f"✅ {key} generado y escrito directo en .env (sin copy-paste).")
            generated_count += 1

    if generated_count == 0:
        print("✅ Todas las claves auto-generables ya estaban completas -- no se tocó nada.")
    else:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n{generated_count} clave(s) escrita(s) en .env.")

    lines = _maybe_prompt_for_eve_credentials(lines)


def _maybe_prompt_for_eve_credentials(lines: list[str]) -> list[str]:
    """
    A diferencia de las 4 claves de arriba, `EVE_SSO_CLIENT_ID` /
    `EVE_SSO_CLIENT_SECRET` NO se pueden generar localmente -- salen de
    registrar una app en developers.eveonline.com, un paso manual en el
    sitio de CCP que ningún script puede hacer por el usuario. Lo que
    SÍ se puede automatizar es la parte de ACÁ para adelante: en vez de
    pedirle que abra el .env en un editor de texto y pegue los valores
    a mano, se los pide accá mismo, en la terminal, y los escribe
    directo -- un paso menos, mismo principio que las claves generadas
    solas (eliminar fricción manual donde se pueda).

    Si el usuario no tiene los valores todavía (typical primera vez),
    puede dejar vacío con Enter y completarlo después -- no bloquea el
    arranque del resto de la app.
    """
    missing = []
    for key in ("EVE_SSO_CLIENT_ID", "EVE_SSO_CLIENT_SECRET"):
        for line in lines:
            match = re.match(rf"^{key}=(.*)$", line)
            if match and not match.group(1).strip():
                missing.append(key)
                break

    if not missing:
        return lines

    if not sys.stdin.isatty():
        # No hay terminal interactiva de verdad (ej. corriendo en un
        # test, o en un entorno sin consola) -- no se puede hacer
        # input() acá, avisar y seguir sin bloquear.
        print(
            f"\n⚠️  Estas claves NO se pueden generar solas, hay que completarlas "
            f"a mano (ver docs/SETUP.md paso 2): {', '.join(missing)}"
        )
        return lines

    print(
        "\n📋 Faltan las credenciales de EVE SSO -- si ya registraste una app en "
        "developers.eveonline.com, pegalas acá y las guardo directo (Enter vacío "
        "para saltear y completarlo después):\n"
        "   Si todavía no registraste la app: entrá a developers.eveonline.com,\n"
        "   'Create New Application', Connection Type = 'Authentication Only',\n"
        "   Callback URL = http://127.0.0.1:8000/api/auth/callback\n"
    )

    updated = False
    for key in missing:
        label = "Client ID" if key == "EVE_SSO_CLIENT_ID" else "Client Secret"
        value = input(f"   {label}: ").strip()
        if value:
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    updated = True
                    break

    if updated:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("✅ Credenciales de EVE guardadas en .env.")
    else:
        print("↷ Salteado -- completá EVE_SSO_CLIENT_ID/SECRET en .env cuando los tengas.")

    return lines


if __name__ == "__main__":
    main()
