from __future__ import annotations

from dataclasses import dataclass

from stock_state.card import StockStateCard
from stock_state.config import DEFAULTS, Defaults


@dataclass(frozen=True)
class RankSpec:
    direction: str


RANK_SPECS = {
    "crowding_score": RankSpec("desc"),
    "ep_yield": RankSpec("asc"),
    "momentum_6m": RankSpec("desc"),
    "rs_vs_qqq_pct_3m": RankSpec("desc"),
    "roe": RankSpec("desc"),
    "target_upside_pct": RankSpec("desc"),
}


def compute_cross_section(
    cards: list[StockStateCard],
    config: Defaults = DEFAULTS,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    caveat = f"组内排名基于 {len(cards)} 只自选股，非全市场统计"
    for card in cards:
        output[card.ticker] = {"caveat": caveat}
    for field_name in config.CS_RANK_FIELDS:
        values = [
            (card.ticker, _metric(card, field_name))
            for card in cards
            if _metric(card, field_name) is not None
        ]
        spec = RANK_SPECS[field_name]
        values.sort(key=lambda item: item[1], reverse=spec.direction == "desc")
        n_effective = len(values)
        ranks = {ticker: index + 1 for index, (ticker, _) in enumerate(values)}
        for card in cards:
            if card.ticker not in ranks:
                output[card.ticker][field_name] = {
                    "rank": None,
                    "n_effective": n_effective,
                    "pct_in_list": None,
                }
            else:
                rank = ranks[card.ticker]
                output[card.ticker][field_name] = {
                    "rank": rank,
                    "n_effective": n_effective,
                    "pct_in_list": 100.0 * (n_effective - rank + 1) / n_effective,
                }
    return output


def _metric(card: StockStateCard, field_name: str) -> float | None:
    mapping = {
        "crowding_score": card.crowding.crowding_score.value,
        "ep_yield": card.valuation.pe_ttm_pct.value,
        "momentum_6m": card.volume_price.momentum_6m.value,
        "rs_vs_qqq_pct_3m": card.relative.rs_vs_qqq_pct_3m.value,
        "roe": card.fundamentals.roe.value,
        "target_upside_pct": card.analyst.target_upside_pct.value,
    }
    return mapping[field_name]

