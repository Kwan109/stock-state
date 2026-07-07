from __future__ import annotations

from typing import Any, Protocol

import pandas as pd


class ProviderError(RuntimeError):
    """Base provider error."""


class ProviderNotAvailableError(ProviderError):
    """Raised when a provider port exists but has no implementation."""


class DataProvider(Protocol):
    name: str

    def get_price_history(self, ticker: str, lookback: str = "5y") -> pd.DataFrame:
        """Return [open, high, low, close, volume], daily ascending, adjusted."""

    def get_info(self, ticker: str) -> dict[str, Any]:
        """Return point-in-time-ish quote/fundamental metadata where available."""

    def get_annual_financials(self, ticker: str) -> pd.DataFrame:
        """Return annual financial rows indexed by report period end."""

    def get_quarterly_financials(self, ticker: str) -> pd.DataFrame:
        """Return quarterly financial rows indexed by report period end."""

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        """Return balance sheet rows indexed by report period end."""

    def get_earnings_dates(self, ticker: str) -> pd.DataFrame:
        """Return earnings calendar/surprise data where available."""

    def get_analyst_data(self, ticker: str) -> dict[str, Any]:
        """Return defensive raw analyst endpoint snapshots."""

