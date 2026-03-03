from __future__ import annotations

import argparse
import signal
import sys
import time

import pandas as pd

from agent.core.config import AppConfig, load_config
from agent.core.engine import MarketContext, TradingEngine
from agent.data.data_loader import DataLoader
from agent.data.live_market_provider import LiveMarketProvider, MarketDefinition
from agent.execution.coinbase_ws_stream import CoinbaseMarketDataStream, CoinbaseUserStream
from agent.utils.logger import get_logger


def build_market_provider(
    engine: TradingEngine,
    config: AppConfig,
    logger,
    spot_csv: str | None,
    futures_csv: str | None,
    perps_csv: str | None,
    use_websocket: bool,
    enable_user_stream: bool,
    spot_product_id: str,
    futures_product_id: str,
    perps_product_id: str,
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
                "spot": MarketContext(symbol=spot_product_id, market="spot", data=spot_df),
                "futures": MarketContext(symbol=futures_product_id, market="futures", data=fut_df),
                "perps": MarketContext(symbol=perps_product_id, market="perps", data=perp_df),
            }

        return provider, None

    if use_websocket:
        market_defs = {
            "spot": MarketDefinition(market="spot", context_symbol=spot_product_id, feed_product_id=spot_product_id),
            "futures": MarketDefinition(
                market="futures",
                context_symbol=futures_product_id,
                feed_product_id=futures_product_id,
            ),
            "perps": MarketDefinition(market="perps", context_symbol=perps_product_id, feed_product_id=perps_product_id),
        }

        market_stream = CoinbaseMarketDataStream(
            product_ids=[spot_product_id, futures_product_id, perps_product_id],
            ws_url=config.engine.websocket_market_url,
            reconnect_seconds=config.engine.websocket_reconnect_seconds,
            max_bars=max(1000, config.engine.websocket_lookback_bars * 5),
        )

        user_stream = None
        if enable_user_stream and config.engine.websocket_user_jwt:
            user_stream = CoinbaseUserStream(
                jwt_token=config.engine.websocket_user_jwt,
                product_ids=[spot_product_id, futures_product_id, perps_product_id],
                ws_url=config.engine.websocket_user_url,
                reconnect_seconds=config.engine.websocket_reconnect_seconds,
            )
        elif enable_user_stream:
            logger.warning("User stream requested but COINBASE_WS_USER_JWT is empty; skipping user stream.")

        live_provider = LiveMarketProvider(
            loader=loader,
            market_stream=market_stream,
            market_defs=market_defs,
            user_stream=user_stream,
            lookback_bars=config.engine.websocket_lookback_bars,
        )
        live_provider.start()

        def provider_ws():
            contexts = live_provider.contexts()
            updates = live_provider.drain_order_updates()
            if updates:
                latest = updates[-1]
                logger.info(
                    "User stream updates=%s latest(order_id=%s status=%s product=%s)",
                    len(updates),
                    latest.order_id,
                    latest.status,
                    latest.product_id,
                )
            return contexts

        return provider_ws, live_provider

    def provider_live_polling():
        end = int(time.time())
        start = end - (60 * 300)

        spot = loader.fetch_ohlcv(spot_product_id, start, end)
        futures = loader.fetch_ohlcv(futures_product_id, start, end)
        perps = loader.fetch_ohlcv(perps_product_id, start, end)

        for df in (spot, futures, perps):
            if not df.empty and "close" in df.columns:
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(inplace=True)

        if "funding_rate" not in perps.columns:
            perps["funding_rate"] = 0.0

        return {
            "spot": MarketContext(symbol=spot_product_id, market="spot", data=spot),
            "futures": MarketContext(symbol=futures_product_id, market="futures", data=futures),
            "perps": MarketContext(symbol=perps_product_id, market="perps", data=perps),
        }

    return provider_live_polling, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Agent007 multi-market engine")
    parser.add_argument("--env", type=str, default=None, help="Optional .env path")
    parser.add_argument("--spot-csv", type=str, default=None, help="CSV for spot data")
    parser.add_argument("--futures-csv", type=str, default=None, help="CSV for futures data")
    parser.add_argument("--perps-csv", type=str, default=None, help="CSV for perps data")
    parser.add_argument("--disable-websocket", action="store_true", help="Force polling mode")
    parser.add_argument("--enable-user-stream", action="store_true", help="Enable authenticated user websocket stream")
    parser.add_argument("--spot-product-id", type=str, default="BTC-USD", help="Spot product id")
    parser.add_argument("--futures-product-id", type=str, default="BTC-USD-FUT", help="Futures product id")
    parser.add_argument("--perps-product-id", type=str, default="BTC-PERP", help="Perps product id")
    args = parser.parse_args()

    logger = get_logger("main")
    config = load_config(args.env)
    engine = TradingEngine(config)

    use_websocket = config.engine.use_websocket_data and (not args.disable_websocket)
    enable_user_stream = config.engine.enable_user_stream or args.enable_user_stream

    provider, live_provider = build_market_provider(
        engine=engine,
        config=config,
        logger=logger,
        spot_csv=args.spot_csv,
        futures_csv=args.futures_csv,
        perps_csv=args.perps_csv,
        use_websocket=use_websocket,
        enable_user_stream=enable_user_stream,
        spot_product_id=args.spot_product_id,
        futures_product_id=args.futures_product_id,
        perps_product_id=args.perps_product_id,
    )

    def _handle_signal(signum, frame):
        _ = frame
        logger.warning("Received signal %s, shutting down.", signum)
        if live_provider is not None:
            live_provider.stop()
        engine.shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        engine.run_forever(provider)
    except Exception as exc:
        logger.exception("Fatal engine error: %s", exc)
        if live_provider is not None:
            live_provider.stop()
        engine.shutdown()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
