from __future__ import annotations

from typing import Any, Dict, List

from agent.execution.coinbase_futures_connector import CoinbaseFuturesConnector
from agent.execution.coinbase_spot_connector import CoinbaseSpotConnector
from agent.utils.logger import get_logger


class OrderManager:
    def __init__(
        self,
        spot_connector: CoinbaseSpotConnector,
        futures_connector: CoinbaseFuturesConnector,
    ) -> None:
        self.spot_connector = spot_connector
        self.futures_connector = futures_connector
        self.logger = get_logger(self.__class__.__name__)

    def execute_order(self, market: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        market = market.lower()
        if market == "spot":
            return self.spot_connector.place_order(payload)
        if market in {"futures", "perps"}:
            return self.futures_connector.place_order(payload)
        raise ValueError(f"Unsupported market: {market}")

    def close_all_positions(self) -> List[Dict[str, Any]]:
        closed = []
        positions = self.futures_connector.get_positions()
        for pos in positions:
            size = float(pos.get("number_of_contracts", "0"))
            if size == 0:
                continue

            side = "SELL" if pos.get("side", "LONG").upper() == "LONG" else "BUY"
            order = {
                "product_id": pos.get("product_id"),
                "side": side,
                "order_configuration": {
                    "market_market_ioc": {
                        "quote_size": None,
                        "base_size": str(abs(size)),
                    }
                },
            }
            closed.append(self.futures_connector.place_order(order))

        self.spot_connector.cancel_all_orders()
        self.logger.warning("Close-all flow executed for derivatives and spot orders.")
        return closed
