from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, List


@dataclass
class TradeRecord:
    timestamp: datetime
    market: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str


@dataclass
class EngineState:
    enabled: bool = True
    balances: Dict[str, float] = field(default_factory=dict)
    positions: Dict[str, Dict] = field(default_factory=dict)
    funding_rates: Dict[str, float] = field(default_factory=dict)
    exposure_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    trades: List[TradeRecord] = field(default_factory=list)


class StateManager:
    """Thread-safe mutable runtime state."""

    def __init__(self) -> None:
        self._state = EngineState()
        self._lock = Lock()

    def snapshot(self) -> EngineState:
        with self._lock:
            return EngineState(
                enabled=self._state.enabled,
                balances=dict(self._state.balances),
                positions=dict(self._state.positions),
                funding_rates=dict(self._state.funding_rates),
                exposure_pct=self._state.exposure_pct,
                daily_pnl_pct=self._state.daily_pnl_pct,
                trades=list(self._state.trades),
            )

    def update_balances(self, balances: Dict[str, float]) -> None:
        with self._lock:
            self._state.balances.update(balances)

    def update_positions(self, positions: Dict[str, Dict]) -> None:
        with self._lock:
            self._state.positions = positions

    def update_funding_rates(self, rates: Dict[str, float]) -> None:
        with self._lock:
            self._state.funding_rates = rates

    def set_exposure_pct(self, exposure_pct: float) -> None:
        with self._lock:
            self._state.exposure_pct = exposure_pct

    def set_daily_pnl_pct(self, daily_pnl_pct: float) -> None:
        with self._lock:
            self._state.daily_pnl_pct = daily_pnl_pct

    def add_trade(self, trade: TradeRecord) -> None:
        with self._lock:
            self._state.trades.append(trade)

    def disable_engine(self) -> None:
        with self._lock:
            self._state.enabled = False

    def is_enabled(self) -> bool:
        with self._lock:
            return self._state.enabled
