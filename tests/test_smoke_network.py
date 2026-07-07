from __future__ import annotations

import pytest

from stock_state.card import build_stock_state_card
from stock_state.providers.yfinance_provider import YFinanceProvider


@pytest.mark.network
def test_aapl_network_smoke(tmp_path) -> None:
    pytest.importorskip("yfinance")
    card = build_stock_state_card("AAPL", YFinanceProvider(throttle_seconds=0), root=tmp_path)
    assert card.ticker == "AAPL"
    assert card.close > 0

