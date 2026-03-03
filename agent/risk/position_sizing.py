from __future__ import annotations


def risk_based_position_size(
    account_value: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    leverage: float = 1.0,
) -> float:
    """Compute quantity from risk budget and stop distance."""
    if account_value <= 0 or entry_price <= 0 or leverage <= 0:
        return 0.0

    risk_capital = account_value * risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0

    raw_qty = risk_capital / stop_distance
    max_notional = account_value * leverage
    qty_by_notional = max_notional / entry_price
    return max(0.0, min(raw_qty, qty_by_notional))
