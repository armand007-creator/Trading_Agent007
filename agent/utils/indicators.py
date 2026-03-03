from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def returns(series: pd.Series) -> pd.Series:
    return series.pct_change().fillna(0.0)


def volatility(returns_series: pd.Series, window: int = 30) -> pd.Series:
    return returns_series.rolling(window).std() * np.sqrt(252)


def ema_slope(series: pd.Series, span: int = 20, lookback: int = 5) -> pd.Series:
    em = ema(series, span=span)
    return em.diff(lookback) / lookback
