from __future__ import annotations

import pandas as pd

from agent.core.config import StrategyConfig
from agent.strategy.base_strategy import BaseStrategy, Signal, StrategySignal
from agent.utils.indicators import atr


class FuturesStrategy(BaseStrategy):
    name = "futures"

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def generate_signal(self, df: pd.DataFrame, **kwargs) -> StrategySignal:
        lookback = 20
        if len(df) < max(lookback, self.config.atr_period) + 2:
            return StrategySignal(Signal.HOLD, 0.0, {"reason": "insufficient_data"})

        high_break = df["high"].rolling(lookback).max().iloc[-2]
        low_break = df["low"].rolling(lookback).min().iloc[-2]
        last_close = float(df["close"].iloc[-1])
        atr_series = atr(df, self.config.atr_period)
        current_atr = float(atr_series.iloc[-1])
        vol_ratio = current_atr / last_close if last_close else 0.0

        leverage_hint = max(1.0, 5.0 - (vol_ratio * 20))

        if last_close > high_break:
            stop = last_close - (2 * current_atr)
            return StrategySignal(
                Signal.LONG,
                confidence=0.74,
                metadata={"stop": stop, "atr": current_atr, "leverage_hint": leverage_hint},
            )

        if last_close < low_break:
            stop = last_close + (2 * current_atr)
            return StrategySignal(
                Signal.SHORT,
                confidence=0.74,
                metadata={"stop": stop, "atr": current_atr, "leverage_hint": leverage_hint},
            )

        return StrategySignal(Signal.HOLD, 0.35, {"atr": current_atr, "leverage_hint": leverage_hint})
