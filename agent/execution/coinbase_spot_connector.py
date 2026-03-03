from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict

import requests

from agent.core.config import ApiCredentials
from agent.utils.logger import get_logger


class CoinbaseSpotConnector:
    """Coinbase Advanced Trade spot connector.

    Endpoints vary by account permissions; methods return empty fallbacks on API errors.
    """

    def __init__(self, creds: ApiCredentials, timeout: int = 15) -> None:
        self.creds = creds
        self.timeout = timeout
        self.logger = get_logger(self.__class__.__name__)

    def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time()))
        prehash = f"{timestamp}{method.upper()}{path}{body}"

        secret = self.creds.secret
        try:
            secret_bytes = base64.b64decode(secret)
        except Exception:
            secret_bytes = secret.encode("utf-8")

        signature = hmac.new(secret_bytes, prehash.encode("utf-8"), hashlib.sha256).digest()
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "CB-ACCESS-KEY": self.creds.key,
            "CB-ACCESS-SIGN": signature_b64,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": self.creds.passphrase,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        body = json.dumps(payload) if payload else ""
        url = f"{self.creds.base_url}{path}"
        headers = self._headers(method, path, body)

        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body if body else None,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except Exception as exc:
            self.logger.warning("API request failed %s %s: %s", method, path, exc)
            return {}

    def get_accounts(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v3/brokerage/accounts")

    def get_spot_balances(self) -> Dict[str, float]:
        data = self.get_accounts()
        balances: Dict[str, float] = {}
        for account in data.get("accounts", []):
            if account.get("type", "").lower() != "fiat" and account.get("platform", "").lower() == "consumer":
                pass
            currency = account.get("currency") or account.get("available_balance", {}).get("currency")
            value = account.get("available_balance", {}).get("value")
            if currency and value is not None:
                balances[currency] = float(value)
        return balances

    def get_product_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "ONE_MINUTE",
    ) -> Dict[str, Any]:
        path = "/api/v3/brokerage/products/{}/candles?start={}&end={}&granularity={}".format(
            product_id,
            start,
            end,
            granularity,
        )
        return self._request("GET", path)

    def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/v3/brokerage/orders", payload)

    def cancel_all_orders(self) -> Dict[str, Any]:
        return self._request("POST", "/api/v3/brokerage/orders/batch_cancel", {"order_ids": []})
