"""
Value Object: User

Identidad de un usuario autenticado. NUNCA guardamos contraseñas -- la
autenticación real la hace el servidor de EVE SSO (OAuth2); acá solo
persistimos qué personaje de EVE es cada usuario, para poder separar
la watchlist y cualquier otro dato personal futuro entre usuarios
distintos.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    eve_character_id: int
    eve_character_name: str

    def __post_init__(self):
        if not self.eve_character_name:
            raise ValueError("eve_character_name no puede estar vacío")
