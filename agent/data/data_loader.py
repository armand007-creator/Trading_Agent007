from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from agent.execution.coinbase_spot_connector import CoinbaseSpotConnector


class DataLoader:
    def __init__(self, spot_connector: CoinbaseSpotConnector | None = None) -> None:
        self.spot_connector = spot_connector

    @staticmethod
    def load_csv(path: str | Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        required = {"open", "high", "low", "close", "volume"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
        return df

    def fetch_ohlcv(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "ONE_MINUTE",
    ) -> pd.DataFrame:
        if self.spot_connector is None:
            raise ValueError("spot_connector is required for API loading")

        raw = self.spot_connector.get_product_candles(product_id, start, end, granularity)
        candles = raw.get("candles", [])
        if not candles:
            return pd.DataFrame(columns=["start", "low", "high", "open", "close", "volume"])

        df = pd.DataFrame(candles)
        numeric_cols = ["low", "high", "open", "close", "volume"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if "start" in df.columns:
            df["start"] = pd.to_datetime(df["start"], unit="s", errors="coerce")
            df = df.sort_values("start").reset_index(drop=True)

        return df
