from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

import pandas as pd

from agent.core.engine import MarketContext
from agent.data.data_loader import DataLoader
from agent.execution.coinbase_ws_stream import CoinbaseMarketDataStream, CoinbaseUserStream
from agent.utils.logger import get_logger


@dataclass
class MarketDefinition:
    market: str
    context_symbol: str
    feed_product_id: str


class LiveMarketProvider:
    """Serve rolling OHLCV frames from websocket ticks with REST fallback."""

    def __init__(
        self,
        loader: DataLoader,
        market_stream: CoinbaseMarketDataStream,
        market_defs: Dict[str, MarketDefinition],
        user_stream: CoinbaseUserStream | None = None,
        lookback_bars: int = 300,
    ) -> None:
        self.loader = loader
        self.market_stream = market_stream
        self.market_defs = market_defs
        self.user_stream = user_stream
        self.lookback_bars = lookback_bars
        self.logger = get_logger(self.__class__.__name__)

    def start(self) -> None:
        self._warmup_from_rest()
        self.market_stream.start()
        if self.user_stream is not None:
            self.user_stream.start()

    def stop(self) -> None:
        self.market_stream.stop()
        if self.user_stream is not None:
            self.user_stream.stop()

    def drain_order_updates(self):
        if self.user_stream is None:
            return []
        return self.user_stream.drain_updates()

    def contexts(self) -> Dict[str, MarketContext]:
        output: Dict[str, MarketContext] = {}
        for key, definition in self.market_defs.items():
            df = self.market_stream.aggregator.get_ohlcv(definition.feed_product_id, lookback=self.lookback_bars)
            if len(df) < min(60, self.lookback_bars // 2):
                self.logger.warning(
                    "Insufficient websocket bars for %s (%s), using REST fallback for this cycle.",
                    key,
                    definition.feed_product_id,
                )
                df = self._fetch_rest(definition.feed_product_id)
                self.market_stream.aggregator.seed_history(definition.feed_product_id, df)
                df = self.market_stream.aggregator.get_ohlcv(definition.feed_product_id, lookback=self.lookback_bars)

            if definition.market == "perps" and "funding_rate" not in df.columns:
                df["funding_rate"] = 0.0

            output[key] = MarketContext(
                symbol=definition.context_symbol,
                market=definition.market,
                data=df,
            )

        return output

    def _warmup_from_rest(self) -> None:
        for definition in self.market_defs.values():
            df = self._fetch_rest(definition.feed_product_id)
            self.market_stream.aggregator.seed_history(definition.feed_product_id, df)

    def _fetch_rest(self, product_id: str) -> pd.DataFrame:
        end = int(time.time())
        start = end - (60 * self.lookback_bars)
        df = self.loader.fetch_ohlcv(product_id, start, end)
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "start" in df.columns:
            df["start"] = pd.to_datetime(df["start"], utc=True, errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
