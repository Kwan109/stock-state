from __future__ import annotations

import numpy as np
import pandas as pd

from stock_state.card import RelativeFamily, field, na
from stock_state.config import Defaults
from stock_state.indicators import ols_slope, rolling_latest_percentile


def compute_relative(
    prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    attribution_classification: str,
    config: Defaults,
) -> RelativeFamily:
    qqq_ratio = _aligned_ratio(prices, market_prices)
    sector_ratio = (
        _aligned_ratio(prices, sector_prices)
        if sector_prices is not None and not sector_prices.empty
        else pd.Series(dtype="float64")
    )
    flags = _flags(qqq_ratio)
    if attribution_classification == "逆市强势":
        flags.append("defiant_strength_today")
    return RelativeFamily(
        rs_vs_qqq_slope_20d=_slope(qqq_ratio, config.RS_SLOPE_WINDOW),
        rs_vs_qqq_pct_3m=field(
            rolling_latest_percentile(
                qqq_ratio, config.RS_PCTL_WINDOW, config.MIN_PCTL_COVERAGE
            ),
            "insufficient history",
        ),
        rs_vs_sector_slope_20d=_slope(sector_ratio, config.RS_SLOPE_WINDOW)
        if not sector_ratio.empty
        else na("missing sector ETF"),
        rs_vs_sector_pct_3m=field(
            rolling_latest_percentile(
                sector_ratio, config.RS_PCTL_WINDOW, config.MIN_PCTL_COVERAGE
            ),
            "insufficient history",
        )
        if not sector_ratio.empty
        else na("missing sector ETF"),
        flags=flags,
    )


def _aligned_ratio(left: pd.DataFrame, right: pd.DataFrame | None) -> pd.Series:
    if right is None or right.empty:
        return pd.Series(dtype="float64")
    aligned = pd.concat([left["close"], right["close"]], axis=1, join="inner").dropna()
    if aligned.empty:
        return pd.Series(dtype="float64")
    ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1]
    ratio.name = "ratio"
    return ratio


def _slope(ratio: pd.Series, window: int):
    if len(ratio.dropna()) < window:
        return na("insufficient history")
    subset = ratio.dropna().tail(window)
    if (subset <= 0).any():
        return na("invalid ratio")
    slope = ols_slope(np.log(subset))
    return field(None if slope is None else slope * 252.0, "insufficient history")


def _flags(ratio: pd.Series) -> list[str]:
    valid = ratio.dropna()
    if len(valid) < 252:
        return []
    window = valid.tail(252)
    latest = window.iloc[-1]
    flags: list[str] = []
    if latest >= window.max():
        flags.append("rs_252d_high")
    if latest <= window.min():
        flags.append("rs_252d_low")
    return flags

