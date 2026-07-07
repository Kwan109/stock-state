from __future__ import annotations

from dataclasses import dataclass

from stock_state.web import _brief_payload, _parse_tickers


@dataclass(frozen=True)
class _Validation:
    passed: bool
    violations: list[str]


@dataclass(frozen=True)
class _Brief:
    text: str = "brief"
    display_text: str = "brief"
    available: bool = True
    from_cache: bool = False
    provider: str = "fake"
    model: str = "fake-model"
    error: str | None = None
    validation: _Validation | None = _Validation(True, [])


def test_parse_tickers_dedupes_commas_and_whitespace() -> None:
    assert _parse_tickers("aapl, nvda\nAAPL  ko") == ["AAPL", "NVDA", "KO"]


def test_brief_payload_serializes_validation() -> None:
    payload = _brief_payload(_Brief(validation=_Validation(False, ["bad number"])))
    assert payload["available"] is True
    assert payload["validation"] == {"passed": False, "violations": ["bad number"]}
