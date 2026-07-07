from __future__ import annotations

import math
from typing import Any

import pandas as pd

from stock_state.card import FundamentalsFamily, field, na
from stock_state.config import Defaults


def compute_fundamentals(
    annual_financials: pd.DataFrame,
    quarterly_financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict[str, Any],
    config: Defaults,
) -> FundamentalsFamily:
    _ = config
    annual = _sorted(annual_financials)
    quarterly = _sorted(quarterly_financials)
    balance = _sorted(balance_sheet)
    market_cap = _numeric(info.get("marketCap"))
    dividend_yield = _numeric(info.get("dividendYield"))
    return FundamentalsFamily(
        revenue_yoy_annual=_growth(annual, "total_revenue", 1),
        revenue_yoy_quarter=_growth(quarterly, "total_revenue", 4),
        eps_yoy_annual=_eps_growth(annual),
        gross_margin=_gross_margin(annual),
        gross_margin_trend=_gross_margin_trend(annual, config.MARGIN_TREND_YEARS),
        roe=_roe(annual, balance),
        debt_to_equity=_debt_to_equity(balance),
        log_market_cap=field(
            math.log(market_cap) if market_cap is not None and market_cap > 0 else None,
            "missing marketCap",
        ),
        market_cap=field(market_cap, "missing marketCap"),
        dividend_yield=field(dividend_yield, "missing dividendYield"),
    )


def _growth(frame: pd.DataFrame, column: str, periods_back: int):
    if frame.empty or column not in frame.columns or len(frame) <= periods_back:
        return na("insufficient history")
    current = _numeric(frame[column].iloc[-1])
    previous = _numeric(frame[column].iloc[-periods_back - 1])
    if current is None or previous is None or previous == 0:
        return na("missing denominator")
    return field(current / previous - 1.0)


def _eps_growth(annual: pd.DataFrame):
    if annual.empty or "diluted_eps" not in annual.columns or len(annual) < 2:
        return na("insufficient history")
    current = _numeric(annual["diluted_eps"].iloc[-1])
    previous = _numeric(annual["diluted_eps"].iloc[-2])
    if current is None or previous is None:
        return na("missing EPS")
    if current <= 0 or previous <= 0:
        return na("sign change")
    return field(current / previous - 1.0)


def _gross_margin(annual: pd.DataFrame):
    if annual.empty or not {"gross_profit", "total_revenue"}.issubset(annual.columns):
        return na("missing gross profit or revenue")
    gross_profit = _numeric(annual["gross_profit"].iloc[-1])
    revenue = _numeric(annual["total_revenue"].iloc[-1])
    if gross_profit is None or revenue is None or revenue == 0:
        return na("missing denominator")
    return field(gross_profit / revenue)


def _gross_margin_trend(annual: pd.DataFrame, years: int):
    if annual.empty or not {"gross_profit", "total_revenue"}.issubset(annual.columns):
        return na("missing gross profit or revenue")
    margins = (
        pd.to_numeric(annual["gross_profit"], errors="coerce")
        / pd.to_numeric(annual["total_revenue"], errors="coerce")
    ).dropna()
    if len(margins) < years:
        return na("insufficient history")
    latest = float(margins.iloc[-1])
    average = float(margins.tail(years).mean())
    return field((latest - average) * 100.0)


def _roe(annual: pd.DataFrame, balance: pd.DataFrame):
    if annual.empty or balance.empty:
        return na("missing financial statements")
    net_income = _latest(annual, "net_income")
    equity = _latest(balance, "stockholders_equity")
    if net_income is None or equity is None:
        return na("missing net income or equity")
    if equity <= 0:
        return na("non-positive equity")
    return field(net_income / equity)


def _debt_to_equity(balance: pd.DataFrame):
    if balance.empty:
        return na("missing balance sheet")
    debt = _latest(balance, "total_debt")
    equity = _latest(balance, "stockholders_equity")
    if debt is None or equity is None:
        return na("missing debt or equity")
    if equity <= 0:
        return na("non-positive equity")
    return field(debt / equity)


def _latest(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number

