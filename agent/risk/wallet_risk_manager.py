from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from agent.core.config import RiskConfig
from agent.risk.leverage_control import LeverageControl


@dataclass
class WalletRiskDecision:
    allowed: bool
    reason: str = "ok"
    reduce_position: bool = False


class WalletRiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.leverage_control = LeverageControl(config.max_leverage)

    def validate_wallet(
        self,
        wallet_value: float,
        wallet_notional: float,
        leverage: float,
        margin_health: float,
        liquidation_buffer_pct: float,
    ) -> WalletRiskDecision:
        if wallet_value <= 0:
            return WalletRiskDecision(False, "wallet_value_non_positive")

        risk_pct = wallet_notional / wallet_value if wallet_value > 0 else 0.0
        if risk_pct > self.config.max_wallet_risk_pct:
            return WalletRiskDecision(False, "max_wallet_risk_breached")

        if leverage > self.config.max_leverage:
            return WalletRiskDecision(False, "max_leverage_breached")

        if margin_health < 1.15:
            return WalletRiskDecision(False, "margin_health_critical", reduce_position=True)

        if liquidation_buffer_pct < self.config.min_liquidation_buffer_pct:
            return WalletRiskDecision(False, "liquidation_buffer_below_threshold", reduce_position=True)

        return WalletRiskDecision(True)

    def validate_transfer(
        self,
        source_balance: float,
        transfer_amount: float,
        source_market_notional: float,
    ) -> WalletRiskDecision:
        if transfer_amount <= 0:
            return WalletRiskDecision(False, "transfer_amount_non_positive")
        if source_balance < transfer_amount:
            return WalletRiskDecision(False, "insufficient_balance")

        post_balance = source_balance - transfer_amount
        if post_balance <= 0:
            return WalletRiskDecision(False, "source_wallet_would_be_empty")

        projected_risk = source_market_notional / post_balance
        if projected_risk > self.config.max_wallet_risk_pct:
            return WalletRiskDecision(False, "transfer_would_break_wallet_risk")

        return WalletRiskDecision(True)

    def propose_reduced_leverage(self, base_leverage: float, realized_vol: float) -> float:
        return self.leverage_control.adjust_for_volatility(base_leverage, realized_vol)

    def monitor_liquidation_buffer(
        self,
        positions: Dict[str, Dict],
    ) -> Dict[str, bool]:
        actions = {}
        for pid, pos in positions.items():
            buffer_pct = self.leverage_control.liquidation_distance_pct(
                mark_price=pos.get("mark_price", 0.0),
                liquidation_price=pos.get("liquidation_price", 0.0),
                side=pos.get("side", "LONG"),
            )
            actions[pid] = buffer_pct < self.config.min_liquidation_buffer_pct
        return actions

    def liquidation_price_estimate(
        self,
        entry_price: float,
        leverage: float,
        side: str,
        maintenance_margin_rate: float = 0.005,
    ) -> float:
        """Simple estimate for monitoring; exchange-specific values should replace this in production."""
        if leverage <= 0:
            return 0.0
        if side.upper() == "LONG":
            return entry_price * (1 - (1 / leverage) + maintenance_margin_rate)
        return entry_price * (1 + (1 / leverage) - maintenance_margin_rate)
