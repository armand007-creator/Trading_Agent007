# Trading_Agent007

Multi-account, multi-market quantitative trading framework for Coinbase spot, futures, and perpetual-style workflows with adaptive risk personality.

## Machine Personality

`Adaptive Barbell`:
- `RISK_ON`: growth mode with higher derivatives allocation and leverage.
- `NEUTRAL`: balanced allocation.
- `RISK_OFF`: capital-preservation mode with reduced leverage and increased spot weight.

This enables aggressive growth behavior when conditions are favorable while preserving capital under stress.

## Architecture Diagram

```text
                     +-------------------------+
                     |      main.py            |
                     |  signal-safe runtime    |
                     +------------+------------+
                                  |
                                  v
                    +-------------+--------------+
                    |    TradingEngine           |
                    |  10-step execution loop    |
                    +------+------+------+-------+
                           |      |      |
              +------------+      |      +----------------+
              |                   |                       |
              v                   v                       v
      +-------+-------+   +-------+--------+      +-------+-------+
      |  Strategy      |   |   Risk Layer   |      |  Execution    |
      | Spot/Fut/Perp  |   | Global + Wallet|      | Coinbase APIs |
      | ML overlay     |   | + Leverage Ctrl|      | Order/Wallet  |
      +-------+--------+   +-------+--------+      +-------+-------+
              |                    |                       |
              +-----------+--------+-----------------------+
                          |
                          v
                 +--------+---------+
                 | Portfolio/State  |
                 | Allocator/Logs   |
                 +--------+---------+
                          |
                          v
                 +--------+---------+
                 | Backtesting      |
                 | Spot + Derivs    |
                 +------------------+
```

## Project Layout

```text
Trading_Agent007/
+-- agent/
¦   +-- core/
¦   +-- strategy/
¦   +-- risk/
¦   +-- execution/
¦   +-- backtest/
¦   +-- data/
¦   +-- utils/
+-- docker/
+-- tests/
+-- .env.example
+-- requirements.txt
+-- README.md
+-- main.py
```

## Spot vs Futures vs Perps

- Spot:
  - Long-only default behavior.
  - Market and limit compatible payload structure.
- Futures:
  - Long/short signals.
  - Configurable leverage with volatility-based reduction.
  - Isolated-style risk modeling; cross behavior can be layered in connector logic.
- Perps:
  - Funding-rate-aware strategy filter.
  - Long/short support.
  - Liquidation buffer monitoring and auto-reduction hooks.

## Wallet Interaction

`WalletManager` provides:
- `get_spot_balance()`
- `get_futures_balance()`
- `transfer_spot_to_futures(amount)`
- `transfer_futures_to_spot(amount)`
- `get_total_portfolio_value()`

Risk gating:
- Transfers are blocked unless `WalletRiskManager.validate_transfer()` passes.
- Margin usage, collateral, and unrealized PnL are tracked.

### Transfer examples

```python
resp = wallet_manager.transfer_spot_to_futures(amount=500, currency="USD", source_market_notional=2000)
resp = wallet_manager.transfer_futures_to_spot(amount=250, currency="USD", source_market_notional=1500)
```

## Risk Layer Diagram

```text
Signal -> WalletRiskManager -> GlobalRiskManager -> Execution
            |                     |
            |                     +-- daily drawdown kill-switch
            +-- leverage caps
            +-- liquidation buffer checks
            +-- margin health checks
```

Kill-switch behavior:
- Close all positions.
- Disable engine state.

## Backtesting Guide

### Spot backtest

```python
from agent.backtest.backtester import Backtester
from agent.strategy.spot_strategy import SpotStrategy

bt = Backtester(SpotStrategy(cfg), fee_bps=8, slippage_bps=5)
result = bt.run(df)
print(result.metrics)
```

### Derivatives backtest

```python
from agent.backtest.derivatives_backtester import DerivativesBacktester

dbt = DerivativesBacktester(strategy=perp_strategy, leverage=3.0)
result = dbt.run(df, funding_rate_col="funding_rate")
print(result.metrics, result.liquidation_events)
```

Included metrics:
- CAGR
- Sharpe
- Sortino
- Max drawdown
- Calmar ratio
- Profit factor
- Liquidation events count (derivatives)

Equity curve is returned for plotting.

## Live Deployment Guide

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure

```bash
cp .env.example .env
# fill Coinbase keys and risk/allocation settings
```

### 3) Run

```bash
python main.py
```

Optional CSV-driven run:

```bash
python main.py --spot-csv data/spot.csv --futures-csv data/futures.csv --perps-csv data/perps.csv
```

### 4) Docker

```bash
docker build -f docker/Dockerfile -t trading-agent007 .
docker run --env-file .env --name agent007 trading-agent007
```

Container characteristics:
- Non-root runtime user.
- Environment-driven config.
- Auto-starts `main.py`.
- Graceful shutdown via signal handling.
- Optional close-all on shutdown (`CLOSE_POSITIONS_ON_SHUTDOWN=true`).

## Security

- Secrets are environment-only.
- `.gitignore` excludes `.env`.
- Separate spot/derivatives API keys supported.

## Notes on Coinbase Endpoint Availability

Derivatives/perpetual endpoints vary by jurisdiction/account permissions. Connector methods are structured for Advanced Trade-style routes and designed to fail-safe with empty responses when permissions/endpoints are unavailable.

## Disclaimer

This software is for research and infrastructure purposes only and does not constitute financial advice. Live trading with leverage can result in significant losses, including liquidation. You are solely responsible for deployment, risk settings, regulatory compliance, and capital at risk.
