from __future__ import annotations

import pandas as pd

from stock_state.card import VolumePriceFamily, field, na
from stock_state.config import Defaults
from stock_state.indicators import (
    atr,
    current_return,
    money_flow_index,
    obv_norm_slope,
    rolling_latest_percentile,
    updown_vol_ratio,
)


def compute_volume_price(prices: pd.DataFrame, config: Defaults) -> VolumePriceFamily:
    if len(prices) < 2:
        return VolumePriceFamily(
            state="N/A",
            volume_pct=na("insufficient history"),
            atr_pct=na("insufficient history"),
            dollar_volume=na("insufficient history"),
            obv_norm_slope_20d=na("insufficient history"),
            obv_trend=None,
            updown_vol_ratio_10d=na("insufficient history"),
            mfi_14=na("insufficient history"),
            momentum_3m=na("insufficient history"),
            momentum_6m=na("insufficient history"),
            momentum_12_1=na("insufficient history"),
        )
    close = pd.to_numeric(prices["close"], errors="coerce")
    volume = pd.to_numeric(prices["volume"], errors="coerce")
    day_return = current_return(prices)
    volume_pct_value = rolling_latest_percentile(
        volume, config.VOL_WINDOW, config.MIN_PCTL_COVERAGE
    )
    atr_value = atr(prices, config.ATR_WINDOW).iloc[-1]
    prev_close = close.iloc[-2]
    atr_pct_value = (
        float(atr_value / prev_close)
        if pd.notna(atr_value) and pd.notna(prev_close) and prev_close != 0
        else None
    )
    state = _state(day_return, atr_pct_value, volume_pct_value, config)
    dollar_volume = close.iloc[-1] * volume.iloc[-1]
    obv_slope = obv_norm_slope(prices, config.OBV_WINDOW)
    mfi = money_flow_index(prices, config.MFI_WINDOW).iloc[-1]
    return VolumePriceFamily(
        state=state,
        volume_pct=field(volume_pct_value, "insufficient history"),
        atr_pct=field(atr_pct_value, "insufficient history"),
        dollar_volume=field(dollar_volume, "missing price or volume"),
        obv_norm_slope_20d=field(obv_slope, "insufficient history"),
        obv_trend=_obv_trend(obv_slope, config),
        updown_vol_ratio_10d=field(
            updown_vol_ratio(prices, config.UPDOWN_WINDOW, config.RATIO_CAP),
            "insufficient history",
        ),
        mfi_14=field(mfi, "insufficient history"),
        momentum_3m=_momentum(prices, config.MOM_3M),
        momentum_6m=_momentum(prices, config.MOM_6M),
        momentum_12_1=_momentum_12_1(prices, config),
    )


def _state(
    day_return: float | None,
    atr_pct: float | None,
    volume_pct: float | None,
    config: Defaults,
) -> str:
    if day_return is None or atr_pct is None or volume_pct is None:
        return "N/A"
    if abs(day_return) < config.DIR_ATR_MULT * atr_pct:
        return "盘整"
    direction = "up" if day_return > 0 else "down"
    if volume_pct >= config.VOL_HIGH:
        volume_bucket = "high"
    elif volume_pct <= config.VOL_LOW:
        volume_bucket = "low"
    else:
        volume_bucket = "normal"
    states = {
        ("up", "high"): "放量上涨",
        ("up", "normal"): "温和上涨",
        ("up", "low"): "缩量上涨",
        ("down", "high"): "放量下跌",
        ("down", "normal"): "温和下跌",
        ("down", "low"): "缩量下跌",
    }
    return states[(direction, volume_bucket)]


def _obv_trend(value: float | None, config: Defaults) -> str | None:
    if value is None:
        return None
    if value > config.OBV_FLAT_BAND:
        return "rising"
    if value < -config.OBV_FLAT_BAND:
        return "falling"
    return "flat"


def _momentum(prices: pd.DataFrame, lookback: int):
    close = pd.to_numeric(prices["close"], errors="coerce")
    if len(close) <= lookback:
        return na("insufficient history")
    base = close.iloc[-lookback - 1]
    if pd.isna(base) or base == 0:
        return na("missing price")
    return field(close.iloc[-1] / base - 1.0)


def _momentum_12_1(prices: pd.DataFrame, config: Defaults):
    close = pd.to_numeric(prices["close"], errors="coerce")
    required = config.MOM_12M + 1
    if len(close) <= required:
        return na("insufficient history")
    recent = close.iloc[-config.MOM_SKIP - 1]
    base = close.iloc[-config.MOM_12M - 1]
    if pd.isna(recent) or pd.isna(base) or base == 0:
        return na("missing price")
    return field(recent / base - 1.0)

