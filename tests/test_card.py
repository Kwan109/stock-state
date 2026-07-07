from __future__ import annotations

import pandas as pd

from stock_state.card import build_card_from_inputs, build_stock_state_card, load_inputs
from stock_state.cross_section import compute_cross_section


class MockProvider:
    name = "mock"

    def __init__(self, make_prices):
        self._make_prices = make_prices

    def get_price_history(self, ticker: str, lookback: str = "5y") -> pd.DataFrame:
        drift = {"QQQ": 0.0005, "XLK": 0.0007}.get(ticker, 0.001)
        return self._make_prices(520, daily_return=drift)

    def get_info(self, ticker: str) -> dict:
        return {
            "sector": "Technology",
            "sharesOutstanding": 10_000_000.0,
            "trailingPE": 25.0,
            "priceToSalesTrailing12Months": 8.0,
            "shortPercentOfFloat": 0.03,
            "totalDebt": 1_000_000.0,
            "totalCash": 500_000.0,
            "marketCap": 1_000_000_000.0,
            "dividendYield": 0.0,
            "recommendationMean": 1.8,
            "numberOfAnalystOpinions": 12,
        }

    def get_annual_financials(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "diluted_eps": [3.0, 4.0, 5.0],
                "total_revenue": [100_000_000.0, 120_000_000.0, 150_000_000.0],
                "net_income": [30_000_000.0, 40_000_000.0, 50_000_000.0],
                "gross_profit": [50_000_000.0, 66_000_000.0, 90_000_000.0],
            },
            index=pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"]),
        )

    def get_quarterly_financials(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame(
            {"total_revenue": [20.0, 22.0, 23.0, 24.0, 30.0]},
            index=pd.to_datetime(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]),
        )

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame(
            {"total_debt": [10_000_000.0], "total_cash": [2_000_000.0], "stockholders_equity": [100_000_000.0]},
            index=pd.to_datetime(["2024-12-31"]),
        )

    def get_earnings_dates(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame(
            {"Surprise(%)": [5.0, None]},
            index=pd.to_datetime(["2025-01-30", "2026-01-30"]),
        )

    def get_analyst_data(self, ticker: str) -> dict:
        return {
            "analyst_price_targets": {"mean": 150.0, "median": 148.0, "low": 100.0, "high": 200.0},
            "recommendations_summary": pd.DataFrame(
                [{"strongBuy": 5, "buy": 4, "hold": 2, "sell": 1, "strongSell": 0}]
            ),
            "earnings_estimate": pd.DataFrame({"avg": [6.0]}, index=["0y"]),
            "eps_trend": pd.DataFrame({"current": [6.0], "90daysAgo": [5.0]}, index=["0y"]),
            "eps_revisions": pd.DataFrame({"upLast30days": [3], "downLast30days": [1]}, index=["0y"]),
        }


def test_card_builds_json_and_offline_cache(make_prices, tmp_path) -> None:
    provider = MockProvider(make_prices)
    card = build_stock_state_card("MOCK", provider, root=tmp_path)
    assert card.ticker == "MOCK"
    assert card.sector_etf == "XLK"
    assert card.model_dump_json()
    offline = build_stock_state_card("MOCK", provider, root=tmp_path, offline=True)
    assert offline.provenance.cache_hit is True


def test_judgement_log_failure_warns_without_blocking(make_prices, tmp_path, monkeypatch, capsys) -> None:
    provider = MockProvider(make_prices)

    def fail_log(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("stock_state.card.log_judgement_event", fail_log)
    card = build_stock_state_card("MOCK", provider, root=tmp_path)

    captured = capsys.readouterr()
    assert card.ticker == "MOCK"
    assert "failed to write judgement log" in captured.err
    assert "OSError: disk full" in captured.err
    assert str(tmp_path / "data_cache" / "judgement_log.parquet") in captured.err


def test_cross_section_is_outside_card_body(make_prices, tmp_path) -> None:
    provider = MockProvider(make_prices)
    card = build_stock_state_card("MOCK", provider, root=tmp_path)
    dumped = card.model_dump(mode="json")
    cross = compute_cross_section([card])
    assert card.model_dump(mode="json") == dumped
    assert "cross_section" not in dumped
    assert cross["MOCK"]["crowding_score"]["rank"] == 1


def test_single_and_batch_card_body_are_byte_identical(make_prices, tmp_path) -> None:
    provider = MockProvider(make_prices)
    inputs = load_inputs("MOCK", provider, root=tmp_path)
    single = build_card_from_inputs(inputs)
    batch = build_card_from_inputs(inputs)
    cross = compute_cross_section([batch])

    assert single.model_dump_json() == batch.model_dump_json()
    assert "cross_section" not in batch.model_dump(mode="json")
    assert cross["MOCK"]["crowding_score"]["rank"] == 1
