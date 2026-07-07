from __future__ import annotations

import json
from collections import Counter
from typing import Any

from stock_state.card import NAField, StockStateCard
from stock_state.config import DEFAULTS, Defaults


CONTEXT_KEYS = ("trend_state", "tape_state", "rs_context", "attribution_context")


def build_digest(
    cards: list[StockStateCard],
    cross_section: dict[str, dict[str, object]] | None = None,
    *,
    config: Defaults = DEFAULTS,
) -> dict[str, Any]:
    ordered = sorted(cards, key=_card_priority)
    digest = {
        "date": str(ordered[0].as_of) if ordered else None,
        "n_tickers": len(ordered),
        "stale_count": sum(1 for card in ordered if card.provenance.stale),
        "stance_distribution": dict(Counter(card.judgement.stance for card in ordered)),
        "cards": [
            _card_digest(card, cross_section or {}, config.NARRATOR_DIGEST_EVIDENCE_N)
            for card in ordered
        ],
    }
    return compact_digest(digest, config.NARRATOR_MAX_BRIEF_CHARS)


def digest_to_json(digest: dict[str, Any]) -> str:
    return json.dumps(digest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_digest(digest: dict[str, Any], max_chars: int) -> dict[str, Any]:
    if len(digest_to_json(digest)) <= max_chars:
        return digest
    out = json.loads(json.dumps(digest, ensure_ascii=False))
    for evidence_n in (1, 0):
        for card in out.get("cards", []):
            card["evidence"] = card.get("evidence", [])[:evidence_n]
        if len(digest_to_json(out)) <= max_chars:
            return out
    for card in out.get("cards", []):
        for key in CONTEXT_KEYS:
            card.pop(key, None)
    if len(digest_to_json(out)) <= max_chars:
        return out
    kept: list[dict[str, Any]] = []
    for card in out.get("cards", []):
        candidate = {**out, "cards": kept + [card]}
        if len(digest_to_json(candidate)) > max_chars:
            break
        kept.append(card)
    out["cards"] = kept
    return out


def _card_digest(
    card: StockStateCard,
    cross_section: dict[str, dict[str, object]],
    evidence_n: int,
) -> dict[str, Any]:
    judgement = card.judgement
    return {
        "ticker": card.ticker,
        "close": _round(card.close),
        "day_return_pct": _round(card.day_return_pct * 100.0),
        "stance": judgement.stance,
        "earnings_overlay": judgement.earnings_overlay,
        "confidence": judgement.confidence,
        "confidence_score": _round(judgement.confidence_score),
        "risk_flags": list(judgement.risk_flags),
        "evidence": list(judgement.evidence[:evidence_n]),
        "trend_state": judgement.trend_state,
        "tape_state": judgement.tape_state,
        "rs_context": judgement.rs_context,
        "attribution_context": judgement.attribution_context,
        "days_to_next_earnings": _field(card.days_to_next_earnings),
        "crowding_score": _field(card.crowding.crowding_score),
        "pe_ttm_pct": _field(card.valuation.pe_ttm_pct),
        "momentum_6m": _pct_field(card.volume_price.momentum_6m),
        "cross_section_ranks": cross_section.get(card.ticker, {}),
    }


def _card_priority(card: StockStateCard) -> tuple[int, str]:
    stance_rank = {
        "distribution_risk": 0,
        "breakdown_risk": 0,
        "avoid_until_reclaim": 0,
        "actionable_long": 1,
        "wait_for_pullback": 2,
        "constructive_watch": 3,
        "extended_do_not_chase": 4,
        "data_insufficient": 5,
        "no_clear_setup": 6,
    }.get(card.judgement.stance, 7)
    return (stance_rank, card.ticker)


def _field(field: NAField) -> float | None:
    return None if field.value is None else _round(field.value)


def _pct_field(field: NAField) -> float | None:
    return None if field.value is None else _round(field.value * 100.0)


def _round(value: float) -> float:
    return round(float(value), 1)

