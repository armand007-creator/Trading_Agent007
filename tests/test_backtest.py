from __future__ import annotations

import pandas as pd

from agent.backtest.backtester import Backtester
from agent.core.config import StrategyConfig
from agent.strategy.spot_strategy import SpotStrategy


def test_spot_backtester_runs():
    prices = [100 + (i * 0.2) for i in range(300)]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1_000 + i for i in range(300)],
        }
    )
    cfg = StrategyConfig(
        ema_fast=10,
        ema_slow=20,
        rsi_period=14,
        rsi_overbought=70,
        rsi_oversold=30,
        atr_period=14,
        volume_lookback=10,
    )
    bt = Backtester(SpotStrategy(cfg))
    result = bt.run(df)
    assert len(result.equity_curve) > 0
