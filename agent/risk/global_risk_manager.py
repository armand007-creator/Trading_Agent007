from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from agent.core.config import RiskConfig
from agent.core.portfolio_manager import PortfolioManager


@dataclass
class GlobalRiskDecision:
    allowed: bool
    reason: str = "ok"


class GlobalRiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def validate(
        self,
        portfolio_manager: PortfolioManager,
        portfolio_value: float,
        daily_pnl_pct: float,
    ) -> GlobalRiskDecision:
        exposure = portfolio_manager.exposure_pct(portfolio_value)
        if exposure > self.config.max_total_exposure_pct:
            return GlobalRiskDecision(False, "max_total_exposure_breached")

        correlated = portfolio_manager.correlated_exposure_pct(portfolio_value)
        if correlated > self.config.max_correlated_exposure_pct:
            return GlobalRiskDecision(False, "max_correlated_exposure_breached")

        if portfolio_manager.open_positions_count() > self.config.max_open_positions:
            return GlobalRiskDecision(False, "max_open_positions_breached")

        if daily_pnl_pct <= -abs(self.config.max_daily_drawdown_pct):
            return GlobalRiskDecision(False, "daily_drawdown_kill_switch")

        return GlobalRiskDecision(True)

    def kill_switch(self, order_manager, state_manager) -> Tuple[bool, str]:
        order_manager.close_all_positions()
        state_manager.disable_engine()
        return True, "kill_switch_executed"
