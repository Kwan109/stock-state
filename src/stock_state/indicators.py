from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


def finite(value: float | int | None) -> bool:
    return value is not None and math.isfinite(float(value))


def percentile_rank(values: pd.Series | list[float], value: float | None = None) -> float | None:
    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return None
    target = float(series.iloc[-1] if value is None else value)
    if not math.isfinite(target):
        return None
    less = float((series < target).sum())
    equal = float((series == target).sum())
    return 100.0 * (less + 0.5 * equal) / float(len(series))


def rolling_latest_percentile(
    series: pd.Series,
    window: int,
    min_coverage: float,
) -> float | None:
    subset = pd.to_numeric(series, errors="coerce").tail(window).dropna()
    if len(subset) < math.ceil(window * min_coverage):
        return None
    return percentile_rank(subset)


def true_range(prices: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(prices["high"], errors="coerce")
    low = pd.to_numeric(prices["low"], errors="coerce")
    close = pd.to_numeric(prices["close"], errors="coerce")
    prev_close = close.shift(1)
    parts = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return parts.max(axis=1)


def atr(prices: pd.DataFrame, window: int) -> pd.Series:
    return true_range(prices).rolling(window=window, min_periods=window).mean()


def obv(prices: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(prices["close"], errors="coerce")
    volume = pd.to_numeric(prices["volume"], errors="coerce").fillna(0.0)
    direction = np.sign(close.diff()).fillna(0.0)
    increments = direction * volume
    return increments.cumsum()


def ols_slope(values: pd.Series | np.ndarray | list[float]) -> float | None:
    y = pd.Series(values, dtype="float64").dropna().to_numpy()
    if len(y) < 2:
        return None
    x = np.arange(len(y), dtype="float64")
    if np.allclose(y, y[0]):
        return 0.0
    return float(np.polyfit(x, y, 1)[0])


def obv_norm_slope(prices: pd.DataFrame, window: int) -> float | None:
    if len(prices) < window:
        return None
    obv_values = obv(prices).tail(window)
    slope = ols_slope(obv_values)
    avg_volume = pd.to_numeric(prices["volume"], errors="coerce").tail(window).mean()
    if slope is None or not finite(avg_volume) or avg_volume == 0:
        return None
    return slope / float(avg_volume)


def updown_vol_ratio(prices: pd.DataFrame, window: int, cap: float) -> float | None:
    if len(prices) < window + 1:
        return None
    subset = prices.tail(window + 1).copy()
    returns = subset["close"].pct_change().iloc[1:]
    volumes = pd.to_numeric(subset["volume"], errors="coerce").iloc[1:]
    up_vol = float(volumes[returns > 0].sum())
    down_vol = float(volumes[returns < 0].sum())
    if down_vol == 0:
        return cap
    return min(up_vol / down_vol, cap)


def money_flow_index(prices: pd.DataFrame, window: int) -> pd.Series:
    high = pd.to_numeric(prices["high"], errors="coerce")
    low = pd.to_numeric(prices["low"], errors="coerce")
    close = pd.to_numeric(prices["close"], errors="coerce")
    volume = pd.to_numeric(prices["volume"], errors="coerce")
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    diff = typical.diff()
    positive = raw_flow.where(diff > 0, 0.0)
    negative = raw_flow.where(diff < 0, 0.0).abs()
    pos_sum = positive.rolling(window=window, min_periods=window).sum()
    neg_sum = negative.rolling(window=window, min_periods=window).sum()
    ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    mfi = 100.0 - 100.0 / (1.0 + ratio)
    mfi = mfi.where(neg_sum != 0.0, 100.0)
    mfi = mfi.where(pos_sum != 0.0, 0.0)
    return mfi


def realized_vol(close: pd.Series, window: int) -> pd.Series:
    log_returns = np.log(pd.to_numeric(close, errors="coerce") / pd.to_numeric(close, errors="coerce").shift(1))
    return log_returns.rolling(window=window, min_periods=window).std(ddof=1) * math.sqrt(252.0)


def rolling_correlation(
    left: pd.Series,
    right: pd.Series,
    window: int,
) -> pd.Series:
    aligned = pd.concat([left, right], axis=1).dropna()
    if aligned.empty:
        return pd.Series(dtype="float64")
    return aligned.iloc[:, 0].rolling(window=window, min_periods=window).corr(aligned.iloc[:, 1])


@dataclass(frozen=True)
class RegressionResult:
    coefficients: np.ndarray
    residuals: np.ndarray
    r_squared: float


def ols_regression(y: np.ndarray, x: np.ndarray) -> RegressionResult | None:
    y_arr = np.asarray(y, dtype="float64")
    x_arr = np.asarray(x, dtype="float64")
    if y_arr.ndim != 1 or len(y_arr) < 3:
        return None
    if x_arr.ndim == 1:
        x_arr = x_arr.reshape(-1, 1)
    if len(x_arr) != len(y_arr):
        return None
    mask = np.isfinite(y_arr) & np.isfinite(x_arr).all(axis=1)
    y_arr = y_arr[mask]
    x_arr = x_arr[mask]
    if len(y_arr) < x_arr.shape[1] + 2:
        return None
    design = np.column_stack([np.ones(len(y_arr)), x_arr])
    coeffs, *_ = np.linalg.lstsq(design, y_arr, rcond=None)
    fitted = design @ coeffs
    residuals = y_arr - fitted
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y_arr - y_arr.mean()) ** 2))
    r_squared = 0.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return RegressionResult(coefficients=coeffs, residuals=residuals, r_squared=r_squared)


def current_return(prices: pd.DataFrame) -> float | None:
    close = pd.to_numeric(prices["close"], errors="coerce")
    if len(close.dropna()) < 2:
        return None
    return float(close.iloc[-1] / close.iloc[-2] - 1.0)

