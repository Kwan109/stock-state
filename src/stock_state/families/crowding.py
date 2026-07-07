from __future__ import annotations

from typing import Any

import pandas as pd

from stock_state.card import CrowdingFamily, NAField, field, na
from stock_state.config import Defaults
from stock_state.indicators import realized_vol, rolling_correlation, rolling_latest_percentile


def compute_crowding(
    prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    info: dict[str, Any],
    config: Defaults,
) -> CrowdingFamily:
    close = pd.to_numeric(prices["close"], errors="coerce")
    volume = pd.to_numeric(prices["volume"], errors="coerce")
    shares = _numeric(info.get("sharesOutstanding"))
    turnover = (
        volume / shares if shares is not None and shares > 0 else pd.Series(dtype="float64")
    )
    turnover_pct = (
        field(
            rolling_latest_percentile(turnover, config.PCTL_WINDOW, config.MIN_PCTL_COVERAGE),
            "insufficient history",
        )
        if shares is not None and shares > 0
        else na("missing sharesOutstanding")
    )
    rvol_series = realized_vol(close, config.RVOL_WINDOW)
    rvol_pct = field(
        rolling_latest_percentile(rvol_series, config.PCTL_WINDOW, config.MIN_PCTL_COVERAGE),
        "insufficient history",
    )
    extension_series = close / close.rolling(config.SMA_LONG, min_periods=config.SMA_LONG).mean() - 1.0
    extension_pct = field(
        rolling_latest_percentile(
            extension_series, config.PCTL_WINDOW, config.MIN_PCTL_COVERAGE
        ),
        "insufficient history",
    )
    corr_uplift = _corr_uplift(prices, sector_prices, config)
    short_percent = _short_percent(info.get("shortPercentOfFloat"))
    available = [
        turnover_pct.value,
        rvol_pct.value,
        extension_pct.value,
        corr_uplift.value * 100.0 if corr_uplift.value is not None else None,
    ]
    valid = [value for value in available if value is not None]
    score = field(sum(valid) / len(valid), "fewer than two available components") if len(valid) >= 2 else na("fewer than two available components")
    return CrowdingFamily(
        crowding_score=score,
        turnover_pct=turnover_pct,
        rvol_pct=rvol_pct,
        extension_pct=extension_pct,
        corr_uplift=corr_uplift,
        short_percent_of_float=field(short_percent, "missing shortPercentOfFloat"),
    )


def _corr_uplift(
    prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    config: Defaults,
) -> NAField:
    if sector_prices is None or sector_prices.empty:
        return na("missing sector ETF")
    stock_returns = prices["close"].pct_change()
    sector_returns = sector_prices["close"].pct_change()
    corr = rolling_correlation(stock_returns, sector_returns, config.CORR_WINDOW)
    window = corr.dropna().tail(config.PCTL_WINDOW)
    if len(window) < int(config.PCTL_WINDOW * config.MIN_PCTL_COVERAGE):
        return na("insufficient history")
    current = float(window.iloc[-1])
    low = float(window.min())
    high = float(window.max())
    if high == low:
        return field(0.5)
    return field((current - low) / (high - low))


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _short_percent(value: Any) -> float | None:
    number = _numeric(value)
    if number is None:
        return None
    return number * 100.0 if abs(number) <= 1.0 else number

