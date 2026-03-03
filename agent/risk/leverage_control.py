from __future__ import annotations


class LeverageControl:
    def __init__(self, max_leverage: float) -> None:
        self.max_leverage = max_leverage

    def adjust_for_volatility(self, base_leverage: float, realized_vol: float) -> float:
        """Reduce leverage as volatility increases."""
        if realized_vol >= 1.2:
            return max(1.0, min(base_leverage, self.max_leverage) * 0.35)
        if realized_vol >= 0.9:
            return max(1.0, min(base_leverage, self.max_leverage) * 0.50)
        if realized_vol >= 0.6:
            return max(1.0, min(base_leverage, self.max_leverage) * 0.70)
        return max(1.0, min(base_leverage, self.max_leverage))

    @staticmethod
    def liquidation_distance_pct(mark_price: float, liquidation_price: float, side: str) -> float:
        if mark_price <= 0:
            return 0.0
        if side.upper() == "LONG":
            return max(0.0, (mark_price - liquidation_price) / mark_price)
        return max(0.0, (liquidation_price - mark_price) / mark_price)
