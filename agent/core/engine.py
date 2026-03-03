from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict

import pandas as pd

from agent.core.capital_allocator import CapitalAllocator, StrategyTelemetry
from agent.core.config import AppConfig
from agent.core.portfolio_manager import PortfolioManager, Position
from agent.core.state_manager import StateManager, TradeRecord
from agent.execution.coinbase_futures_connector import CoinbaseFuturesConnector
from agent.execution.coinbase_spot_connector import CoinbaseSpotConnector
from agent.execution.order_manager import OrderManager
from agent.execution.wallet_manager import WalletManager
from agent.risk.global_risk_manager import GlobalRiskManager
from agent.risk.position_sizing import risk_based_position_size
from agent.risk.wallet_risk_manager import WalletRiskManager
from agent.strategy.base_strategy import Signal, StrategySignal
from agent.strategy.futures_strategy import FuturesStrategy
from agent.strategy.ml_strategy import MLStrategy
from agent.strategy.perp_strategy import PerpStrategy
from agent.strategy.spot_strategy import SpotStrategy
from agent.utils.indicators import returns
from agent.utils.logger import get_logger


@dataclass
class MarketContext:
    symbol: str
    market: str
    data: pd.DataFrame


class TradingEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)

        self.state_manager = StateManager()
        self.portfolio_manager = PortfolioManager()

        self.global_risk = GlobalRiskManager(config.risk)
        self.wallet_risk = WalletRiskManager(config.risk)
        self.capital_allocator = CapitalAllocator(config.allocation)

        self.spot_connector = CoinbaseSpotConnector(config.spot_api)
        self.futures_connector = CoinbaseFuturesConnector(config.derivatives_api)
        self.order_manager = OrderManager(self.spot_connector, self.futures_connector)
        self.wallet_manager = WalletManager(self.spot_connector, self.futures_connector, self.wallet_risk)

        self.spot_strategy = SpotStrategy(config.strategy)
        self.futures_strategy = FuturesStrategy(config.strategy)
        self.perp_strategy = PerpStrategy(config.strategy)
        self.ml_strategy = MLStrategy(config.strategy)

        self.market_intervals = {
            "spot": config.engine.loop_interval_seconds,
            "futures": config.engine.loop_interval_seconds,
            "perps": config.engine.loop_interval_seconds,
        }

    def _latest_realized_vol(self, market_data: Dict[str, pd.DataFrame]) -> float:
        spot_df = market_data.get("spot")
        if spot_df is None or len(spot_df) < 50:
            return 0.5
        ret = returns(spot_df["close"]).tail(30)
        return float(ret.std() * (252**0.5)) if not ret.empty else 0.5

    def _telemetry_from_data(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, StrategyTelemetry]:
        telem = {}
        for market, df in market_data.items():
            if df is None or len(df) < 40:
                telem[market] = StrategyTelemetry(sharpe=0.0, recent_return=0.0, volatility=1.0)
                continue
            rets = returns(df["close"]).tail(30)
            vol = float(rets.std() * (252**0.5)) if not rets.empty else 1.0
            sharpe = float((rets.mean() / rets.std()) * (252**0.5)) if rets.std() and rets.std() > 0 else 0.0
            telem[market] = StrategyTelemetry(
                sharpe=sharpe,
                recent_return=float((df["close"].iloc[-1] / df["close"].iloc[-10]) - 1) if len(df) > 10 else 0.0,
                volatility=vol,
            )
        return telem

    def _funding_rates(self, symbols: list[str]) -> Dict[str, float]:
        return self.futures_connector.get_funding_rates(symbols)

    def _update_positions(self) -> None:
        raw_positions = self.futures_connector.get_positions()
        positions = []
        for p in raw_positions:
            qty = float(p.get("number_of_contracts", "0"))
            if qty == 0:
                continue
            positions.append(
                Position(
                    symbol=p.get("product_id", "UNKNOWN"),
                    market="futures",
                    side=p.get("side", "LONG"),
                    quantity=qty,
                    entry_price=float(p.get("entry_price", "0")),
                    mark_price=float(p.get("mark_price", "0")),
                    leverage=float(p.get("leverage", "1") or "1"),
                )
            )

        self.portfolio_manager.update_positions(positions)
        self.state_manager.update_positions(
            {
                f"futures:{pos.symbol}": {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "qty": pos.quantity,
                    "entry_price": pos.entry_price,
                    "mark_price": pos.mark_price,
                    "liquidation_price": self.wallet_risk.liquidation_price_estimate(
                        pos.entry_price,
                        pos.leverage,
                        pos.side,
                    ),
                }
                for pos in positions
            }
        )

    def _build_order_payload(
        self,
        symbol: str,
        signal: StrategySignal,
        qty: float,
        market: str,
        side_override: str | None = None,
    ) -> Dict:
        side_map = {
            Signal.LONG: "BUY",
            Signal.SHORT: "SELL",
            Signal.EXIT: "SELL",
            Signal.HOLD: "BUY",
        }
        side = side_override or side_map[signal.signal]

        payload = {
            "client_order_id": f"{market}-{symbol}-{int(time.time())}",
            "product_id": symbol,
            "side": side,
            "order_configuration": {
                "market_market_ioc": {
                    "base_size": str(max(0.0, qty)),
                }
            },
        }
        return payload

    def _exit_order_details(
        self,
        market: str,
        symbol: str,
        spot_balances: Dict[str, float],
        positions: Dict[str, Dict],
    ) -> tuple[float, str]:
        if market == "spot":
            base_asset = symbol.split("-")[0]
            qty = max(0.0, spot_balances.get(base_asset, 0.0))
            return qty, "SELL"

        for _, pos in positions.items():
            if pos.get("symbol") != symbol:
                continue
            qty = abs(float(pos.get("qty", 0.0)))
            side = "SELL" if str(pos.get("side", "LONG")).upper() == "LONG" else "BUY"
            return qty, side

        return 0.0, "SELL"

    def _strategy_signal(self, market: str, df: pd.DataFrame, funding_rate: float = 0.0) -> StrategySignal:
        if market == "spot":
            return self.spot_strategy.generate_signal(df)
        if market == "futures":
            return self.futures_strategy.generate_signal(df)
        if market == "perps":
            ml_sig = self.ml_strategy.generate_signal(df)
            perp_sig = self.perp_strategy.generate_signal(df, funding_rate=funding_rate)
            if perp_sig.signal == Signal.HOLD:
                return ml_sig
            return perp_sig
        raise ValueError(f"Unsupported market: {market}")

    def run_once(self, market_contexts: Dict[str, MarketContext]) -> None:
        # 1) Update balances
        spot_bal = self.wallet_manager.get_spot_balance()
        fut_bal = self.wallet_manager.get_futures_balance()
        self.state_manager.update_balances(
            {
                "spot_total": sum(spot_bal.values()),
                "futures_total": sum(fut_bal.values()),
                "portfolio": self.wallet_manager.get_total_portfolio_value(),
            }
        )

        # 2) Update funding data
        perp_symbols = [ctx.symbol for ctx in market_contexts.values() if ctx.market == "perps"]
        funding = self._funding_rates(perp_symbols) if perp_symbols else {}
        self.state_manager.update_funding_rates(funding)

        # 3) Update open positions
        self._update_positions()

        snapshot = self.state_manager.snapshot()
        portfolio_value = snapshot.balances.get("portfolio", 0.0)

        # Personality regime detection and dynamic allocation
        market_data = {k: v.data for k, v in market_contexts.items()}
        realized_vol = self._latest_realized_vol(market_data)
        funding_stress = max([abs(v) for v in funding.values()], default=0.0)
        regime = self.capital_allocator.detect_regime(
            realized_vol=realized_vol,
            drawdown_pct=snapshot.daily_pnl_pct,
            funding_stress=funding_stress,
        )
        alloc = self.capital_allocator.allocate(regime, self._telemetry_from_data(market_data))

        for name, ctx in market_contexts.items():
            # 4) Run strategy per market
            market = ctx.market
            sig = self._strategy_signal(market, ctx.data, funding_rate=funding.get(ctx.symbol, 0.0))
            if market == "spot" and sig.signal == Signal.SHORT:
                sig = StrategySignal(Signal.EXIT, sig.confidence, {**sig.metadata, "translated_from": "SHORT"})
            if sig.signal == Signal.HOLD:
                continue

            last_price = float(ctx.data["close"].iloc[-1])
            stop_price = float(sig.metadata.get("stop", last_price * 0.98))
            target_allocation = alloc.get(market, 0.0)
            wallet_budget = portfolio_value * target_allocation

            leverage_hint = float(sig.metadata.get("leverage_hint", self.config.risk.max_leverage))
            leverage = self.wallet_risk.propose_reduced_leverage(leverage_hint, realized_vol)

            side_override = None
            if sig.signal == Signal.EXIT:
                qty, side_override = self._exit_order_details(market, ctx.symbol, spot_bal, snapshot.positions)
            else:
                qty = risk_based_position_size(
                    account_value=wallet_budget,
                    risk_pct=min(0.02, self.config.risk.max_wallet_risk_pct / 10),
                    entry_price=last_price,
                    stop_price=stop_price,
                    leverage=leverage,
                )
            if qty <= 0:
                continue

            liquidation_price = self.wallet_risk.liquidation_price_estimate(last_price, leverage, sig.signal.value)
            liquidation_buffer_pct = self.wallet_risk.leverage_control.liquidation_distance_pct(
                mark_price=last_price,
                liquidation_price=liquidation_price,
                side=sig.signal.value,
            )

            if sig.signal == Signal.EXIT:
                payload = self._build_order_payload(ctx.symbol, sig, qty, market, side_override=side_override)
                response = self.order_manager.execute_order(market, payload)
                status = "accepted" if response else "rejected_or_empty"
                self.state_manager.add_trade(
                    TradeRecord(
                        timestamp=datetime.utcnow(),
                        market=market,
                        symbol=ctx.symbol,
                        side=sig.signal.value,
                        quantity=qty,
                        price=last_price,
                        status=status,
                    )
                )
                continue

            # 5) Validate via wallet risk
            wallet_decision = self.wallet_risk.validate_wallet(
                wallet_value=max(wallet_budget, 1.0),
                wallet_notional=qty * last_price,
                leverage=leverage,
                margin_health=1.30,
                liquidation_buffer_pct=liquidation_buffer_pct,
            )
            if not wallet_decision.allowed:
                if wallet_decision.reduce_position:
                    self.logger.warning("Wallet risk requesting reduction for %s", ctx.symbol)
                continue

            # 6) Validate via global risk
            global_decision = self.global_risk.validate(
                self.portfolio_manager,
                portfolio_value=max(1.0, portfolio_value),
                daily_pnl_pct=snapshot.daily_pnl_pct,
            )
            if not global_decision.allowed:
                self.logger.error("Global risk breach: %s", global_decision.reason)
                self.global_risk.kill_switch(self.order_manager, self.state_manager)
                return

            # 7) Execute order
            payload = self._build_order_payload(ctx.symbol, sig, qty, market, side_override=side_override)
            response = self.order_manager.execute_order(market, payload)

            # 8) Log trade
            status = "accepted" if response else "rejected_or_empty"
            self.state_manager.add_trade(
                TradeRecord(
                    timestamp=datetime.utcnow(),
                    market=market,
                    symbol=ctx.symbol,
                    side=sig.signal.value,
                    quantity=qty,
                    price=last_price,
                    status=status,
                )
            )

        # 9) Recalculate exposure
        exposure = self.portfolio_manager.exposure_pct(portfolio_value=max(1.0, portfolio_value))
        self.state_manager.set_exposure_pct(exposure)

    def run_forever(self, market_contexts_provider) -> None:
        while self.state_manager.is_enabled():
            contexts = market_contexts_provider()
            self.run_once(contexts)
            # 10) Sleep until next interval
            time.sleep(self.config.engine.loop_interval_seconds)

    def shutdown(self) -> None:
        if self.config.engine.close_positions_on_shutdown:
            self.order_manager.close_all_positions()
        self.state_manager.disable_engine()
