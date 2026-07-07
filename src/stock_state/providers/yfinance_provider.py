from __future__ import annotations

import contextlib
import io
import time
from typing import Any

import numpy as np
import pandas as pd

from stock_state.providers.base import ProviderError


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, throttle_seconds: float = 0.5) -> None:
        self.throttle_seconds = throttle_seconds

    def _yf(self) -> Any:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError(
                "yfinance is not installed; run `python3 -m pip install -e .`"
            ) from exc
        return yf

    def _ticker(self, ticker: str) -> Any:
        return self._yf().Ticker(ticker.upper())

    def _throttle(self) -> None:
        if self.throttle_seconds > 0:
            time.sleep(self.throttle_seconds)

    def get_price_history(self, ticker: str, lookback: str = "5y") -> pd.DataFrame:
        yf = self._yf()
        symbol = ticker.upper()
        self._throttle()
        raw = _quiet_call(
            lambda: yf.download(
                symbol,
                period=lookback,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        )
        return _normalize_price_frame(raw, symbol)

    def get_info(self, ticker: str) -> dict[str, Any]:
        self._throttle()
        tk = self._ticker(ticker)
        try:
            info = _quiet_call(tk.get_info)
        except Exception:
            try:
                info = _quiet_call(lambda: tk.info)
            except Exception:
                info = {}
        keys = {
            "sector",
            "sharesOutstanding",
            "trailingPE",
            "forwardPE",
            "priceToSalesTrailing12Months",
            "shortPercentOfFloat",
            "totalDebt",
            "totalCash",
            "marketCap",
            "dividendYield",
            "recommendationMean",
            "numberOfAnalystOpinions",
        }
        return {key: info.get(key) for key in keys if key in info}

    def get_annual_financials(self, ticker: str) -> pd.DataFrame:
        self._throttle()
        tk = self._ticker(ticker)
        try:
            raw = _quiet_call(lambda: tk.income_stmt)
        except Exception:
            raw = pd.DataFrame()
        return _normalize_income_statement(raw)

    def get_quarterly_financials(self, ticker: str) -> pd.DataFrame:
        self._throttle()
        tk = self._ticker(ticker)
        try:
            raw = _quiet_call(lambda: tk.quarterly_income_stmt)
        except Exception:
            raw = pd.DataFrame()
        return _normalize_income_statement(raw)

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        self._throttle()
        tk = self._ticker(ticker)
        try:
            raw = _quiet_call(lambda: tk.balance_sheet)
        except Exception:
            raw = pd.DataFrame()
        return _normalize_balance_sheet(raw)

    def get_earnings_dates(self, ticker: str) -> pd.DataFrame:
        self._throttle()
        tk = self._ticker(ticker)
        try:
            raw = _quiet_call(lambda: tk.earnings_dates)
        except Exception:
            raw = pd.DataFrame()
        if raw is None or raw.empty:
            return pd.DataFrame()
        out = raw.copy()
        out.index = pd.to_datetime(out.index, errors="coerce").tz_localize(None)
        out = out[~out.index.isna()].sort_index()
        return out

    def get_analyst_data(self, ticker: str) -> dict[str, Any]:
        self._throttle()
        tk = self._ticker(ticker)
        return {
            "analyst_price_targets": _safe_getattr(tk, "analyst_price_targets"),
            "recommendations_summary": _safe_getattr(tk, "recommendations_summary"),
            "recommendations": _safe_getattr(tk, "recommendations"),
            "earnings_estimate": _safe_getattr(tk, "earnings_estimate"),
            "eps_trend": _safe_getattr(tk, "eps_trend"),
            "eps_revisions": _safe_getattr(tk, "eps_revisions"),
        }


def _safe_getattr(obj: Any, name: str) -> Any:
    try:
        value = _quiet_call(lambda: getattr(obj, name))
    except Exception:
        return None
    return value


def _quiet_call(callback: Any) -> Any:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return callback()


def _normalize_price_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        for level in range(df.columns.nlevels):
            values = [str(v).upper() for v in df.columns.get_level_values(level)]
            if ticker.upper() in values:
                df = df.xs(ticker, axis=1, level=level, drop_level=True)
                break
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename)
    cols = ["open", "high", "low", "close", "volume"]
    missing = [col for col in cols if col not in df.columns]
    if missing:
        return pd.DataFrame(columns=cols)
    out = df[cols].copy()
    out.index = pd.to_datetime(out.index, errors="coerce").tz_localize(None)
    out = out[~out.index.isna()].sort_index()
    out = out.apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=["close"])
    return out


def _statement_table(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    stmt = raw.copy().T
    stmt.index = pd.to_datetime(stmt.index, errors="coerce").tz_localize(None)
    stmt = stmt[~stmt.index.isna()].sort_index()
    stmt.columns = [str(col).strip() for col in stmt.columns]
    return stmt


def _first_available(stmt: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    for alias in aliases:
        if alias in stmt.columns:
            return pd.to_numeric(stmt[alias], errors="coerce")
    return pd.Series(np.nan, index=stmt.index, dtype="float64")


def _normalize_income_statement(raw: pd.DataFrame) -> pd.DataFrame:
    stmt = _statement_table(raw)
    cols = [
        "diluted_eps",
        "total_revenue",
        "net_income",
        "diluted_shares",
        "gross_profit",
    ]
    if stmt.empty:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(index=stmt.index)
    out["diluted_eps"] = _first_available(stmt, ("Diluted EPS", "Diluted Eps"))
    out["total_revenue"] = _first_available(
        stmt, ("Total Revenue", "Operating Revenue")
    )
    out["net_income"] = _first_available(
        stmt,
        (
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income From Continuing Operation Net Minority Interest",
        ),
    )
    out["diluted_shares"] = _first_available(
        stmt,
        (
            "Diluted Average Shares",
            "Diluted Shares",
            "Weighted Average Diluted Shares Outstanding",
        ),
    )
    missing_eps = out["diluted_eps"].isna()
    fallback = out["net_income"] / out["diluted_shares"]
    out.loc[missing_eps, "diluted_eps"] = fallback.loc[missing_eps]
    out["gross_profit"] = _first_available(stmt, ("Gross Profit",))
    return out


def _normalize_balance_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    stmt = _statement_table(raw)
    cols = ["total_debt", "total_cash", "stockholders_equity"]
    if stmt.empty:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(index=stmt.index)
    out["total_debt"] = _first_available(
        stmt, ("Total Debt", "Long Term Debt And Capital Lease Obligation")
    )
    out["total_cash"] = _first_available(
        stmt,
        (
            "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
            "Cash Financial",
        ),
    )
    out["stockholders_equity"] = _first_available(
        stmt, ("Stockholders Equity", "Total Equity Gross Minority Interest")
    )
    return out
