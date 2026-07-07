from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from stock_state.narrator.digest import digest_to_json


REQUIRED_CAVEAT = "本简报为规则型系统输出的叙述整理，未经前向收益验证，不构成投资建议。"
STANCE_WORDS = {
    "actionable_long",
    "wait_for_pullback",
    "constructive_watch",
    "extended_do_not_chase",
    "distribution_risk",
    "breakdown_risk",
    "avoid_until_reclaim",
    "data_insufficient",
    "no_clear_setup",
}
BLACKLISTED_VERBS = ("买入", "卖出", "加仓", "减仓", "清仓")
ALLOWED_UPPERCASE = {
    "AI",
    "API",
    "EV",
    "ETF",
    "JSON",
    "MFI",
    "NA",
    "OBV",
    "PE",
    "PS",
    "QQQ",
    "RS",
    "SMA",
}


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    violations: list[str]


def validate_brief(text: str, digest: dict[str, Any]) -> ValidationResult:
    violations: list[str] = []
    tickers = {str(card["ticker"]) for card in digest.get("cards", [])}
    ticker_to_stance = {str(card["ticker"]): str(card["stance"]) for card in digest.get("cards", [])}
    _validate_tickers(text, tickers, violations)
    _validate_numbers(text, digest, violations)
    _validate_stances(text, ticker_to_stance, violations)
    if REQUIRED_CAVEAT not in text:
        violations.append("missing required caveat")
    for verb in BLACKLISTED_VERBS:
        if verb in text:
            violations.append(f"blacklisted directive verb: {verb}")
    return ValidationResult(passed=not violations, violations=violations)


def _validate_tickers(text: str, tickers: set[str], violations: list[str]) -> None:
    found = set(re.findall(r"\b[A-Z][A-Z0-9.]{1,7}\b", text))
    unknown = sorted(found - tickers - ALLOWED_UPPERCASE)
    if unknown:
        violations.append(f"unknown ticker(s): {', '.join(unknown)}")


def _validate_numbers(text: str, digest: dict[str, Any], violations: list[str]) -> None:
    allowed = [float(item) for item in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", digest_to_json(digest))]
    if not allowed:
        return
    for number in _numbers_from_output(text):
        if not any(abs(number - item) <= 0.05 for item in allowed):
            violations.append(f"number not in digest: {number:g}")


def _numbers_from_output(text: str) -> list[float]:
    values: list[float] = []
    for line in text.splitlines():
        if line.startswith("##"):
            continue
        for raw in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", line):
            values.append(float(raw))
    return values


def _validate_stances(
    text: str,
    ticker_to_stance: dict[str, str],
    violations: list[str],
) -> None:
    for line in text.splitlines():
        line_tickers = [ticker for ticker in ticker_to_stance if ticker in line]
        if not line_tickers:
            continue
        mentioned = {stance for stance in STANCE_WORDS if stance in line}
        for ticker in line_tickers:
            wrong = sorted(mentioned - {ticker_to_stance[ticker]})
            if wrong:
                violations.append(
                    f"{ticker} stance mismatch: expected {ticker_to_stance[ticker]}, got {', '.join(wrong)}"
                )
