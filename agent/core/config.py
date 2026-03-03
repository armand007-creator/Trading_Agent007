from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from dotenv import load_dotenv


@dataclass
class ApiCredentials:
    key: str
    secret: str
    passphrase: str
    base_url: str


@dataclass
class RiskConfig:
    max_total_exposure_pct: float
    max_daily_drawdown_pct: float
    max_correlated_exposure_pct: float
    max_open_positions: int
    max_wallet_risk_pct: float
    max_leverage: float
    min_liquidation_buffer_pct: float


@dataclass
class AllocationConfig:
    spot: float
    futures: float
    perps: float

    def as_dict(self) -> Dict[str, float]:
        return {"spot": self.spot, "futures": self.futures, "perps": self.perps}


@dataclass
class StrategyConfig:
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_overbought: int
    rsi_oversold: int
    atr_period: int
    volume_lookback: int


@dataclass
class EngineConfig:
    loop_interval_seconds: int
    close_positions_on_shutdown: bool


@dataclass
class AppConfig:
    spot_api: ApiCredentials
    derivatives_api: ApiCredentials
    risk: RiskConfig
    allocation: AllocationConfig
    strategy: StrategyConfig
    engine: EngineConfig


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env_path: str | None = None) -> AppConfig:
    load_dotenv(dotenv_path=env_path)

    spot_api = ApiCredentials(
        key=os.getenv("COINBASE_API_KEY", ""),
        secret=os.getenv("COINBASE_API_SECRET", ""),
        passphrase=os.getenv("COINBASE_API_PASSPHRASE", ""),
        base_url=os.getenv("COINBASE_API_BASE_URL", "https://api.coinbase.com"),
    )
    derivatives_api = ApiCredentials(
        key=os.getenv("COINBASE_DERIV_API_KEY", spot_api.key),
        secret=os.getenv("COINBASE_DERIV_API_SECRET", spot_api.secret),
        passphrase=os.getenv("COINBASE_DERIV_API_PASSPHRASE", spot_api.passphrase),
        base_url=os.getenv("COINBASE_DERIV_API_BASE_URL", spot_api.base_url),
    )

    risk = RiskConfig(
        max_total_exposure_pct=float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.85")),
        max_daily_drawdown_pct=float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.08")),
        max_correlated_exposure_pct=float(os.getenv("MAX_CORRELATED_EXPOSURE_PCT", "0.45")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "8")),
        max_wallet_risk_pct=float(os.getenv("MAX_WALLET_RISK_PCT", "0.30")),
        max_leverage=float(os.getenv("MAX_LEVERAGE", "5.0")),
        min_liquidation_buffer_pct=float(os.getenv("MIN_LIQUIDATION_BUFFER_PCT", "0.15")),
    )

    allocation = AllocationConfig(
        spot=float(os.getenv("ALLOC_SPOT", "0.40")),
        futures=float(os.getenv("ALLOC_FUTURES", "0.35")),
        perps=float(os.getenv("ALLOC_PERPS", "0.25")),
    )

    total_alloc = allocation.spot + allocation.futures + allocation.perps
    if abs(total_alloc - 1.0) > 1e-6:
        allocation.spot /= total_alloc
        allocation.futures /= total_alloc
        allocation.perps /= total_alloc

    strategy = StrategyConfig(
        ema_fast=int(os.getenv("EMA_FAST", "20")),
        ema_slow=int(os.getenv("EMA_SLOW", "50")),
        rsi_period=int(os.getenv("RSI_PERIOD", "14")),
        rsi_overbought=int(os.getenv("RSI_OVERBOUGHT", "70")),
        rsi_oversold=int(os.getenv("RSI_OVERSOLD", "30")),
        atr_period=int(os.getenv("ATR_PERIOD", "14")),
        volume_lookback=int(os.getenv("VOLUME_LOOKBACK", "20")),
    )

    engine = EngineConfig(
        loop_interval_seconds=int(os.getenv("TRADING_LOOP_INTERVAL_SECONDS", "30")),
        close_positions_on_shutdown=_get_bool("CLOSE_POSITIONS_ON_SHUTDOWN", True),
    )

    return AppConfig(
        spot_api=spot_api,
        derivatives_api=derivatives_api,
        risk=risk,
        allocation=allocation,
        strategy=strategy,
        engine=engine,
    )
