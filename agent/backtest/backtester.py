from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from agent.strategy.base_strategy import BaseStrategy, Signal
from agent.utils.metrics import PerformanceMetrics, calculate_performance_metrics


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    metrics: PerformanceMetrics
    trades: List[dict]


class Backtester:
    def __init__(
        self,
        strategy: BaseStrategy,
        fee_bps: float = 8.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 10_000.0,
    ) -> None:
        self.strategy = strategy
        self.fee = fee_bps / 10_000
        self.slippage = slippage_bps / 10_000
        self.initial_capital = initial_capital

    def run(self, df: pd.DataFrame) -> BacktestResult:
        cash = self.initial_capital
        position_qty = 0.0
        equity = []
        trades: List[dict] = []

        for i in range(60, len(df)):
            window = df.iloc[: i + 1]
            px = float(df["close"].iloc[i])
            signal = self.strategy.generate_signal(window)

            if signal.signal == Signal.LONG and position_qty == 0:
                entry_price = px * (1 + self.slippage)
                qty = cash / entry_price
                fee = qty * entry_price * self.fee
                cash -= qty * entry_price + fee
                position_qty = qty
                trades.append({"i": i, "type": "BUY", "price": entry_price, "qty": qty, "fee": fee})

            elif signal.signal in {Signal.EXIT, Signal.SHORT} and position_qty > 0:
                exit_price = px * (1 - self.slippage)
                proceeds = position_qty * exit_price
                fee = proceeds * self.fee
                cash += proceeds - fee
                trades.append(
                    {"i": i, "type": "SELL", "price": exit_price, "qty": position_qty, "fee": fee}
                )
                position_qty = 0.0

            equity_value = cash + position_qty * px
            equity.append(equity_value)

        equity_curve = pd.Series(equity, index=df.index[60:])
        returns = equity_curve.pct_change().fillna(0.0)
        metrics = calculate_performance_metrics(equity_curve, returns)

        return BacktestResult(equity_curve=equity_curve, returns=returns, metrics=metrics, trades=trades)
