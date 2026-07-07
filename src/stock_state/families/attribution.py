from __future__ import annotations

import math

import numpy as np
import pandas as pd

from stock_state.card import AttributionFamily, field, na
from stock_state.config import Defaults
from stock_state.indicators import ols_regression


def compute_attribution(
    prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    config: Defaults,
) -> AttributionFamily:
    aligned = _aligned_returns(prices, market_prices, sector_prices)
    if aligned is None or len(aligned) < config.ATTR_WINDOW + 1:
        return _missing("insufficient history", "two-factor" if sector_prices is not None else "market-only")
    window = aligned.tail(config.ATTR_WINDOW + 1)
    estimate = window.iloc[:-1]
    target = window.iloc[-1]
    if "sector" in aligned.columns:
        result = _two_factor(estimate, target, config)
    else:
        result = _market_only(estimate, target, config)
    return result


def _two_factor(
    estimate: pd.DataFrame,
    target: pd.Series,
    config: Defaults,
) -> AttributionFamily:
    sector_model = ols_regression(
        estimate["sector"].to_numpy(), estimate["market"].to_numpy()
    )
    if sector_model is None:
        return _missing("insufficient history", "market-only")
    u_est = sector_model.residuals
    sector_alpha, sector_beta = sector_model.coefficients
    u_target = float(target["sector"] - (sector_alpha + sector_beta * target["market"]))
    stock_x = np.column_stack([estimate["market"].to_numpy(), u_est])
    stock_model = ols_regression(estimate["stock"].to_numpy(), stock_x)
    if stock_model is None:
        return _missing("insufficient history", "two-factor")
    beta_market = float(stock_model.coefficients[1])
    beta_sector = float(stock_model.coefficients[2])
    market_component = beta_market * float(target["market"])
    sector_component = beta_sector * u_target
    residual = float(target["stock"] - market_component - sector_component)
    residual_z = _residual_z(residual, stock_model.residuals)
    classification = _classification(
        float(target["market"]), float(target["stock"]), residual_z, config
    )
    return AttributionFamily(
        classification=classification,
        market_component=field(market_component),
        sector_component=field(sector_component),
        residual=field(residual),
        residual_z=field(residual_z, "zero residual volatility"),
        beta_market=field(beta_market),
        beta_sector=field(beta_sector),
        r_squared=field(stock_model.r_squared),
        mode="two-factor",
        residual_vol_annualized=field(_residual_vol(stock_model.residuals)),
    )


def _market_only(
    estimate: pd.DataFrame,
    target: pd.Series,
    config: Defaults,
) -> AttributionFamily:
    stock_model = ols_regression(
        estimate["stock"].to_numpy(), estimate["market"].to_numpy()
    )
    if stock_model is None:
        return _missing("insufficient history", "market-only")
    beta_market = float(stock_model.coefficients[1])
    market_component = beta_market * float(target["market"])
    residual = float(target["stock"] - market_component)
    residual_z = _residual_z(residual, stock_model.residuals)
    classification = _classification(
        float(target["market"]), float(target["stock"]), residual_z, config
    )
    return AttributionFamily(
        classification=classification,
        market_component=field(market_component),
        sector_component=na("market-only attribution"),
        residual=field(residual),
        residual_z=field(residual_z, "zero residual volatility"),
        beta_market=field(beta_market),
        beta_sector=na("market-only attribution"),
        r_squared=field(stock_model.r_squared),
        mode="market-only",
        residual_vol_annualized=field(_residual_vol(stock_model.residuals)),
    )


def _classification(
    market_return: float,
    stock_return: float,
    residual_z: float | None,
    config: Defaults,
) -> str:
    if residual_z is not None and market_return <= config.MKT_DOWN and residual_z <= config.Z_AMPLIFIER:
        return "放大器"
    if residual_z is not None and market_return <= config.MKT_DOWN and residual_z >= config.Z_DEFIANT:
        return "逆市强势"
    if market_return <= config.MKT_DOWN and stock_return < 0:
        return "系统性下跌"
    if residual_z is not None and market_return > config.MKT_DOWN and residual_z <= config.Z_IDIO:
        return "个股性下跌"
    return "正常"


def _aligned_returns(
    prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
) -> pd.DataFrame | None:
    stock = prices["close"].pct_change().rename("stock")
    market = market_prices["close"].pct_change().rename("market")
    frames = [stock, market]
    if sector_prices is not None and not sector_prices.empty:
        frames.append(sector_prices["close"].pct_change().rename("sector"))
    aligned = pd.concat(frames, axis=1, join="inner").dropna()
    if aligned.empty:
        return None
    return aligned


def _residual_z(residual: float, residuals: np.ndarray) -> float | None:
    sigma = float(np.std(residuals, ddof=1))
    if not math.isfinite(sigma) or sigma == 0.0:
        return 0.0 if abs(residual) < 1e-10 else None
    return residual / sigma


def _residual_vol(residuals: np.ndarray) -> float | None:
    sigma = float(np.std(residuals, ddof=1))
    if not math.isfinite(sigma):
        return None
    return sigma * math.sqrt(252.0) * 100.0


def _missing(reason: str, mode: str) -> AttributionFamily:
    return AttributionFamily(
        classification="N/A",
        market_component=na(reason),
        sector_component=na(reason if mode == "two-factor" else "market-only attribution"),
        residual=na(reason),
        residual_z=na(reason),
        beta_market=na(reason),
        beta_sector=na(reason if mode == "two-factor" else "market-only attribution"),
        r_squared=na(reason),
        mode=mode,
        residual_vol_annualized=na(reason),
    )

