from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from agent.strategy.base_strategy import BaseStrategy, Signal
from agent.utils.metrics import PerformanceMetrics, calculate_performance_metrics


@dataclass
class DerivativesBacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    metrics: PerformanceMetrics
    liquidation_events: int
    trades: List[dict]


class DerivativesBacktester:
    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 10_000.0,
        leverage: float = 3.0,
        fee_bps: float = 10.0,
        slippage_bps: float = 7.0,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.fee = fee_bps / 10_000
        self.slippage = slippage_bps / 10_000

    def run(
        self,
        df: pd.DataFrame,
        funding_rate_col: str = "funding_rate",
        funding_interval_bars: int = 8,
    ) -> DerivativesBacktestResult:
        cash = self.initial_capital
        position_qty = 0.0
        side = "FLAT"
        entry_price = 0.0
        liquidation_events = 0
        equity = []
        trades: List[dict] = []

        for i in range(80, len(df)):
            window = df.iloc[: i + 1]
            px = float(df["close"].iloc[i])
            high = float(df["high"].iloc[i])
            low = float(df["low"].iloc[i])
            funding_rate = float(df[funding_rate_col].iloc[i]) if funding_rate_col in df.columns else 0.0

            signal = self.strategy.generate_signal(window, funding_rate=funding_rate)

            notional = abs(position_qty) * px
            if side != "FLAT" and i % funding_interval_bars == 0:
                funding_cost = notional * funding_rate * (1 if side == "LONG" else -1)
                cash -= funding_cost

            if side == "LONG":
                liq = entry_price * (1 - (1 / self.leverage))
                if low <= liq:
                    cash -= abs(position_qty) * entry_price / self.leverage
                    position_qty = 0.0
                    side = "FLAT"
                    liquidation_events += 1
            elif side == "SHORT":
                liq = entry_price * (1 + (1 / self.leverage))
                if high >= liq:
                    cash -= abs(position_qty) * entry_price / self.leverage
                    position_qty = 0.0
                    side = "FLAT"
                    liquidation_events += 1

            if side == "FLAT" and signal.signal in {Signal.LONG, Signal.SHORT}:
                side = "LONG" if signal.signal == Signal.LONG else "SHORT"
                fill = px * (1 + self.slippage if side == "LONG" else 1 - self.slippage)
                notional_target = cash * self.leverage
                position_qty = (notional_target / fill) * (1 if side == "LONG" else -1)
                fee = abs(position_qty) * fill * self.fee
                cash -= fee
                entry_price = fill
                trades.append({"i": i, "type": f"OPEN_{side}", "price": fill, "qty": position_qty, "fee": fee})

            elif side != "FLAT" and signal.signal in {Signal.EXIT, Signal.LONG, Signal.SHORT}:
                close_fill = px * (1 - self.slippage if side == "LONG" else 1 + self.slippage)
                pnl = (close_fill - entry_price) * position_qty
                fee = abs(position_qty) * close_fill * self.fee
                cash += pnl - fee
                trades.append(
                    {"i": i, "type": f"CLOSE_{side}", "price": close_fill, "qty": position_qty, "pnl": pnl, "fee": fee}
                )
                position_qty = 0.0
                side = "FLAT"
                entry_price = 0.0

            equity_value = cash
            if side != "FLAT":
                equity_value += (px - entry_price) * position_qty
            equity.append(equity_value)

        equity_curve = pd.Series(equity, index=df.index[80:])
        returns = equity_curve.pct_change().fillna(0.0)
        metrics = calculate_performance_metrics(equity_curve, returns)

        return DerivativesBacktestResult(
            equity_curve=equity_curve,
            returns=returns,
            metrics=metrics,
            liquidation_events=liquidation_events,
            trades=trades,
        )
