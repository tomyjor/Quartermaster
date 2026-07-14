"""
Infrastructure/Security: token_encryption

Cifra/descifra tokens OAuth2 (access/refresh de EVE SSO) antes de
guardarlos en `oauth_tokens` -- NUNCA texto plano en la base. Usa
Fernet (AES-128-CBC + HMAC-SHA256 autenticado, de la librería
`cryptography`, ya un estándar de facto para este caso de uso) --
simétrico: la misma clave cifra y descifra.

La clave viene de una variable de entorno
(`QUARTERMASTER_ENCRYPTION_KEY`), NUNCA hardcodeada en el código ni
committeada al repo -- si se compromete el código fuente, no se
compromete automáticamente la clave. Ver `generate_key()` para generar
una nueva (correr UNA vez, guardar el resultado de forma segura, nunca
regenerar sin plan de migración -- perder la clave significa perder la
capacidad de descifrar tokens ya guardados, forzando a todos los
usuarios a re-loguearse).
"""

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class TokenEncryptionError(Exception):
    """Clave faltante/incorrecta, o dato corrupto/manipulado."""
    pass


def generate_key() -> str:
    """
    Genera una clave Fernet nueva, lista para usar como
    `QUARTERMASTER_ENCRYPTION_KEY`. Correr una sola vez:

        python -c "from infrastructure.security.token_encryption import generate_key; print(generate_key())"
    """
    return Fernet.generate_key().decode("utf-8")


class TokenEncryptor:
    """
    Wrapper fino sobre Fernet -- existe para que el resto del código
    hable en términos de "cifrar/descifrar un token", no de los
    detalles de Fernet directamente (si algún día cambia el esquema de
    cifrado, este es el único lugar a tocar).
    """

    def __init__(self, key: Optional[str] = None):
        key = key or os.environ.get("QUARTERMASTER_ENCRYPTION_KEY")
        if not key:
            raise TokenEncryptionError(
                "Falta QUARTERMASTER_ENCRYPTION_KEY en el entorno. Generá una con "
                "generate_key() (una sola vez) y configurala antes de arrancar la API -- "
                "sin esto, no se pueden guardar ni leer tokens de EVE SSO."
            )
        try:
            self._fernet = Fernet(key.encode("utf-8") if isinstance(key, str) else key)
        except (ValueError, TypeError) as e:
            raise TokenEncryptionError(f"QUARTERMASTER_ENCRYPTION_KEY inválida: {e}")

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken:
            raise TokenEncryptionError(
                "No se pudo descifrar -- la clave no coincide con la que se usó para cifrar, "
                "o el dato fue manipulado/corrompido."
            )
