from __future__ import annotations

import pandas as pd

from agent.core.config import StrategyConfig
from agent.strategy.base_strategy import BaseStrategy, Signal, StrategySignal
from agent.utils.indicators import ema


class PerpStrategy(BaseStrategy):
    name = "perps"

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def generate_signal(self, df: pd.DataFrame, funding_rate: float = 0.0, **kwargs) -> StrategySignal:
        if len(df) < self.config.ema_slow + 2:
            return StrategySignal(Signal.HOLD, 0.0, {"reason": "insufficient_data"})

        close = df["close"]
        trend_fast = ema(close, self.config.ema_fast).iloc[-1]
        trend_slow = ema(close, self.config.ema_slow).iloc[-1]
        trend_up = trend_fast > trend_slow

        extreme_funding = abs(funding_rate) > 0.0015

        if trend_up and funding_rate < 0.0015:
            return StrategySignal(
                Signal.LONG,
                0.68,
                {
                    "funding_rate": funding_rate,
                    "extreme_funding": extreme_funding,
                    "avoid_against_extreme": True,
                },
            )

        if (not trend_up) and funding_rate > -0.0015:
            return StrategySignal(
                Signal.SHORT,
                0.68,
                {
                    "funding_rate": funding_rate,
                    "extreme_funding": extreme_funding,
                    "avoid_against_extreme": True,
                },
            )

        if extreme_funding:
            return StrategySignal(Signal.EXIT, 0.6, {"reason": "funding_extreme", "funding_rate": funding_rate})

        return StrategySignal(Signal.HOLD, 0.3, {"funding_rate": funding_rate})
