from __future__ import annotations

import numpy as np
import pandas as pd

from stock_state.indicators import (
    atr,
    money_flow_index,
    obv_norm_slope,
    percentile_rank,
    updown_vol_ratio,
)


def test_percentile_rank_half_weight_ties() -> None:
    assert percentile_rank([1, 2, 2, 3], 2) == 50.0


def test_atr_manual_bars() -> None:
    prices = pd.DataFrame(
        {
            "high": [10, 12, 13, 14, 15],
            "low": [9, 10, 11, 13, 14],
            "close": [9.5, 11, 12, 13.5, 14.5],
        }
    )
    assert np.isclose(atr(prices, 3).iloc[-1], (2.0 + 2.0 + 1.5) / 3.0)


def test_obv_norm_slope_rising_for_uptrend(make_prices) -> None:
    prices = make_prices(40, daily_return=0.01)
    assert obv_norm_slope(prices, 20) > 0.05


def test_mfi_all_up_is_100(make_prices) -> None:
    prices = make_prices(20, daily_return=0.01)
    assert money_flow_index(prices, 14).iloc[-1] == 100.0


def test_updown_ratio_caps_when_no_down_days(make_prices) -> None:
    prices = make_prices(20, daily_return=0.01)
    assert updown_vol_ratio(prices, 10, 10.0) == 10.0

