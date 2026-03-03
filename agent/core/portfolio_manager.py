from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


@dataclass
class Position:
    symbol: str
    market: str
    side: str
    quantity: float
    entry_price: float
    mark_price: float
    leverage: float = 1.0

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.mark_price)

    @property
    def unrealized_pnl(self) -> float:
        direction = 1 if self.side.upper() == "LONG" else -1
        return (self.mark_price - self.entry_price) * self.quantity * direction


class PortfolioManager:
    def __init__(self) -> None:
        self.positions: Dict[str, Position] = {}

    def update_positions(self, positions: Iterable[Position]) -> None:
        self.positions = {f"{p.market}:{p.symbol}": p for p in positions}

    def total_notional(self) -> float:
        return sum(p.notional for p in self.positions.values())

    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    def exposure_pct(self, portfolio_value: float) -> float:
        if portfolio_value <= 0:
            return 0.0
        return self.total_notional() / portfolio_value

    def open_positions_count(self) -> int:
        return len(self.positions)

    def correlated_exposure_pct(self, portfolio_value: float) -> float:
        """Conservative approximation using top symbol concentration."""
        if portfolio_value <= 0 or not self.positions:
            return 0.0

        by_base: Dict[str, float] = {}
        for pos in self.positions.values():
            base = pos.symbol.split("-")[0]
            by_base[base] = by_base.get(base, 0.0) + pos.notional

        return max(by_base.values()) / portfolio_value if by_base else 0.0
