"""
Value Object: Money
Representa cantidades de dinero con precisión usando minor units.

v1.1: `currency` ya NO tiene default. Antes `currency: str = "ISK"`
significaba que construir un `Money` sin pasar moneda asumía EVE en
silencio -- no rompía nada al usarlo con otro mercado, simplemente
mentía en los datos sin avisar. Es el tipo de acoplamiento más
peligroso: no se nota hasta que alguien confía en un número que en
realidad nunca fue verificado. Ver docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md §2.
"""

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class Money:
    """
    Cantidad de dinero inmutable.
    Se trabaja siempre en minor units (ej: centavos, o el equivalente
    de la moneda que corresponda).
    """
    amount_minor: int
    currency: str

    def __post_init__(self):
        # Permitimos valores negativos (pérdidas, net profit negativo, etc.)
        # Esto es necesario en dominios financieros.
        if not self.currency:
            raise ValueError("Currency must be specified")

    @property
    def amount(self) -> float:
        """Devuelve el valor en unidades normales (ej: ISK completos)."""
        return self.amount_minor / 100

    def __str__(self) -> str:
        return f"{self.amount:,.2f} {self.currency}"

    def __add__(self, other: Self) -> Self:
        if self.currency != other.currency:
            raise ValueError("Cannot add Money with different currencies")
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Self) -> Self:
        if self.currency != other.currency:
            raise ValueError("Cannot subtract Money with different currencies")
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __mul__(self, scalar: float) -> Self:
        return Money(int(round(self.amount_minor * scalar)), self.currency)

    def __truediv__(self, scalar: float) -> Self:
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Money by zero")
        return Money(int(self.amount_minor / scalar), self.currency)
