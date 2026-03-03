from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from agent.core.config import AllocationConfig


class VolatilityRegime(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


@dataclass
class StrategyTelemetry:
    sharpe: float
    recent_return: float
    volatility: float


class CapitalAllocator:
    """Adaptive barbell allocator: growth in stable regimes, defense in stress."""

    def __init__(self, base_allocation: AllocationConfig) -> None:
        self.base = base_allocation.as_dict()

    def detect_regime(self, realized_vol: float, drawdown_pct: float, funding_stress: float) -> VolatilityRegime:
        if drawdown_pct <= -0.06 or realized_vol > 0.90 or abs(funding_stress) > 0.008:
            return VolatilityRegime.RISK_OFF
        if realized_vol < 0.45 and drawdown_pct > -0.02:
            return VolatilityRegime.RISK_ON
        return VolatilityRegime.NEUTRAL

    def allocate(
        self,
        regime: VolatilityRegime,
        strategy_stats: Dict[str, StrategyTelemetry],
    ) -> Dict[str, float]:
        weights = dict(self.base)

        if regime == VolatilityRegime.RISK_ON:
            weights["futures"] += 0.10
            weights["perps"] += 0.05
            weights["spot"] -= 0.15
        elif regime == VolatilityRegime.RISK_OFF:
            weights["spot"] += 0.25
            weights["futures"] -= 0.15
            weights["perps"] -= 0.10

        for market, telemetry in strategy_stats.items():
            if market not in weights:
                continue
            if telemetry.sharpe < 0:
                weights[market] *= 0.75
            elif telemetry.sharpe > 1.5 and telemetry.recent_return > 0:
                weights[market] *= 1.15

        return self._normalize(weights)

    @staticmethod
    def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
        clipped = {k: max(0.01, v) for k, v in weights.items()}
        total = sum(clipped.values())
        return {k: v / total for k, v in clipped.items()}
