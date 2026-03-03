from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    profit_factor: float


def _annualized_return(equity_curve: pd.Series, periods_per_year: int = 252) -> float:
    if len(equity_curve) < 2:
        return 0.0
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    years = len(equity_curve) / periods_per_year
    if years <= 0:
        return 0.0
    return (1 + total_return) ** (1 / years) - 1


def _max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdowns = equity_curve / running_max - 1
    return float(drawdowns.min()) if not drawdowns.empty else 0.0


def _profit_factor(returns_series: pd.Series) -> float:
    gross_profit = returns_series[returns_series > 0].sum()
    gross_loss = -returns_series[returns_series < 0].sum()
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def calculate_performance_metrics(
    equity_curve: pd.Series,
    returns_series: pd.Series,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    if returns_series.empty:
        return PerformanceMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    cagr = _annualized_return(equity_curve, periods_per_year)
    excess = returns_series - 0.0
    std = excess.std(ddof=0)
    downside = excess[excess < 0].std(ddof=0)

    sharpe = float((excess.mean() / std) * np.sqrt(periods_per_year)) if std and std > 0 else 0.0
    sortino = (
        float((excess.mean() / downside) * np.sqrt(periods_per_year))
        if downside and downside > 0
        else 0.0
    )
    max_dd = _max_drawdown(equity_curve)
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    pf = _profit_factor(returns_series)

    return PerformanceMetrics(
        cagr=float(cagr),
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=float(max_dd),
        calmar=calmar,
        profit_factor=pf,
    )
