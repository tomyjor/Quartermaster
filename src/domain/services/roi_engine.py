"""
Domain Service: ROIEngine
Calcula ROI y costos reales según MATH-001 v1.3 (con fee de entrada
como Sunk Cost). Vocabulario generalizado (ver
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md) -- "broker fee"/"sales tax"
eran nombres de EVE Online; acá son "entry fee"/"exit fee", el mismo
concepto en cualquier mercado con comisión de intermediario + impuesto
de venta.
"""

from dataclasses import dataclass
from domain.value_objects.money import Money
from domain.value_objects.fee_profile import FeeProfile
from domain.value_objects.analysis_result import AnalysisResult


@dataclass(frozen=True)
class ROIInput:
    buy_price: Money
    sell_price: Money
    fee_profile: FeeProfile


@dataclass(frozen=True)
class TransactionCost:
    """Resultado del cálculo de costos y rentabilidad."""
    buy_price: Money
    entry_fee: Money
    total_capital_required: Money
    sell_price: Money
    total_fees_sell: Money
    net_profit: Money
    roi_percent: float


class ROIEngine:
    """
    Motor de cálculo de ROI y costos.
    Implementa estrictamente MATH-001 v1.3.
    """

    def calculate(self, input_data: ROIInput) -> AnalysisResult[TransactionCost]:
        if input_data.buy_price.amount_minor <= 0:
            raise ValueError("buy_price must be positive")
        if input_data.sell_price.amount_minor <= 0:
            raise ValueError("sell_price must be positive")

        # === Buy Leg (Sunk Cost) ===
        entry_fee = input_data.buy_price * input_data.fee_profile.entry_fee_rate
        total_capital_required = input_data.buy_price + entry_fee

        # === Sell Leg ===
        total_fees_sell = input_data.sell_price * input_data.fee_profile.total_sell_fee_rate

        # === Net Profit ===
        net_profit = (input_data.sell_price - total_fees_sell) - input_data.buy_price

        # === ROI ===
        if input_data.buy_price.amount_minor == 0:
            roi_percent = 0.0
        else:
            roi_percent = (net_profit.amount_minor / input_data.buy_price.amount_minor) * 100

        result = TransactionCost(
            buy_price=input_data.buy_price,
            entry_fee=entry_fee,
            total_capital_required=total_capital_required,
            sell_price=input_data.sell_price,
            total_fees_sell=total_fees_sell,
            net_profit=net_profit,
            roi_percent=round(roi_percent, 2)
        )

        return AnalysisResult(
            value=result,
            confidence=95.0,
            evidence_count=1,
            validation_status="Valid"
        )
