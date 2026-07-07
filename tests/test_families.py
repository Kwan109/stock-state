from __future__ import annotations

import numpy as np
import pandas as pd

from stock_state.config import DEFAULTS
from stock_state.families.attribution import compute_attribution
from stock_state.families.fundamentals import compute_fundamentals
from stock_state.families.valuation import compute_valuation
from stock_state.families.volume_price import _state


def test_state_truth_table() -> None:
    cfg = DEFAULTS
    assert _state(0.02, 0.01, 90, cfg) == "放量上涨"
    assert _state(0.02, 0.01, 50, cfg) == "温和上涨"
    assert _state(0.02, 0.01, 20, cfg) == "缩量上涨"
    assert _state(-0.02, 0.01, 90, cfg) == "放量下跌"
    assert _state(-0.02, 0.01, 50, cfg) == "温和下跌"
    assert _state(-0.02, 0.01, 20, cfg) == "缩量下跌"
    assert _state(0.001, 0.01, 90, cfg) == "盘整"


def test_market_only_attribution_systemic_down(prices_from_returns) -> None:
    market_returns = np.linspace(-0.004, 0.004, 130)
    market_returns[-1] = -0.01
    stock_returns = 1.5 * market_returns
    result = compute_attribution(
        prices_from_returns(stock_returns),
        prices_from_returns(market_returns),
        None,
        DEFAULTS,
    )
    assert np.isclose(result.beta_market.value, 1.5)
    assert abs(result.residual.value) < 1e-10
    assert result.classification == "系统性下跌"


def test_attribution_amplifier_and_defiant(prices_from_returns) -> None:
    market_returns = np.linspace(-0.004, 0.004, 130)
    noise = np.tile([0.004, -0.004], 65)
    market_returns[-1] = -0.01
    estimate_stock = 1.5 * market_returns + noise
    amplifier = estimate_stock.copy()
    amplifier[-1] = 1.5 * market_returns[-1] - 0.03
    defiant = estimate_stock.copy()
    defiant[-1] = 1.5 * market_returns[-1] + 0.03
    amp = compute_attribution(
        prices_from_returns(amplifier),
        prices_from_returns(market_returns),
        None,
        DEFAULTS,
    )
    strong = compute_attribution(
        prices_from_returns(defiant),
        prices_from_returns(market_returns),
        None,
        DEFAULTS,
    )
    assert amp.classification == "放大器"
    assert strong.classification == "逆市强势"


def test_valuation_ep_percentile_survives_negative_eps(make_prices) -> None:
    prices = make_prices(520, start="2022-01-03")
    annual = pd.DataFrame(
        {
            "diluted_eps": [-2.0, -1.0],
            "total_revenue": [100_000_000.0, 120_000_000.0],
        },
        index=pd.to_datetime(["2022-12-31", "2023-12-31"]),
    )
    result = compute_valuation(
        prices,
        annual,
        pd.DataFrame(),
        {"sharesOutstanding": 10_000_000.0},
        DEFAULTS,
    )
    assert result.pe_ttm_pct.value is not None
    assert result.pe_ttm_current.value is None
    assert result.pe_ttm_current.reason == "negative earnings"
    assert result.ps_ttm_pct.value is not None


def test_fundamentals_roe_and_debt_to_equity() -> None:
    annual = pd.DataFrame(
        {
            "total_revenue": [100.0, 120.0],
            "diluted_eps": [1.0, 1.2],
            "gross_profit": [50.0, 66.0],
            "net_income": [10.0, 15.0],
        },
        index=pd.to_datetime(["2022-12-31", "2023-12-31"]),
    )
    balance = pd.DataFrame(
        {"total_debt": [30.0], "stockholders_equity": [50.0]},
        index=pd.to_datetime(["2023-12-31"]),
    )
    result = compute_fundamentals(
        annual, pd.DataFrame(), balance, {"marketCap": 1_000.0, "dividendYield": 0.02}, DEFAULTS
    )
    assert np.isclose(result.roe.value, 0.3)
    assert np.isclose(result.debt_to_equity.value, 0.6)
    bad = compute_fundamentals(annual, pd.DataFrame(), balance.assign(stockholders_equity=-1.0), {}, DEFAULTS)
    assert bad.debt_to_equity.reason == "non-positive equity"
