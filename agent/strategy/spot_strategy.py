from __future__ import annotations

import pandas as pd

from agent.core.config import StrategyConfig
from agent.strategy.base_strategy import BaseStrategy, Signal, StrategySignal
from agent.utils.indicators import ema, rsi


class SpotStrategy(BaseStrategy):
    name = "spot"

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def generate_signal(self, df: pd.DataFrame, **kwargs) -> StrategySignal:
        if len(df) < max(self.config.ema_slow, self.config.rsi_period) + 2:
            return StrategySignal(Signal.HOLD, 0.0, {"reason": "insufficient_data"})

        close = df["close"]
        volume = df["volume"]
        fast = ema(close, self.config.ema_fast)
        slow = ema(close, self.config.ema_slow)
        rsi_val = rsi(close, self.config.rsi_period)

        vol_ma = volume.rolling(self.config.volume_lookback).mean()
        vol_confirm = volume.iloc[-1] > vol_ma.iloc[-1]

        bullish_cross = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        bearish_cross = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

        if bullish_cross and rsi_val.iloc[-1] < self.config.rsi_overbought and vol_confirm:
            return StrategySignal(
                Signal.LONG,
                confidence=0.72,
                metadata={"rsi": float(rsi_val.iloc[-1]), "vol_confirm": bool(vol_confirm)},
            )

        if bearish_cross and rsi_val.iloc[-1] > self.config.rsi_oversold:
            return StrategySignal(
                Signal.EXIT,
                confidence=0.63,
                metadata={"rsi": float(rsi_val.iloc[-1]), "vol_confirm": bool(vol_confirm)},
            )

        return StrategySignal(Signal.HOLD, 0.3, {"rsi": float(rsi_val.iloc[-1])})
