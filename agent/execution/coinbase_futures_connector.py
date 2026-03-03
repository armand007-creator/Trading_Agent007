from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List

import requests

from agent.core.config import ApiCredentials
from agent.utils.logger import get_logger


class CoinbaseFuturesConnector:
    """Connector for futures/perpetual endpoints where enabled on Coinbase accounts."""

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

    def get_derivatives_balances(self) -> Dict[str, float]:
        data = self._request("GET", "/api/v3/brokerage/accounts")
        balances: Dict[str, float] = {}
        for account in data.get("accounts", []):
            if "future" not in str(account.get("name", "")).lower() and "deriv" not in str(
                account.get("name", "")
            ).lower():
                continue
            currency = account.get("currency") or account.get("available_balance", {}).get("currency")
            value = account.get("available_balance", {}).get("value")
            if currency and value is not None:
                balances[currency] = float(value)
        return balances

    def get_positions(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/v3/brokerage/cfm/positions")
        return data.get("positions", []) if isinstance(data, dict) else []

    def get_funding_rates(self, product_ids: List[str]) -> Dict[str, float]:
        rates: Dict[str, float] = {}
        for pid in product_ids:
            path = f"/api/v3/brokerage/products/{pid}"
            data = self._request("GET", path)
            funding = data.get("future_product_details", {}).get("perpetual_details", {}).get(
                "funding_rate"
            )
            if funding is not None:
                rates[pid] = float(funding)
        return rates

    def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/v3/brokerage/orders", payload)

    def set_leverage(self, product_id: str, leverage: float) -> Dict[str, Any]:
        payload = {"product_id": product_id, "leverage": str(leverage)}
        return self._request("POST", "/api/v3/brokerage/cfm/leverage", payload)

    def transfer(self, amount: float, currency: str, transfer_type: str) -> Dict[str, Any]:
        payload = {
            "amount": str(amount),
            "currency": currency,
            "transfer_type": transfer_type,
        }
        return self._request("POST", "/api/v3/brokerage/intx/transfers", payload)
