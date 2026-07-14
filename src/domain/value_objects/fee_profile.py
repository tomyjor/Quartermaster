"""
Value Object: FeeProfile

Representa las tasas de fees aplicables a una transacción en un
mercado. Antes se llamaba `TaxProfile` con campos `broker_fee_rate` /
`sales_tax_rate` -- nombres tomados directo del vocabulario de EVE
Online. Renombrado como parte de la generalización del dominio (ver
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md): la idea de "fee de entrada"
+ "fee de salida" en una operación de compra/venta no es específica de
EVE, aplica a cualquier mercado con comisiones de intermediario y/o
impuesto de venta.

Mapeo con el vocabulario de EVE (para quien conoce el juego):
    entry_fee_rate -> el "broker fee" al poner una orden (skills de
                       Broker Relations lo reducen)
    exit_fee_rate  -> el "sales tax" al vender (skills de Accounting
                       lo reducen)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeProfile:
    """
    Tasas de fees derivadas de las condiciones del usuario en ese
    mercado (en EVE: skills + standings + estación).
    """
    entry_fee_rate: float   # En EVE: broker fee. Ej: 0.03 (3%)
    exit_fee_rate: float    # En EVE: sales tax. Ej: 0.036 (3.6%)

    def __post_init__(self):
        if not (0 <= self.entry_fee_rate <= 1):
            raise ValueError("entry_fee_rate must be between 0 and 1")
        if not (0 <= self.exit_fee_rate <= 1):
            raise ValueError("exit_fee_rate must be between 0 and 1")

    @property
    def total_sell_fee_rate(self) -> float:
        """Tasa total aplicada en la venta (entrada + salida)."""
        return self.entry_fee_rate + self.exit_fee_rate

    def __str__(self) -> str:
        return f"Entry fee: {self.entry_fee_rate*100:.1f}%, Exit fee: {self.exit_fee_rate*100:.1f}%"
