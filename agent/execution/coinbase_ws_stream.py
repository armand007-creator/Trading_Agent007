from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Tuple

import pandas as pd
import websocket

from agent.utils.logger import get_logger


def _to_datetime_utc(raw_ts: Any) -> datetime:
    if raw_ts is None:
        return datetime.now(timezone.utc)

    if isinstance(raw_ts, (int, float)):
        return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)

    ts = str(raw_ts).strip()
    if not ts:
        return datetime.now(timezone.utc)

    ts = ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class OrderUpdate:
    order_id: str
    client_order_id: str
    product_id: str
    side: str
    status: str
    price: float
    size: float
    event_time: str
    raw: Dict[str, Any]


class OhlcvAggregator:
    def __init__(
        self,
        symbols: Iterable[str],
        max_bars: int = 2000,
        timeframe_seconds: int = 60,
    ) -> None:
        self.timeframe_seconds = timeframe_seconds
        self._bars: Dict[str, Deque[Dict[str, Any]]] = {
            symbol: deque(maxlen=max_bars) for symbol in set(symbols)
        }
        self._lock = threading.Lock()

    def seed_history(self, symbol: str, df: pd.DataFrame) -> None:
        if df.empty:
            return

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return

        with self._lock:
            if symbol not in self._bars:
                self._bars[symbol] = deque(maxlen=2000)

            target = self._bars[symbol]
            for _, row in df.tail(target.maxlen or len(df)).iterrows():
                ts = row.get("start")
                start_ts = _to_datetime_utc(ts)
                start_ts = start_ts.replace(second=0, microsecond=0)
                target.append(
                    {
                        "start": start_ts,
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": _safe_float(row.get("close")),
                        "volume": _safe_float(row.get("volume")),
                    }
                )

    def ingest_tick(self, symbol: str, price: float, size: float, event_ts: Any) -> None:
        price = _safe_float(price)
        size = max(0.0, _safe_float(size))
        if price <= 0:
            return

        tick_dt = _to_datetime_utc(event_ts)
        bucket = tick_dt.replace(second=0, microsecond=0)

        with self._lock:
            if symbol not in self._bars:
                self._bars[symbol] = deque(maxlen=2000)

            bars = self._bars[symbol]
            if not bars or bars[-1]["start"] != bucket:
                bars.append(
                    {
                        "start": bucket,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": size,
                    }
                )
                return

            bar = bars[-1]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += size

    def get_ohlcv(self, symbol: str, lookback: int = 300) -> pd.DataFrame:
        with self._lock:
            bars = list(self._bars.get(symbol, []))

        if not bars:
            return pd.DataFrame(columns=["start", "open", "high", "low", "close", "volume"])

        frame = pd.DataFrame(bars[-lookback:])
        frame = frame.sort_values("start").reset_index(drop=True)
        return frame


class CoinbaseMarketDataStream:
    def __init__(
        self,
        product_ids: List[str],
        ws_url: str = "wss://advanced-trade-ws.coinbase.com",
        reconnect_seconds: int = 5,
        max_bars: int = 2000,
    ) -> None:
        self.product_ids = sorted(set(product_ids))
        self.ws_url = ws_url
        self.reconnect_seconds = reconnect_seconds
        self.logger = get_logger(self.__class__.__name__)
        self.aggregator = OhlcvAggregator(self.product_ids, max_bars=max_bars)

        self._thread: threading.Thread | None = None
        self._ws_app: websocket.WebSocketApp | None = None
        self._stop_event = threading.Event()
        self._connected = threading.Event()

    @staticmethod
    def extract_ticks(payload: Dict[str, Any]) -> List[Tuple[str, float, float, Any]]:
        ticks: List[Tuple[str, float, float, Any]] = []

        # Coinbase Advanced Trade format
        channel = payload.get("channel")
        if channel == "ticker":
            event_time = payload.get("timestamp")
            for event in payload.get("events", []):
                for tick in event.get("tickers", []):
                    symbol = tick.get("product_id")
                    price = _safe_float(tick.get("price"))
                    size = _safe_float(tick.get("last_size"), default=0.0)
                    ts = tick.get("time") or event_time
                    if symbol and price > 0:
                        ticks.append((symbol, price, size, ts))

        # Legacy feed style ticker message
        if payload.get("type") == "ticker":
            symbol = payload.get("product_id")
            price = _safe_float(payload.get("price"))
            size = _safe_float(payload.get("last_size"), default=0.0)
            ts = payload.get("time")
            if symbol and price > 0:
                ticks.append((symbol, price, size, ts))

        return ticks

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="coinbase-market-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected.clear()

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def _on_open(self, ws) -> None:
        _ = ws
        self._connected.set()
        self.logger.info("Connected to market data websocket.")

        subscribe = {
            "type": "subscribe",
            "channel": "ticker",
            "product_ids": self.product_ids,
        }
        if self._ws_app is not None:
            self._ws_app.send(json.dumps(subscribe))

        # Optional heartbeat subscription for monitoring.
        heartbeat = {
            "type": "subscribe",
            "channel": "heartbeats",
            "product_ids": self.product_ids,
        }
        if self._ws_app is not None:
            self._ws_app.send(json.dumps(heartbeat))

    def _on_message(self, ws, message: str) -> None:
        _ = ws
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return

        ticks = self.extract_ticks(payload)
        for symbol, price, size, ts in ticks:
            self.aggregator.ingest_tick(symbol, price, size, ts)

    def _on_error(self, ws, error: Any) -> None:
        _ = ws
        self._connected.clear()
        self.logger.warning("Market websocket error: %s", error)

    def _on_close(self, ws, close_status_code: int, close_msg: str) -> None:
        _ = ws
        self._connected.clear()
        self.logger.warning(
            "Market websocket closed: code=%s msg=%s",
            close_status_code,
            close_msg,
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._ws_app = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            if self._stop_event.is_set():
                break
            self.logger.warning("Reconnecting market websocket in %ss", self.reconnect_seconds)
            time.sleep(self.reconnect_seconds)


class CoinbaseUserStream:
    def __init__(
        self,
        jwt_token: str,
        product_ids: List[str],
        ws_url: str = "wss://advanced-trade-ws-user.coinbase.com",
        reconnect_seconds: int = 5,
        max_updates: int = 500,
    ) -> None:
        self.jwt_token = jwt_token
        self.product_ids = sorted(set(product_ids))
        self.ws_url = ws_url
        self.reconnect_seconds = reconnect_seconds
        self.logger = get_logger(self.__class__.__name__)

        self._thread: threading.Thread | None = None
        self._ws_app: websocket.WebSocketApp | None = None
        self._stop_event = threading.Event()
        self._connected = threading.Event()

        self._updates: Deque[OrderUpdate] = deque(maxlen=max_updates)
        self._lock = threading.Lock()

    @staticmethod
    def extract_order_updates(payload: Dict[str, Any]) -> List[OrderUpdate]:
        updates: List[OrderUpdate] = []

        if payload.get("channel") == "user":
            event_time = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            for event in payload.get("events", []):
                for order in event.get("orders", []):
                    updates.append(
                        OrderUpdate(
                            order_id=str(order.get("order_id", "")),
                            client_order_id=str(order.get("client_order_id", "")),
                            product_id=str(order.get("product_id", "")),
                            side=str(order.get("order_side", order.get("side", ""))),
                            status=str(order.get("status", event.get("type", "UNKNOWN"))),
                            price=_safe_float(order.get("limit_price", order.get("price"),), default=0.0),
                            size=_safe_float(order.get("base_size", order.get("size"),), default=0.0),
                            event_time=str(order.get("event_time", event_time)),
                            raw=order,
                        )
                    )

        # Legacy feed order lifecycle shape fallback
        msg_type = payload.get("type", "")
        if msg_type in {"received", "open", "done", "match", "change"}:
            updates.append(
                OrderUpdate(
                    order_id=str(payload.get("order_id", "")),
                    client_order_id=str(payload.get("client_oid", "")),
                    product_id=str(payload.get("product_id", "")),
                    side=str(payload.get("side", "")),
                    status=msg_type.upper(),
                    price=_safe_float(payload.get("price"), default=0.0),
                    size=_safe_float(payload.get("size", payload.get("remaining_size")), default=0.0),
                    event_time=str(payload.get("time", datetime.now(timezone.utc).isoformat())),
                    raw=payload,
                )
            )

        return updates

    def start(self) -> None:
        if not self.jwt_token:
            self.logger.warning("User websocket jwt is empty; user stream is disabled.")
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="coinbase-user-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected.clear()

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def drain_updates(self) -> List[OrderUpdate]:
        with self._lock:
            data = list(self._updates)
            self._updates.clear()
        return data

    def _on_open(self, ws) -> None:
        _ = ws
        self._connected.set()
        self.logger.info("Connected to user websocket.")

        subscribe = {
            "type": "subscribe",
            "channel": "user",
            "product_ids": self.product_ids,
            "jwt": self.jwt_token,
        }
        if self._ws_app is not None:
            self._ws_app.send(json.dumps(subscribe))

    def _on_message(self, ws, message: str) -> None:
        _ = ws
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return

        updates = self.extract_order_updates(payload)
        if not updates:
            return

        with self._lock:
            self._updates.extend(updates)

    def _on_error(self, ws, error: Any) -> None:
        _ = ws
        self._connected.clear()
        self.logger.warning("User websocket error: %s", error)

    def _on_close(self, ws, close_status_code: int, close_msg: str) -> None:
        _ = ws
        self._connected.clear()
        self.logger.warning(
            "User websocket closed: code=%s msg=%s",
            close_status_code,
            close_msg,
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._ws_app = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            if self._stop_event.is_set():
                break
            self.logger.warning("Reconnecting user websocket in %ss", self.reconnect_seconds)
            time.sleep(self.reconnect_seconds)
