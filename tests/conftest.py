from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def guard_repo_judgement_log(monkeypatch) -> None:
    import stock_state.card as card_module
    import stock_state.cli as cli_module

    original = card_module.log_judgement_event
    repo_root = Path.cwd().resolve()

    def guarded(root, card):
        assert Path(root).resolve() != repo_root, (
            "tests must write judgement logs under tmp_path, not repo data_cache"
        )
        return original(root, card)

    monkeypatch.setattr(card_module, "log_judgement_event", guarded)
    monkeypatch.setattr(cli_module, "log_judgement_event", guarded)


@pytest.fixture
def make_prices():
    def _make(
        n: int = 320,
        *,
        start: str = "2024-01-01",
        first: float = 100.0,
        daily_return: float = 0.001,
        volume: float = 1_000_000.0,
    ) -> pd.DataFrame:
        index = pd.bdate_range(start, periods=n)
        close = first * np.cumprod(np.full(n, 1.0 + daily_return))
        return pd.DataFrame(
            {
                "open": close * 0.995,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume + np.arange(n) * 1000.0,
            },
            index=index,
        )

    return _make


@pytest.fixture
def prices_from_returns():
    def _make(returns: np.ndarray, start: str = "2024-01-01") -> pd.DataFrame:
        index = pd.bdate_range(start, periods=len(returns) + 1)
        close = 100.0 * np.concatenate([[1.0], np.cumprod(1.0 + returns)])
        return pd.DataFrame(
            {
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000.0,
            },
            index=index,
        )

    return _make
