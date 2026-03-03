from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import pandas as pd

from agent.core.config import load_config
from agent.core.engine import MarketContext, TradingEngine
from agent.data.data_loader import DataLoader
from agent.utils.logger import get_logger


def build_market_provider(
    engine: TradingEngine,
    spot_csv: str | None,
    futures_csv: str | None,
    perps_csv: str | None,
):
    loader = DataLoader(engine.spot_connector)

    if any([spot_csv, futures_csv, perps_csv]):
        spot_df = loader.load_csv(spot_csv) if spot_csv else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        fut_df = (
            loader.load_csv(futures_csv)
            if futures_csv
            else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        )
        perp_df = (
            loader.load_csv(perps_csv)
            if perps_csv
            else pd.DataFrame(columns=["open", "high", "low", "close", "volume", "funding_rate"])
        )

        def provider():
            return {
                "spot": MarketContext(symbol="BTC-USD", market="spot", data=spot_df),
                "futures": MarketContext(symbol="BTC-USD-FUT", market="futures", data=fut_df),
                "perps": MarketContext(symbol="BTC-PERP", market="perps", data=perp_df),
            }

        return provider

    def provider_live():
        end = int(time.time())
        start = end - (60 * 300)

        spot = loader.fetch_ohlcv("BTC-USD", start, end)
        futures = loader.fetch_ohlcv("BTC-USD", start, end)
        perps = loader.fetch_ohlcv("BTC-USD", start, end)

        for df in (spot, futures, perps):
            if not df.empty and "close" in df.columns:
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(inplace=True)

        if "funding_rate" not in perps.columns:
            perps["funding_rate"] = 0.0

        return {
            "spot": MarketContext(symbol="BTC-USD", market="spot", data=spot),
            "futures": MarketContext(symbol="BTC-USD-FUT", market="futures", data=futures),
            "perps": MarketContext(symbol="BTC-PERP", market="perps", data=perps),
        }

    return provider_live


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Agent007 multi-market engine")
    parser.add_argument("--env", type=str, default=None, help="Optional .env path")
    parser.add_argument("--spot-csv", type=str, default=None, help="CSV for spot data")
    parser.add_argument("--futures-csv", type=str, default=None, help="CSV for futures data")
    parser.add_argument("--perps-csv", type=str, default=None, help="CSV for perps data")
    args = parser.parse_args()

    logger = get_logger("main")
    config = load_config(args.env)
    engine = TradingEngine(config)

    provider = build_market_provider(engine, args.spot_csv, args.futures_csv, args.perps_csv)

    def _handle_signal(signum, frame):
        _ = frame
        logger.warning("Received signal %s, shutting down.", signum)
        engine.shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        engine.run_forever(provider)
    except Exception as exc:
        logger.exception("Fatal engine error: %s", exc)
        engine.shutdown()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
