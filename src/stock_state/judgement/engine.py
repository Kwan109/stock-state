from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from stock_state.card import (
    AnalystFamily,
    AttributionFamily,
    CrowdingFamily,
    FundamentalsFamily,
    JudgementBlock,
    NAField,
    RelativeFamily,
    ValuationFamily,
    VolumePriceFamily,
)
from stock_state.config import Defaults
from stock_state.indicators import ols_regression


@dataclass(frozen=True)
class AttributionDiagnostics:
    residual_5d_z: float | None
    amplifier_days_20d: int | None
    defiant_days_20d: int | None
    market_5d_return: float | None


def evaluate_judgement(
    *,
    as_of: date,
    close: float,
    sector: str | None,
    prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    volume_price: VolumePriceFamily,
    crowding: CrowdingFamily,
    valuation: ValuationFamily,
    relative: RelativeFamily,
    attribution: AttributionFamily,
    fundamentals: FundamentalsFamily,
    analyst: AnalystFamily,
    days_to_next_earnings: NAField,
    provenance_stale: bool,
    config: Defaults,
) -> JudgementBlock:
    diagnostics = attribution_diagnostics(prices, market_prices, sector_prices, config)
    trend_state = _trend_state(close, volume_price, config)
    tape_state = _tape_state(volume_price, crowding, trend_state, config)
    crowding_risk = _crowding_risk(crowding.crowding_score.value, config)
    valuation_context = _valuation_context(valuation, config)
    rs_context = _rs_context(relative, config)
    attribution_context = _attribution_context(attribution, diagnostics, config)
    risk_flags = _risk_flags(
        sector=sector,
        volume_price=volume_price,
        crowding=crowding,
        valuation=valuation,
        attribution_context=attribution_context,
        diagnostics=diagnostics,
        fundamentals=fundamentals,
        analyst=analyst,
        days_to_next_earnings=days_to_next_earnings,
        provenance_stale=provenance_stale,
        config=config,
    )
    entry_context = _entry_context(
        trend_state, tape_state, volume_price, crowding, crowding_risk, rs_context, config
    )
    exit_context = _exit_context(
        tape_state, volume_price, days_to_next_earnings, diagnostics, config
    )
    stance, stance_evidence = _stance(
        trend_state=trend_state,
        tape_state=tape_state,
        crowding_risk=crowding_risk,
        rs_context=rs_context,
        attribution_context=attribution_context,
        entry_context=entry_context,
        volume_price=volume_price,
        crowding=crowding,
        days_to_next_earnings=days_to_next_earnings,
        config=config,
    )
    confidence_score, confidence = _confidence(
        trend_state=trend_state,
        tape_state=tape_state,
        rs_context=rs_context,
        attribution_context=attribution_context,
        volume_price=volume_price,
        crowding=crowding,
        valuation=valuation,
        relative=relative,
        attribution=attribution,
        diagnostics=diagnostics,
        days_to_next_earnings=days_to_next_earnings,
        analyst=analyst,
        config=config,
    )
    earnings_overlay = _earnings_overlay(days_to_next_earnings, config)
    evidence = _evidence(
        stance_evidence,
        trend_state,
        tape_state,
        crowding_risk,
        valuation_context,
        rs_context,
        attribution_context,
        volume_price,
        diagnostics,
    )
    return JudgementBlock(
        stance=stance,
        earnings_overlay=earnings_overlay,
        trend_state=trend_state,
        tape_state=tape_state,
        crowding_risk=crowding_risk,
        valuation_context=valuation_context,
        rs_context=rs_context,
        attribution_context=attribution_context,
        risk_flags=risk_flags,
        entry_context=entry_context,
        exit_context=exit_context,
        confidence=confidence,
        confidence_score=confidence_score,
        evidence=evidence[:6],
    )


def attribution_diagnostics(
    prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    sector_prices: pd.DataFrame | None,
    config: Defaults,
) -> AttributionDiagnostics:
    aligned = _aligned_returns(prices, market_prices, sector_prices)
    if aligned is None or len(aligned) < config.ATTR_WINDOW + config.JUDGEMENT_RESIDUAL_WINDOW:
        return AttributionDiagnostics(None, None, None, None)
    count = min(config.JUDGEMENT_ATTR_COUNT_WINDOW, len(aligned) - config.ATTR_WINDOW)
    rows: list[tuple[float, float | None, str, float]] = []
    for target_pos in range(len(aligned) - count, len(aligned)):
        estimate = aligned.iloc[target_pos - config.ATTR_WINDOW : target_pos]
        target = aligned.iloc[target_pos]
        residual, sigma, classification = _rolling_residual(estimate, target, config)
        if residual is not None:
            rows.append((residual, sigma, classification, float(target["market"])))
    if not rows:
        return AttributionDiagnostics(None, None, None, None)
    residual_window = rows[-config.JUDGEMENT_RESIDUAL_WINDOW :]
    sigmas = [row[1] for row in residual_window if row[1] is not None and row[1] > 0]
    residual_5d_z = None
    if sigmas:
        sigma = float(np.mean(sigmas))
        residual_5d_z = sum(row[0] for row in residual_window) / (
            sigma * math.sqrt(len(residual_window))
        )
    amplifier_days = sum(1 for row in rows if row[2] == "放大器")
    defiant_days = sum(1 for row in rows if row[2] == "逆市强势")
    market_5d = None
    if len(rows) >= config.JUDGEMENT_RESIDUAL_WINDOW:
        market_5d = float(np.prod([1.0 + row[3] for row in rows[-5:]]) - 1.0)
    return AttributionDiagnostics(
        residual_5d_z=residual_5d_z,
        amplifier_days_20d=amplifier_days,
        defiant_days_20d=defiant_days,
        market_5d_return=market_5d,
    )


def _rolling_residual(
    estimate: pd.DataFrame,
    target: pd.Series,
    config: Defaults,
) -> tuple[float | None, float | None, str]:
    if "sector" in estimate.columns:
        sector_model = ols_regression(
            estimate["sector"].to_numpy(), estimate["market"].to_numpy()
        )
        if sector_model is None:
            return None, None, "N/A"
        u_est = sector_model.residuals
        sector_alpha, sector_beta = sector_model.coefficients
        u_target = float(target["sector"] - (sector_alpha + sector_beta * target["market"]))
        stock_x = np.column_stack([estimate["market"].to_numpy(), u_est])
        stock_model = ols_regression(estimate["stock"].to_numpy(), stock_x)
        if stock_model is None:
            return None, None, "N/A"
        beta_market = float(stock_model.coefficients[1])
        beta_sector = float(stock_model.coefficients[2])
        residual = float(
            target["stock"] - beta_market * target["market"] - beta_sector * u_target
        )
    else:
        stock_model = ols_regression(
            estimate["stock"].to_numpy(), estimate["market"].to_numpy()
        )
        if stock_model is None:
            return None, None, "N/A"
        beta_market = float(stock_model.coefficients[1])
        residual = float(target["stock"] - beta_market * target["market"])
    sigma = float(np.std(stock_model.residuals, ddof=1))
    residual_z = None if sigma == 0 else residual / sigma
    return residual, sigma, _classification(
        float(target["market"]), float(target["stock"]), residual_z, config
    )


def _trend_state(close: float, vp: VolumePriceFamily, config: Defaults) -> str:
    if vp.sma200.value is None or vp.sma50.value is None:
        return "insufficient_history"
    sma50 = vp.sma50.value
    sma200 = vp.sma200.value
    mom6 = vp.momentum_6m.value
    if close > sma50 > sma200 and mom6 is not None and mom6 > 0:
        return "strong_uptrend"
    if sma50 > sma200 and sma200 < close < sma50:
        return "uptrend_pullback"
    if sma50 < sma200 and close > sma50:
        return "downtrend_rally"
    if close < sma200 and sma50 < sma200:
        return "downtrend"
    return "neutral_range"


def _tape_state(
    vp: VolumePriceFamily,
    crowding: CrowdingFamily,
    trend_state: str,
    config: Defaults,
) -> str:
    state = vp.state
    pct_high = vp.pct_from_252d_high.value
    volume_pct = vp.volume_pct.value
    hv_down = vp.hv_down_days_10d.value
    if state == "N/A":
        return "unknown"
    if state == "放量上涨" and trend_state in {"strong_uptrend", "uptrend_pullback"}:
        return "demand_confirmation"
    if trend_state == "uptrend_pullback" and state in {"缩量下跌", "盘整"}:
        return "supply_drying_pullback"
    if pct_high is not None and pct_high >= config.JUDGEMENT_NEAR_HIGH_PCT:
        if state == "放量下跌" or (
            state == "盘整"
            and volume_pct is not None
            and volume_pct >= config.JUDGEMENT_HIGH_VOLUME_PCT
        ):
            return "churn_top_risk"
    if hv_down is not None and hv_down >= config.JUDGEMENT_HV_DOWN_THRESHOLD:
        return "distribution_pressure"
    if trend_state == "downtrend" and state == "放量下跌":
        if (
            volume_pct is not None
            and volume_pct >= config.JUDGEMENT_EXTREME_VOLUME_PCT
            and crowding.extension_pct.value is not None
            and crowding.extension_pct.value <= 10.0
        ):
            return "capitulation_flush"
    if trend_state in {"downtrend", "downtrend_rally"} and state == "缩量上涨":
        return "weak_rally"
    return "neutral"


def _crowding_risk(score: float | None, config: Defaults) -> str:
    if score is None:
        return "unknown"
    if score < config.JUDGEMENT_CROWDING_LOW:
        return "low"
    if score < config.JUDGEMENT_CROWDING_ELEVATED:
        return "moderate"
    if score < config.JUDGEMENT_CROWDING_EXTREME:
        return "elevated"
    return "extreme"


def _valuation_context(valuation: ValuationFamily, config: Defaults) -> str:
    pe = valuation.pe_ttm_pct.value
    ps = valuation.ps_ttm_pct.value
    if pe is None or ps is None:
        return "unknown"
    if abs(pe - ps) > 30.0:
        return "mixed"
    if pe >= config.JUDGEMENT_VERY_RICH_PCTL and ps >= 80.0:
        return "very_rich"
    if pe >= config.JUDGEMENT_RICH_PCTL:
        return "rich"
    if pe < config.JUDGEMENT_CHEAP_PCTL:
        return "cheap_vs_history"
    return "fair"


def _rs_context(relative: RelativeFamily, config: Defaults) -> str:
    pct = relative.rs_vs_qqq_pct_3m.value
    slope = relative.rs_vs_qqq_slope_20d.value
    if pct is None or slope is None:
        return "unknown"
    if pct >= config.JUDGEMENT_RS_LEADER_PCTL and slope > 0:
        return "leader"
    if slope > 0 and pct < config.JUDGEMENT_RS_LEADER_PCTL:
        return "improving"
    if slope < 0 and pct >= config.JUDGEMENT_RS_LAGGING_PCTL:
        return "deteriorating"
    if pct < config.JUDGEMENT_RS_LAGGING_PCTL and slope <= 0:
        return "lagging"
    return "neutral"


def _attribution_context(
    attribution: AttributionFamily,
    diagnostics: AttributionDiagnostics,
    config: Defaults,
) -> str:
    if attribution.classification == "N/A":
        return "unknown"
    residual_5d = diagnostics.residual_5d_z
    if attribution.classification == "个股性下跌" or (
        residual_5d is not None and residual_5d <= -config.JUDGEMENT_RESIDUAL_STRONG_Z
    ):
        return "idiosyncratic_weakness"
    if attribution.classification == "放大器" or (
        diagnostics.amplifier_days_20d is not None and diagnostics.amplifier_days_20d >= 2
    ):
        return "amplified_downside"
    if diagnostics.defiant_days_20d is not None and diagnostics.defiant_days_20d >= 2:
        return "relative_accumulation"
    if (
        diagnostics.market_5d_return is not None
        and diagnostics.market_5d_return <= config.JUDGEMENT_MARKET_PRESSURE_5D
        and residual_5d is not None
        and residual_5d >= config.JUDGEMENT_REL_ACCUM_Z
    ):
        return "relative_accumulation"
    if residual_5d is not None and residual_5d >= config.JUDGEMENT_RESIDUAL_STRONG_Z:
        return "idiosyncratic_strength"
    if (
        attribution.residual_z.value is not None
        and abs(attribution.residual_z.value) < 1.0
        and attribution.r_squared.value is not None
        and attribution.r_squared.value >= 0.5
    ):
        return "market_driven"
    return "normal"


def _risk_flags(
    *,
    sector: str | None,
    volume_price: VolumePriceFamily,
    crowding: CrowdingFamily,
    valuation: ValuationFamily,
    attribution_context: str,
    diagnostics: AttributionDiagnostics,
    fundamentals: FundamentalsFamily,
    analyst: AnalystFamily,
    days_to_next_earnings: NAField,
    provenance_stale: bool,
    config: Defaults,
) -> list[str]:
    flags: list[str] = []
    earnings_days = days_to_next_earnings.value
    if earnings_days is None:
        flags.append("earnings_date_unknown")
    elif earnings_days <= config.JUDGEMENT_EARNINGS_WINDOW_DAYS:
        flags.append("earnings_within_5d")
    if crowding.crowding_score.value is not None and crowding.crowding_score.value >= config.JUDGEMENT_CROWDING_EXTREME:
        flags.append("extreme_crowding")
    if volume_price.pct_from_252d_high.value is not None and volume_price.pct_from_252d_high.value > -0.01:
        pass
    if crowding.extension_pct.value is not None and crowding.extension_pct.value >= config.JUDGEMENT_EXTENDED_PCTL:
        flags.append("extended_gt90")
    if crowding.short_percent_of_float.value is not None and crowding.short_percent_of_float.value >= config.JUDGEMENT_HIGH_SHORT_PERCENT:
        flags.append("high_short_interest")
    if analyst.eps_revision_90d_pct.value is not None and analyst.eps_revision_90d_pct.value <= config.JUDGEMENT_NEGATIVE_REVISION:
        flags.append("negative_revisions")
    elif (
        analyst.eps_down_30d.value is not None
        and analyst.eps_up_30d.value is not None
        and analyst.eps_down_30d.value > analyst.eps_up_30d.value
    ):
        flags.append("negative_revisions")
    if fundamentals.gross_margin_trend.value is not None and fundamentals.gross_margin_trend.value <= config.JUDGEMENT_MARGIN_DETERIORATION_PP:
        flags.append("margin_deterioration")
    if (
        fundamentals.debt_to_equity.value is not None
        and fundamentals.debt_to_equity.value >= config.JUDGEMENT_HIGH_LEVERAGE_DE
        and sector != "Financial Services"
    ):
        flags.append("high_leverage")
    if diagnostics.amplifier_days_20d is not None and diagnostics.amplifier_days_20d >= 2:
        flags.append("amplifier_pattern")
    if attribution_context == "idiosyncratic_weakness":
        flags.append("idio_bleed")
    if valuation.pe_ttm_pct.value is not None and valuation.pe_ttm_pct.value >= config.JUDGEMENT_VERY_RICH_PCTL:
        flags.append("valuation_very_rich")
    if analyst.n_analysts.value is not None and analyst.n_analysts.value < config.JUDGEMENT_THIN_COVERAGE:
        flags.append("thin_coverage")
    if provenance_stale:
        flags.append("stale_data")
    return flags


def _entry_context(
    trend_state: str,
    tape_state: str,
    vp: VolumePriceFamily,
    crowding: CrowdingFamily,
    crowding_risk: str,
    rs_context: str,
    config: Defaults,
) -> str:
    if trend_state not in {"strong_uptrend", "uptrend_pullback"}:
        return "not_applicable"
    if crowding.extension_pct.value is not None and crowding.extension_pct.value >= config.JUDGEMENT_EXTENDED_PCTL:
        return "too_hot"
    if vp.hv_up_days_10d.value is not None and vp.hv_up_days_10d.value >= config.JUDGEMENT_HV_UP_HOT_THRESHOLD:
        return "too_hot"
    if tape_state == "demand_confirmation" and _near_high(vp, config):
        return "breakout_zone"
    if tape_state == "supply_drying_pullback":
        return "pullback_zone"
    if crowding_risk in {"elevated", "extreme"}:
        return "too_hot"
    return "base_not_ready"


def _exit_context(
    tape_state: str,
    vp: VolumePriceFamily,
    days_to_next_earnings: NAField,
    diagnostics: AttributionDiagnostics,
    config: Defaults,
) -> str:
    if _earnings_overlay(days_to_next_earnings, config):
        return "event_derisk_window"
    if (
        vp.days_below_sma200.value is not None
        and vp.days_below_sma200.value >= 1
        and vp.hv_down_days_10d.value is not None
        and vp.hv_down_days_10d.value >= 1
    ):
        return "broken_technical"
    if tape_state in {"churn_top_risk", "distribution_pressure"}:
        return "tighten_risk"
    if diagnostics.residual_5d_z is not None and diagnostics.residual_5d_z <= -1.5:
        return "tighten_risk"
    return "trail_normal"


def _stance(
    *,
    trend_state: str,
    tape_state: str,
    crowding_risk: str,
    rs_context: str,
    attribution_context: str,
    entry_context: str,
    volume_price: VolumePriceFamily,
    crowding: CrowdingFamily,
    days_to_next_earnings: NAField,
    config: Defaults,
) -> tuple[str, str]:
    days_below = volume_price.days_below_sma200.value
    hv_down = volume_price.hv_down_days_10d.value
    extension = volume_price.pct_from_252d_high.value
    _ = extension
    if trend_state == "insufficient_history" or attribution_context == "unknown":
        return "data_insufficient", "trend or attribution unavailable"
    if days_below is not None and hv_down is not None:
        if 1 <= days_below <= config.JUDGEMENT_BREAKDOWN_MAX_DAYS and hv_down >= 1:
            return "breakdown_risk", f"days_below_sma200={days_below:.0f}, hv_down_days_10d={hv_down:.0f}"
        if days_below > config.JUDGEMENT_BREAKDOWN_MAX_DAYS:
            return "avoid_until_reclaim", f"days_below_sma200={days_below:.0f}"
    uptrend = trend_state in {"strong_uptrend", "uptrend_pullback"}
    if uptrend and (
        tape_state in {"churn_top_risk", "distribution_pressure"}
        or attribution_context == "idiosyncratic_weakness"
    ):
        return "distribution_risk", f"tape={tape_state}, attribution={attribution_context}"
    if (
        uptrend
        and crowding.extension_pct.value is not None
        and crowding.extension_pct.value >= config.JUDGEMENT_EXTENDED_PCTL
        and crowding_risk in {"elevated", "extreme"}
    ):
        return "extended_do_not_chase", f"extension_pct={crowding.extension_pct.value:.0f}, crowding={crowding_risk}"
    base_breakout = (
        trend_state == "strong_uptrend"
        and tape_state == "demand_confirmation"
        and _near_high(volume_price, config)
        and rs_context in {"leader", "improving"}
        and attribution_context not in {"idiosyncratic_weakness", "amplified_downside"}
    )
    if base_breakout and crowding_risk != "extreme":
        if _earnings_overlay(days_to_next_earnings, config):
            return "constructive_watch", "otherwise actionable_long, blocked by earnings window"
        if crowding_risk == "elevated" or entry_context == "too_hot":
            return "wait_for_pullback", f"entry_context={entry_context}, crowding={crowding_risk}"
        return "actionable_long", "strong_uptrend + demand_confirmation + RS confirmation"
    if uptrend and tape_state in {"supply_drying_pullback", "neutral", "demand_confirmation"}:
        return "constructive_watch", f"trend={trend_state}, tape={tape_state}"
    return "no_clear_setup", f"trend={trend_state}, tape={tape_state}"


def _confidence(
    *,
    trend_state: str,
    tape_state: str,
    rs_context: str,
    attribution_context: str,
    volume_price: VolumePriceFamily,
    crowding: CrowdingFamily,
    valuation: ValuationFamily,
    relative: RelativeFamily,
    attribution: AttributionFamily,
    diagnostics: AttributionDiagnostics,
    days_to_next_earnings: NAField,
    analyst: AnalystFamily,
    config: Defaults,
) -> tuple[float, str]:
    core: list[Any] = [
        volume_price.sma50.value,
        volume_price.sma200.value,
        volume_price.momentum_6m.value,
        None if volume_price.state == "N/A" else volume_price.state,
        crowding.crowding_score.value,
        valuation.pe_ttm_pct.value,
        relative.rs_vs_qqq_pct_3m.value,
        relative.rs_vs_qqq_slope_20d.value,
        None if attribution.classification == "N/A" else attribution.classification,
        diagnostics.residual_5d_z,
        days_to_next_earnings.value,
        analyst.eps_revision_90d_pct.value,
    ]
    coverage = sum(item is not None for item in core) / len(core)
    directions = [
        _direction_trend(trend_state),
        _direction_tape(tape_state),
        _direction_rs(rs_context),
        _direction_attr(attribution_context),
    ]
    known = [item for item in directions if item != 0]
    conflicts = 0
    for idx, left in enumerate(known):
        for right in known[idx + 1 :]:
            if left != right:
                conflicts += 1
    conflicts = min(conflicts, 3)
    score = 0.6 * coverage + 0.4 * (1.0 - conflicts / 3.0)
    if coverage < config.JUDGEMENT_MIN_COVERAGE:
        return round(score, 4), "low"
    if score >= config.JUDGEMENT_CONF_HIGH:
        return round(score, 4), "high"
    if score >= config.JUDGEMENT_CONF_MEDIUM:
        return round(score, 4), "medium"
    return round(score, 4), "low"


def _evidence(
    stance_evidence: str,
    trend_state: str,
    tape_state: str,
    crowding_risk: str,
    valuation_context: str,
    rs_context: str,
    attribution_context: str,
    vp: VolumePriceFamily,
    diagnostics: AttributionDiagnostics,
) -> list[str]:
    items = [stance_evidence]
    items.append(f"trend_state={trend_state}; tape_state={tape_state}")
    if vp.pct_from_252d_high.value is not None:
        items.append(f"pct_from_252d_high={vp.pct_from_252d_high.value:.1%}")
    if vp.hv_down_days_10d.value is not None or vp.hv_up_days_10d.value is not None:
        items.append(
            f"hv_down_days_10d={_fmt(vp.hv_down_days_10d.value)}, "
            f"hv_up_days_10d={_fmt(vp.hv_up_days_10d.value)}"
        )
    if diagnostics.residual_5d_z is not None:
        items.append(f"residual_5d_z={diagnostics.residual_5d_z:+.2f}")
    items.append(
        f"crowding={crowding_risk}; valuation={valuation_context}; "
        f"rs={rs_context}; attribution={attribution_context}"
    )
    return [item for item in items if item]


def _near_high(vp: VolumePriceFamily, config: Defaults) -> bool:
    return (
        vp.pct_from_252d_high.value is not None
        and vp.pct_from_252d_high.value >= config.JUDGEMENT_NEAR_HIGH_PCT
    )


def _earnings_overlay(days_to_next_earnings: NAField, config: Defaults) -> bool:
    return (
        days_to_next_earnings.value is not None
        and days_to_next_earnings.value <= config.JUDGEMENT_EARNINGS_WINDOW_DAYS
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
    return None if aligned.empty else aligned


def _direction_trend(value: str) -> int:
    return {"strong_uptrend": 1, "uptrend_pullback": 1, "downtrend": -1, "downtrend_rally": -1}.get(value, 0)


def _direction_tape(value: str) -> int:
    return {
        "demand_confirmation": 1,
        "supply_drying_pullback": 1,
        "relative_accumulation": 1,
        "churn_top_risk": -1,
        "distribution_pressure": -1,
        "capitulation_flush": -1,
        "weak_rally": -1,
    }.get(value, 0)


def _direction_rs(value: str) -> int:
    return {"leader": 1, "improving": 1, "deteriorating": -1, "lagging": -1}.get(value, 0)


def _direction_attr(value: str) -> int:
    return {
        "relative_accumulation": 1,
        "idiosyncratic_strength": 1,
        "idiosyncratic_weakness": -1,
        "amplified_downside": -1,
    }.get(value, 0)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.0f}"
