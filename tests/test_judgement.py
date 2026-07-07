from __future__ import annotations

from dataclasses import replace

import pandas as pd

from stock_state.card import (
    AnalystFamily,
    AttributionFamily,
    CrowdingFamily,
    FundamentalsFamily,
    RelativeFamily,
    ValuationFamily,
    VolumePriceFamily,
    field,
    na,
)
from stock_state.config import DEFAULTS
from stock_state.judgement.engine import evaluate_judgement


def test_actionable_long_breakout(make_prices) -> None:
    judgement = _judge(make_prices)
    assert judgement.stance == "actionable_long"
    assert judgement.entry_context == "breakout_zone"
    assert judgement.trend_state == "strong_uptrend"


def test_earnings_overlay_blocks_actionable(make_prices) -> None:
    judgement = _judge(make_prices, days_to_earnings=3)
    assert judgement.earnings_overlay is True
    assert judgement.stance == "constructive_watch"
    assert "earnings_within_5d" in judgement.risk_flags


def test_distribution_pressure_in_uptrend(make_prices) -> None:
    judgement = _judge(
        make_prices,
        volume_price=_vp(state="温和上涨", hv_down=3, pct_from_high=-0.02),
    )
    assert judgement.tape_state == "distribution_pressure"
    assert judgement.stance == "distribution_risk"


def test_breakdown_and_avoid_until_reclaim(make_prices) -> None:
    breakdown = _judge(
        make_prices,
        volume_price=_vp(days_below=2, hv_down=1, sma50=90, sma200=100, state="放量下跌"),
        close=95,
    )
    avoid = _judge(
        make_prices,
        volume_price=_vp(days_below=12, hv_down=0, sma50=90, sma200=100, state="缩量上涨"),
        close=95,
    )
    assert breakdown.stance == "breakdown_risk"
    assert avoid.stance == "avoid_until_reclaim"


def test_extended_do_not_chase_overrides_breakout(make_prices) -> None:
    judgement = _judge(make_prices, crowding=_crowding(score=90, extension=95))
    assert judgement.entry_context == "too_hot"
    assert judgement.stance == "extended_do_not_chase"


def test_cheap_valuation_does_not_override_idiosyncratic_weakness(make_prices) -> None:
    judgement = _judge(
        make_prices,
        valuation=_valuation(pe=15, ps=20),
        attribution=_attribution("个股性下跌"),
    )
    assert judgement.valuation_context == "cheap_vs_history"
    assert judgement.stance == "distribution_risk"


def test_hv_down_threshold_is_config_driven(make_prices) -> None:
    cfg = replace(DEFAULTS, JUDGEMENT_HV_DOWN_THRESHOLD=99)
    judgement = _judge(
        make_prices,
        volume_price=_vp(state="温和上涨", hv_down=3, pct_from_high=-0.02),
        config=cfg,
    )
    assert judgement.tape_state == "neutral"
    assert judgement.stance == "constructive_watch"


def _judge(
    make_prices,
    *,
    volume_price: VolumePriceFamily | None = None,
    crowding: CrowdingFamily | None = None,
    valuation: ValuationFamily | None = None,
    relative: RelativeFamily | None = None,
    attribution: AttributionFamily | None = None,
    days_to_earnings: int | None = 30,
    close: float | None = None,
    config=DEFAULTS,
):
    prices = make_prices(260, daily_return=0.001)
    if close is not None:
        prices.iloc[-1, prices.columns.get_loc("close")] = close
    current_close = float(prices["close"].iloc[-1] if close is None else close)
    market = make_prices(260, daily_return=0.0005)
    return evaluate_judgement(
        as_of=pd.Timestamp("2026-01-01").date(),
        close=current_close,
        sector="Technology",
        prices=prices,
        market_prices=market,
        sector_prices=None,
        volume_price=volume_price or _vp(),
        crowding=crowding or _crowding(),
        valuation=valuation or _valuation(),
        relative=relative or _relative(),
        attribution=attribution or _attribution("正常"),
        fundamentals=_fundamentals(),
        analyst=_analyst(),
        days_to_next_earnings=field(days_to_earnings, "missing earnings calendar")
        if days_to_earnings is not None
        else na("missing earnings calendar"),
        provenance_stale=False,
        config=config,
    )


def _vp(
    *,
    state: str = "放量上涨",
    sma50: float = 110.0,
    sma200: float = 100.0,
    mom6: float = 0.2,
    pct_from_high: float = -0.01,
    days_below: int = 0,
    hv_down: int = 0,
    hv_up: int = 1,
) -> VolumePriceFamily:
    return VolumePriceFamily(
        state=state,
        volume_pct=field(95),
        atr_pct=field(0.02),
        dollar_volume=field(1_000_000_000),
        obv_norm_slope_20d=field(0.2),
        obv_trend="rising",
        updown_vol_ratio_10d=field(2.0),
        mfi_14=field(70),
        momentum_3m=field(0.1),
        momentum_6m=field(mom6),
        momentum_12_1=field(0.3),
        sma50=field(sma50),
        sma200=field(sma200),
        pct_from_252d_high=field(pct_from_high),
        days_below_sma200=field(days_below),
        hv_down_days_10d=field(hv_down),
        hv_up_days_10d=field(hv_up),
    )


def _crowding(score: float = 55, extension: float = 60) -> CrowdingFamily:
    return CrowdingFamily(
        crowding_score=field(score),
        turnover_pct=field(60),
        rvol_pct=field(60),
        extension_pct=field(extension),
        corr_uplift=field(0.5),
        short_percent_of_float=field(3),
    )


def _valuation(pe: float = 50, ps: float = 55) -> ValuationFamily:
    return ValuationFamily(
        pe_ttm_pct=field(pe),
        ps_ttm_pct=field(ps),
        ev_sales_pct=field(ps),
        pe_ttm_current=field(25),
        ps_ttm_current=field(8),
        depth_years=field(4),
    )


def _relative(pct: float = 85, slope: float = 0.5) -> RelativeFamily:
    return RelativeFamily(
        rs_vs_qqq_slope_20d=field(slope),
        rs_vs_qqq_pct_3m=field(pct),
        rs_vs_sector_slope_20d=field(slope),
        rs_vs_sector_pct_3m=field(pct),
        flags=[],
    )


def _attribution(classification: str) -> AttributionFamily:
    return AttributionFamily(
        classification=classification,
        market_component=field(0.01),
        sector_component=na("market-only attribution"),
        residual=field(0.0),
        residual_z=field(0.0),
        beta_market=field(1.0),
        beta_sector=na("market-only attribution"),
        r_squared=field(0.6),
        mode="market-only",
        residual_vol_annualized=field(20),
    )


def _fundamentals() -> FundamentalsFamily:
    return FundamentalsFamily(
        revenue_yoy_annual=field(0.2),
        revenue_yoy_quarter=field(0.2),
        eps_yoy_annual=field(0.1),
        gross_margin=field(0.5),
        gross_margin_trend=field(1.0),
        roe=field(0.2),
        debt_to_equity=field(0.5),
        log_market_cap=field(20),
        market_cap=field(1_000_000_000),
        dividend_yield=field(0.0),
    )


def _analyst() -> AnalystFamily:
    return AnalystFamily(
        n_analysts=field(12),
        rating_counts=None,
        recommendation_mean=field(2),
        target_mean=field(150),
        target_median=field(150),
        target_low=field(100),
        target_high=field(200),
        target_upside_pct=field(0.2),
        forward_pe=field(25),
        eps_revision_90d_pct=field(0.02),
        eps_up_30d=field(3),
        eps_down_30d=field(1),
    )
