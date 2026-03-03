from __future__ import annotations

import pandas as pd

from agent.utils.indicators import atr, ema, rsi


def test_ema_runs():
    s = pd.Series([1, 2, 3, 4, 5])
    out = ema(s, 3)
    assert len(out) == 5
    assert out.iloc[-1] > out.iloc[0]


def test_rsi_range():
    s = pd.Series([1, 2, 3, 2, 2.5, 3, 3.5, 3.2, 3.8, 4.0, 4.2, 4.1, 4.4, 4.6, 4.8, 5.0])
    out = rsi(s, 14)
    val = float(out.iloc[-1])
    assert 0 <= val <= 100


def test_atr_positive():
    df = pd.DataFrame(
        {
            "high": [11, 12, 13, 12, 14, 15],
            "low": [9, 10, 11, 10, 12, 13],
            "close": [10, 11, 12, 11, 13, 14],
        }
    )
    out = atr(df, 3)
    assert out.iloc[-1] > 0
