from __future__ import annotations

from typing import Any

import pandas as pd

from stock_state.card import ValuationFamily, field, na
from stock_state.config import Defaults
from stock_state.indicators import percentile_rank


def compute_valuation(
    prices: pd.DataFrame,
    annual_financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict[str, Any],
    config: Defaults,
) -> ValuationFamily:
    close = pd.to_numeric(prices["close"], errors="coerce")
    eps = _lagged_metric(prices.index, annual_financials, "diluted_eps", config)
    revenue = _lagged_metric(prices.index, annual_financials, "total_revenue", config)
    shares = _numeric(info.get("sharesOutstanding"))
    debt = _numeric(info.get("totalDebt"))
    cash = _numeric(info.get("totalCash"))
    if debt is None:
        debt = _latest_balance_value(balance_sheet, "total_debt")
    if cash is None:
        cash = _latest_balance_value(balance_sheet, "total_cash")

    ep_yield = eps / close
    pe_pct = _expensiveness_percentile(ep_yield, "insufficient history")

    if shares is None or shares <= 0:
        ps_pct = na("missing sharesOutstanding")
        ev_sales_pct = na("missing sharesOutstanding")
    else:
        sales_yield = revenue / (shares * close)
        ps_pct = _expensiveness_percentile(sales_yield, "insufficient history")
        if debt is None or cash is None:
            ev_sales_pct = na("missing debt or cash")
        else:
            enterprise_value = close * shares + debt - cash
            sales_ev_yield = revenue / enterprise_value.where(enterprise_value > 0)
            ev_sales_pct = _expensiveness_percentile(
                sales_ev_yield, "insufficient history"
            )

    latest_eps = eps.dropna().iloc[-1] if not eps.dropna().empty else None
    pe_current = _numeric(info.get("trailingPE"))
    if pe_current is None:
        if latest_eps is None:
            pe_current_field = na("negative or missing earnings")
        elif latest_eps <= 0:
            pe_current_field = na("negative earnings")
        else:
            pe_current_field = field(close.iloc[-1] / latest_eps)
    else:
        pe_current_field = field(pe_current)

    ps_current = _numeric(info.get("priceToSalesTrailing12Months"))
    if ps_current is None and shares is not None and shares > 0:
        latest_revenue = revenue.dropna().iloc[-1] if not revenue.dropna().empty else None
        if latest_revenue and latest_revenue > 0:
            ps_current = close.iloc[-1] * shares / latest_revenue

    depth = _depth_years([ep_yield, revenue])
    return ValuationFamily(
        pe_ttm_pct=pe_pct,
        ps_ttm_pct=ps_pct,
        ev_sales_pct=ev_sales_pct,
        pe_ttm_current=pe_current_field,
        ps_ttm_current=field(ps_current, "missing revenue or shares"),
        depth_years=field(depth, "insufficient history"),
    )


def ep_yield_proxy(card_value: float | None) -> float | None:
    if card_value is None:
        return None
    return card_value


def _lagged_metric(
    index: pd.Index,
    financials: pd.DataFrame,
    column: str,
    config: Defaults,
) -> pd.Series:
    out = pd.Series(index=pd.to_datetime(index), dtype="float64")
    if financials is None or financials.empty or column not in financials.columns:
        return out
    reports = financials[[column]].copy()
    reports.index = pd.to_datetime(reports.index)
    reports = reports.sort_index()
    for report_date, row in reports.iterrows():
        value = pd.to_numeric(row[column], errors="coerce")
        if pd.isna(value):
            continue
        effective = report_date + pd.Timedelta(days=config.REPORT_LAG_DAYS)
        out.loc[out.index >= effective] = float(value)
    return out


def _expensiveness_percentile(series: pd.Series, reason: str):
    valid = pd.to_numeric(series, errors="coerce").replace([float("inf"), -float("inf")], pd.NA).dropna()
    if len(valid) < 2:
        return na(reason)
    pct = percentile_rank(valid)
    if pct is None:
        return na(reason)
    return field(100.0 - pct)


def _depth_years(series_list: list[pd.Series]) -> float | None:
    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    for series in series_list:
        valid = pd.to_numeric(series, errors="coerce").dropna()
        if len(valid) >= 2:
            starts.append(pd.to_datetime(valid.index.min()))
            ends.append(pd.to_datetime(valid.index.max()))
    if not starts or not ends:
        return None
    return (max(ends) - min(starts)).days / 365.25


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _latest_balance_value(balance_sheet: pd.DataFrame, column: str) -> float | None:
    if balance_sheet is None or balance_sheet.empty or column not in balance_sheet.columns:
        return None
    series = pd.to_numeric(balance_sheet[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.sort_index().iloc[-1])

