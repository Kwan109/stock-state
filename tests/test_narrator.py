from __future__ import annotations

from dataclasses import replace

from stock_state.card import build_stock_state_card
from stock_state.config import DEFAULTS
from stock_state.cross_section import compute_cross_section
from stock_state.narrator.brief import generate_brief
from stock_state.narrator.digest import build_digest, compact_digest, digest_to_json
from stock_state.narrator.validator import REQUIRED_CAVEAT, validate_brief
from test_card import MockProvider


class FakeNarratorClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, prompt: str, digest: dict[str, object]) -> str:
        self.calls += 1
        card = digest["cards"][0]
        return (
            "## 今日必看\n"
            f"{card['ticker']} 值得优先关注，需要打开量价和归因面板复核"
            f"（{card['ticker']}: {card['stance']}, close={card['close']}）。\n\n"
            "## 风险台账\n无。\n\n"
            "## 机会关注\n"
            f"{card['ticker']} 条件需人工复核（{card['ticker']}: {card['stance']}）。\n\n"
            "## 组合观察\n无。\n\n"
            "## 数据质量\n无异常。\n"
            f"{REQUIRED_CAVEAT}"
        )


class BombNarratorClient:
    provider = "fake"
    model = "bomb"

    def generate(self, *, prompt: str, digest: dict[str, object]) -> str:
        raise AssertionError("cache should avoid second API call")


def test_digest_whitelist_excludes_card_internals(make_prices, tmp_path) -> None:
    card = build_stock_state_card("MOCK", MockProvider(make_prices), root=tmp_path)
    digest = build_digest([card], compute_cross_section([card]))
    rendered = digest_to_json(digest)

    assert "MOCK" in rendered
    assert "sector_etf" not in rendered
    assert "provenance" not in rendered
    assert "raw_response" not in rendered


def test_digest_compacts_large_watchlist_to_valid_json() -> None:
    synthetic = {
        "date": "2026-01-01",
        "n_tickers": 30,
        "stale_count": 0,
        "stance_distribution": {"constructive_watch": 30},
        "cards": [
            {
                "ticker": f"T{i}",
                "close": 100.0 + i,
                "day_return_pct": 0.1,
                "stance": "constructive_watch",
                "evidence": ["x" * 100],
                "trend_state": "strong_uptrend",
                "tape_state": "neutral",
                "rs_context": "leader",
                "attribution_context": "normal",
            }
            for i in range(30)
        ],
    }
    compacted = compact_digest(synthetic, 900)

    assert len(digest_to_json(compacted)) <= 900
    assert isinstance(compacted["cards"], list)


def test_validator_catches_fabrications() -> None:
    digest = {
        "cards": [
            {
                "ticker": "AAPL",
                "stance": "constructive_watch",
                "close": 100.0,
                "risk_flags": [],
            }
        ]
    }
    valid = (
        "## 今日必看\n"
        "AAPL 值得优先关注（AAPL: constructive_watch, close=100.0）。\n"
        f"{REQUIRED_CAVEAT}"
    )
    assert validate_brief(valid, digest).passed
    assert not validate_brief(valid.replace("100.0", "123.4"), digest).passed
    assert not validate_brief(valid.replace("constructive_watch", "distribution_risk"), digest).passed
    assert not validate_brief(valid.replace("值得优先关注", "买入"), digest).passed
    assert not validate_brief(valid.replace(REQUIRED_CAVEAT, ""), digest).passed


def test_generate_brief_uses_cache_on_second_run(make_prices, tmp_path) -> None:
    card = build_stock_state_card("MOCK", MockProvider(make_prices), root=tmp_path)
    cross = compute_cross_section([card])
    client = FakeNarratorClient()

    first = generate_brief([card], cross_section=cross, root=tmp_path, client=client)
    second = generate_brief([card], cross_section=cross, root=tmp_path, client=BombNarratorClient())

    assert first.available is True
    assert first.validation and first.validation.passed
    assert second.from_cache is True
    assert second.text == first.text
    assert client.calls == 1


def test_generate_brief_without_key_does_not_block(make_prices, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    card = build_stock_state_card("MOCK", MockProvider(make_prices), root=tmp_path)
    cfg = replace(DEFAULTS, NARRATOR_PROVIDER="anthropic")

    result = generate_brief([card], root=tmp_path, config=cfg)

    assert result.available is False
    assert "missing ANTHROPIC_API_KEY" in result.text
