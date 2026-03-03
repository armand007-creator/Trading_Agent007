from __future__ import annotations

from agent.execution.coinbase_ws_stream import CoinbaseMarketDataStream, CoinbaseUserStream, OhlcvAggregator


def test_ohlcv_aggregator_builds_candles():
    agg = OhlcvAggregator(["BTC-USD"], max_bars=10)
    agg.ingest_tick("BTC-USD", 100.0, 1.5, "2026-03-03T12:00:01Z")
    agg.ingest_tick("BTC-USD", 101.0, 0.5, "2026-03-03T12:00:20Z")
    agg.ingest_tick("BTC-USD", 99.0, 2.0, "2026-03-03T12:00:55Z")

    df = agg.get_ohlcv("BTC-USD", lookback=5)
    assert len(df) == 1
    assert float(df.iloc[-1]["open"]) == 100.0
    assert float(df.iloc[-1]["high"]) == 101.0
    assert float(df.iloc[-1]["low"]) == 99.0
    assert float(df.iloc[-1]["close"]) == 99.0
    assert float(df.iloc[-1]["volume"]) == 4.0


def test_extract_ticks_advanced_trade_payload():
    payload = {
        "channel": "ticker",
        "timestamp": "2026-03-03T12:01:00Z",
        "events": [
            {
                "type": "snapshot",
                "tickers": [
                    {
                        "product_id": "BTC-USD",
                        "price": "123456.78",
                        "last_size": "0.015",
                    }
                ],
            }
        ],
    }

    ticks = CoinbaseMarketDataStream.extract_ticks(payload)
    assert len(ticks) == 1
    symbol, price, size, ts = ticks[0]
    assert symbol == "BTC-USD"
    assert price == 123456.78
    assert size == 0.015
    assert ts == "2026-03-03T12:01:00Z"


def test_extract_order_updates_user_channel():
    payload = {
        "channel": "user",
        "timestamp": "2026-03-03T12:02:00Z",
        "events": [
            {
                "type": "update",
                "orders": [
                    {
                        "order_id": "abc123",
                        "client_order_id": "cid-1",
                        "product_id": "BTC-USD",
                        "order_side": "BUY",
                        "status": "FILLED",
                        "limit_price": "120000",
                        "base_size": "0.01",
                    }
                ],
            }
        ],
    }

    updates = CoinbaseUserStream.extract_order_updates(payload)
    assert len(updates) == 1
    assert updates[0].order_id == "abc123"
    assert updates[0].status == "FILLED"
    assert updates[0].product_id == "BTC-USD"
