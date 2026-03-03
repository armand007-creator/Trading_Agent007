from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from agent.core.config import StrategyConfig
from agent.strategy.base_strategy import BaseStrategy, Signal, StrategySignal
from agent.utils.indicators import atr, ema_slope, returns, rsi


@dataclass
class MLTrainingState:
    trained: bool = False
    threshold: float = 0.55


class MLStrategy(BaseStrategy):
    name = "ml"

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.model = LogisticRegression(max_iter=500)
        self.state = MLTrainingState()

    def _feature_frame(self, df: pd.DataFrame, funding_rate_series: pd.Series | None = None) -> pd.DataFrame:
        features = pd.DataFrame(index=df.index)
        features["returns"] = returns(df["close"])
        features["rsi"] = rsi(df["close"], self.config.rsi_period)
        features["ema_slope"] = ema_slope(df["close"], span=self.config.ema_fast)
        features["atr"] = atr(df, self.config.atr_period) / df["close"]

        if funding_rate_series is None:
            features["funding_rate"] = 0.0
        else:
            features["funding_rate"] = funding_rate_series.reindex(df.index).fillna(method="ffill").fillna(0.0)

        return features.dropna()

    def fit(self, df: pd.DataFrame, funding_rate_series: pd.Series | None = None) -> None:
        features = self._feature_frame(df, funding_rate_series)
        if len(features) < 200:
            self.state.trained = False
            return

        aligned_close = df.loc[features.index, "close"]
        target = (aligned_close.shift(-1) > aligned_close).astype(int).dropna()
        X = features.loc[target.index]
        y = target

        if len(np.unique(y)) < 2:
            self.state.trained = False
            return

        self.model.fit(X, y)
        self.state.trained = True

    def generate_signal(self, df: pd.DataFrame, funding_rate_series: pd.Series | None = None, **kwargs) -> StrategySignal:
        features = self._feature_frame(df, funding_rate_series)
        if features.empty:
            return StrategySignal(Signal.HOLD, 0.0, {"reason": "insufficient_features"})

        if not self.state.trained:
            self.fit(df, funding_rate_series)

        if not self.state.trained:
            last_ret = features["returns"].iloc[-1]
            fallback = Signal.LONG if last_ret > 0 else Signal.SHORT if last_ret < 0 else Signal.HOLD
            return StrategySignal(fallback, 0.51, {"mode": "fallback"})

        proba_up = float(self.model.predict_proba(features.iloc[[-1]])[0][1])
        if proba_up >= self.state.threshold:
            return StrategySignal(Signal.LONG, proba_up, {"mode": "ml", "p_up": proba_up})

        if proba_up <= (1 - self.state.threshold):
            return StrategySignal(Signal.SHORT, 1 - proba_up, {"mode": "ml", "p_down": 1 - proba_up})

        return StrategySignal(Signal.HOLD, 1 - abs(proba_up - 0.5), {"mode": "ml", "p_up": proba_up})
