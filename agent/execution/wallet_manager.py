from __future__ import annotations

from typing import Dict

from agent.execution.coinbase_futures_connector import CoinbaseFuturesConnector
from agent.execution.coinbase_spot_connector import CoinbaseSpotConnector
from agent.risk.wallet_risk_manager import WalletRiskManager
from agent.utils.logger import get_logger


class WalletManager:
    def __init__(
        self,
        spot_connector: CoinbaseSpotConnector,
        futures_connector: CoinbaseFuturesConnector,
        wallet_risk_manager: WalletRiskManager,
    ) -> None:
        self.spot_connector = spot_connector
        self.futures_connector = futures_connector
        self.wallet_risk_manager = wallet_risk_manager
        self.logger = get_logger(self.__class__.__name__)

    def get_spot_balance(self) -> Dict[str, float]:
        return self.spot_connector.get_spot_balances()

    def get_futures_balance(self) -> Dict[str, float]:
        return self.futures_connector.get_derivatives_balances()

    def transfer_spot_to_futures(
        self,
        amount: float,
        currency: str = "USD",
        source_market_notional: float = 0.0,
    ) -> Dict:
        spot_bal = self.get_spot_balance().get(currency, 0.0)
        decision = self.wallet_risk_manager.validate_transfer(
            source_balance=spot_bal,
            transfer_amount=amount,
            source_market_notional=source_market_notional,
        )
        if not decision.allowed:
            self.logger.warning("Spot->Futures transfer denied: %s", decision.reason)
            return {"success": False, "reason": decision.reason}

        response = self.futures_connector.transfer(amount, currency, "SPOT_TO_DERIVATIVES")
        return {"success": bool(response), "response": response}

    def transfer_futures_to_spot(
        self,
        amount: float,
        currency: str = "USD",
        source_market_notional: float = 0.0,
    ) -> Dict:
        fut_bal = self.get_futures_balance().get(currency, 0.0)
        decision = self.wallet_risk_manager.validate_transfer(
            source_balance=fut_bal,
            transfer_amount=amount,
            source_market_notional=source_market_notional,
        )
        if not decision.allowed:
            self.logger.warning("Futures->Spot transfer denied: %s", decision.reason)
            return {"success": False, "reason": decision.reason}

        response = self.futures_connector.transfer(amount, currency, "DERIVATIVES_TO_SPOT")
        return {"success": bool(response), "response": response}

    def margin_usage(self) -> Dict[str, float]:
        positions = self.futures_connector.get_positions()
        total_notional = 0.0
        total_margin = 0.0

        for p in positions:
            notional = float(p.get("notional_value", "0"))
            margin = float(p.get("initial_margin", "0"))
            total_notional += abs(notional)
            total_margin += margin

        usage = total_margin / total_notional if total_notional > 0 else 0.0
        return {
            "total_notional": total_notional,
            "margin_used": total_margin,
            "margin_usage_pct": usage,
        }

    def available_collateral(self, currency: str = "USD") -> float:
        futures_bal = self.get_futures_balance()
        return futures_bal.get(currency, 0.0)

    def unrealized_pnl(self) -> float:
        positions = self.futures_connector.get_positions()
        return sum(float(p.get("unrealized_pnl", "0")) for p in positions)

    def get_total_portfolio_value(self, quote_currency: str = "USD") -> float:
        spot_total = sum(self.get_spot_balance().values())
        futures_total = sum(self.get_futures_balance().values())
        pnl = self.unrealized_pnl()
        _ = quote_currency
        return spot_total + futures_total + pnl
