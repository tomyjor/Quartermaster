"""Tests para TokenEncryptor -- cifrado de tokens OAuth2 en reposo."""

import os

from infrastructure.security.token_encryption import (
    TokenEncryptor, TokenEncryptionError, generate_key
)


def test_encrypt_then_decrypt_roundtrips_correctly():
    key = generate_key()
    enc = TokenEncryptor(key=key)
    plaintext = "un-token-de-ejemplo-bastante-largo.con.puntos.como.jwt"

    ciphertext = enc.encrypt(plaintext)
    assert enc.decrypt(ciphertext) == plaintext


def test_ciphertext_never_contains_plaintext():
    key = generate_key()
    enc = TokenEncryptor(key=key)
    plaintext = "secreto-super-sensible-token-oauth"

    ciphertext = enc.encrypt(plaintext)
    assert plaintext.encode("utf-8") not in ciphertext


def test_wrong_key_fails_to_decrypt_instead_of_returning_garbage():
    enc_right = TokenEncryptor(key=generate_key())
    enc_wrong = TokenEncryptor(key=generate_key())

    ciphertext = enc_right.encrypt("algo")
    try:
        enc_wrong.decrypt(ciphertext)
        assert False, "debería haber levantado TokenEncryptionError"
    except TokenEncryptionError:
        pass


def test_missing_key_raises_clear_error():
    os.environ.pop("QUARTERMASTER_ENCRYPTION_KEY", None)
    try:
        TokenEncryptor()
        assert False, "debería exigir una clave"
    except TokenEncryptionError as e:
        assert "QUARTERMASTER_ENCRYPTION_KEY" in str(e)


def test_reads_key_from_environment_variable_when_not_passed_explicitly():
    key = generate_key()
    os.environ["QUARTERMASTER_ENCRYPTION_KEY"] = key
    try:
        enc = TokenEncryptor()  # sin pasar key= -- debe leerla del entorno
        ciphertext = enc.encrypt("test")
        assert enc.decrypt(ciphertext) == "test"
    finally:
        os.environ.pop("QUARTERMASTER_ENCRYPTION_KEY", None)


def test_invalid_key_format_raises_clear_error():
    try:
        TokenEncryptor(key="esto-no-es-una-clave-fernet-valida")
        assert False, "deberia rechazar una clave con formato invalido"
    except TokenEncryptionError:
        pass
