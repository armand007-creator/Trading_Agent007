from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

import pandas as pd


class Signal(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"
    HOLD = "HOLD"


@dataclass
class StrategySignal:
    signal: Signal
    confidence: float
    metadata: Dict[str, Any]


class BaseStrategy:
    name = "base"

    def generate_signal(self, df: pd.DataFrame, **kwargs: Any) -> StrategySignal:
        raise NotImplementedError
