from __future__ import annotations

from typing import Any

import pandas as pd

from stock_state.providers.base import ProviderNotAvailableError


class IBKRProvider:
    """Reserved IBKR provider port.

    A real implementation requires a running, authenticated TWS or IB Gateway
    session and market data permissions. The methods are intentionally stubbed
    in v1 so the CLI can expose a clear capability boundary.
    """

    name = "ibkr"

    def _raise(self) -> None:
        raise ProviderNotAvailableError("IBKR provider 未实装，需 IB Gateway；接口已预留")

    def get_price_history(self, ticker: str, lookback: str = "5y") -> pd.DataFrame:
        self._raise()

    def get_info(self, ticker: str) -> dict[str, Any]:
        self._raise()

    def get_annual_financials(self, ticker: str) -> pd.DataFrame:
        self._raise()

    def get_quarterly_financials(self, ticker: str) -> pd.DataFrame:
        self._raise()

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        self._raise()

    def get_earnings_dates(self, ticker: str) -> pd.DataFrame:
        self._raise()

    def get_analyst_data(self, ticker: str) -> dict[str, Any]:
        self._raise()

