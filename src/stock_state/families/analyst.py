from __future__ import annotations

from typing import Any

import pandas as pd

from stock_state.card import AnalystFamily, field, na
from stock_state.config import Defaults


RATING_KEYS = ("strongBuy", "buy", "hold", "sell", "strongSell")


def compute_analyst(
    analyst_data: dict[str, Any],
    info: dict[str, Any],
    close: float,
    config: Defaults,
) -> AnalystFamily:
    targets = _price_targets(analyst_data.get("analyst_price_targets"))
    target_mean = targets.get("target_mean")
    eps_estimate = _eps_estimate(
        analyst_data.get("earnings_estimate"), config.EPS_TREND_HORIZON
    )
    forward_pe = None
    forward_pe_reason = "missing earnings estimate"
    if eps_estimate is not None:
        if eps_estimate > 0:
            forward_pe = close / eps_estimate
        else:
            forward_pe_reason = "non-positive earnings estimate"
    elif _numeric(info.get("forwardPE")) is not None:
        forward_pe = _numeric(info.get("forwardPE"))
    eps_current, eps_90d = _eps_trend_pair(
        analyst_data.get("eps_trend"), config.EPS_TREND_HORIZON
    )
    revision = None
    if eps_current is not None and eps_90d is not None and eps_90d != 0:
        revision = (eps_current - eps_90d) / abs(eps_90d)
    eps_up, eps_down = _eps_revision_counts(analyst_data.get("eps_revisions"))
    return AnalystFamily(
        n_analysts=field(
            _numeric(info.get("numberOfAnalystOpinions")), "missing analyst count"
        ),
        rating_counts=_rating_counts(
            analyst_data.get("recommendations_summary"),
            analyst_data.get("recommendations"),
        ),
        recommendation_mean=field(
            _numeric(info.get("recommendationMean")), "missing recommendationMean"
        ),
        target_mean=field(target_mean, "missing target mean"),
        target_median=field(targets.get("target_median"), "missing target median"),
        target_low=field(targets.get("target_low"), "missing target low"),
        target_high=field(targets.get("target_high"), "missing target high"),
        target_upside_pct=field(
            target_mean / close - 1.0 if target_mean is not None and close > 0 else None,
            "missing target mean",
        ),
        forward_pe=field(forward_pe, forward_pe_reason),
        eps_revision_90d_pct=field(revision, "missing eps_trend 90d history"),
        eps_up_30d=field(eps_up, "missing eps_revisions"),
        eps_down_30d=field(eps_down, "missing eps_revisions"),
    )


def _price_targets(value: Any) -> dict[str, float | None]:
    data = {
        "target_mean": None,
        "target_median": None,
        "target_low": None,
        "target_high": None,
    }
    if value is None:
        return data
    if isinstance(value, dict):
        source = value
    elif isinstance(value, pd.DataFrame) and not value.empty:
        source = value.iloc[0].to_dict()
    else:
        return data
    aliases = {
        "target_mean": ("mean", "targetMean", "target_mean"),
        "target_median": ("median", "targetMedian", "target_median"),
        "target_low": ("low", "targetLow", "target_low"),
        "target_high": ("high", "targetHigh", "target_high"),
    }
    for output, names in aliases.items():
        for name in names:
            if name in source:
                data[output] = _numeric(source.get(name))
                break
    return data


def _rating_counts(summary: Any, recommendations: Any) -> dict[str, int] | None:
    frame = summary if isinstance(summary, pd.DataFrame) else None
    if frame is None or frame.empty:
        frame = recommendations if isinstance(recommendations, pd.DataFrame) else None
    if frame is None or frame.empty:
        return None
    row = frame.iloc[0]
    counts: dict[str, int] = {}
    for key in RATING_KEYS:
        value = row.get(key)
        number = _numeric(value)
        counts[key] = int(number) if number is not None else 0
    return counts if any(counts.values()) else None


def _eps_estimate(value: Any, horizon: str) -> float | None:
    frame = value if isinstance(value, pd.DataFrame) else None
    if frame is None or frame.empty:
        return None
    return _matrix_lookup(frame, horizon, ("avg", "mean", "Average"))


def _eps_trend_pair(value: Any, horizon: str) -> tuple[float | None, float | None]:
    frame = value if isinstance(value, pd.DataFrame) else None
    if frame is None or frame.empty:
        return None, None
    current = _matrix_lookup(frame, horizon, ("current", "Current"))
    ago_90 = _matrix_lookup(frame, horizon, ("90daysAgo", "90DaysAgo", "90dAgo"))
    return current, ago_90


def _eps_revision_counts(value: Any) -> tuple[float | None, float | None]:
    frame = value if isinstance(value, pd.DataFrame) else None
    if frame is None or frame.empty:
        return None, None
    up = _matrix_lookup(
        frame,
        "0y",
        ("upLast30days", "upLast30Days", "Up Last 30 Days", "up30days"),
    )
    down = _matrix_lookup(
        frame,
        "0y",
        ("downLast30days", "downLast30Days", "Down Last 30 Days", "down30days"),
    )
    if up is None:
        up = _first_named(frame, ("upLast30days", "upLast30Days"))
    if down is None:
        down = _first_named(frame, ("downLast30days", "downLast30Days"))
    return up, down


def _matrix_lookup(
    frame: pd.DataFrame,
    horizon: str,
    names: tuple[str, ...],
) -> float | None:
    for name in names:
        if horizon in frame.index and name in frame.columns:
            return _numeric(frame.loc[horizon, name])
        if name in frame.index and horizon in frame.columns:
            return _numeric(frame.loc[name, horizon])
    return None


def _first_named(frame: pd.DataFrame, names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in frame.columns:
            series = pd.to_numeric(frame[name], errors="coerce").dropna()
            if not series.empty:
                return float(series.iloc[0])
        if name in frame.index:
            series = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            if not series.empty:
                return float(series.iloc[0])
    return None


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number

