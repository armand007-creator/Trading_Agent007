from __future__ import annotations

from agent.core.config import RiskConfig
from agent.risk.position_sizing import risk_based_position_size
from agent.risk.wallet_risk_manager import WalletRiskManager


def test_position_sizing_positive():
    qty = risk_based_position_size(
        account_value=10_000,
        risk_pct=0.01,
        entry_price=100,
        stop_price=95,
        leverage=2,
    )
    assert qty > 0


def test_wallet_transfer_rejection_on_balance():
    cfg = RiskConfig(
        max_total_exposure_pct=0.9,
        max_daily_drawdown_pct=0.1,
        max_correlated_exposure_pct=0.5,
        max_open_positions=10,
        max_wallet_risk_pct=0.3,
        max_leverage=5.0,
        min_liquidation_buffer_pct=0.15,
    )
    mgr = WalletRiskManager(cfg)
    decision = mgr.validate_transfer(source_balance=100, transfer_amount=200, source_market_notional=10)
    assert not decision.allowed
