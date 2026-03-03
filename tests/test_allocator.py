from __future__ import annotations

from agent.core.capital_allocator import CapitalAllocator, StrategyTelemetry, VolatilityRegime
from agent.core.config import AllocationConfig


def test_allocator_normalizes_weights():
    allocator = CapitalAllocator(AllocationConfig(spot=0.4, futures=0.35, perps=0.25))
    out = allocator.allocate(
        VolatilityRegime.RISK_ON,
        {
            "spot": StrategyTelemetry(sharpe=0.5, recent_return=0.01, volatility=0.2),
            "futures": StrategyTelemetry(sharpe=1.8, recent_return=0.03, volatility=0.4),
            "perps": StrategyTelemetry(sharpe=1.2, recent_return=0.02, volatility=0.5),
        },
    )
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert out["futures"] > out["spot"]


def test_regime_detection_risk_off():
    allocator = CapitalAllocator(AllocationConfig(spot=0.4, futures=0.35, perps=0.25))
    regime = allocator.detect_regime(realized_vol=1.1, drawdown_pct=-0.01, funding_stress=0.0001)
    assert regime == VolatilityRegime.RISK_OFF
