"""
Port: UserRepository

Interfaz abstracta para persistir/consultar usuarios -- mismo patrón
que `MarketRepository`/`TypeRepository`. El dominio y la capa de
aplicación dependen de esto, nunca de `SQLiteUserRepository` directo.
"""

from abc import ABC, abstractmethod
from typing import Optional

from domain.value_objects.user import User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]:
        ...

    @abstractmethod
    def get_by_eve_character_id(self, eve_character_id: int) -> Optional[User]:
        ...

    @abstractmethod
    def create_or_update_login(self, eve_character_id: int, eve_character_name: str) -> User:
        """
        Login vía EVE SSO: si el personaje ya existe, actualiza
        `last_login_at` y el nombre (puede cambiar si el jugador
        renombra el personaje); si no existe, lo crea. Idempotente por
        diseño -- cada login exitoso llama esto, sin necesidad de un
        paso de "registro" separado.
        """
        ...
