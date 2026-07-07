from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stock_state.card import NAField, StockStateCard


def render_card(card: StockStateCard) -> Panel:
    title = (
        f"{card.ticker} · {card.as_of} · 收盘 {money(card.close)} "
        f"({pct(card.day_return_pct)}) · 数据: "
        f"{card.provenance.provider}/{card.provenance.freshness}"
    )
    rows = [
        _line(
            "量价状态",
            f"{card.volume_price.state}   量能分位 {num(card.volume_price.volume_pct)}  "
            f"OBV{_obv_arrow(card.volume_price.obv_trend)}  "
            f"上下行量比 {num(card.volume_price.updown_vol_ratio_10d, 1)}  "
            f"MFI {num(card.volume_price.mfi_14, 0)}",
        ),
        _line(
            "动量",
            f"3月 {field_pct(card.volume_price.momentum_3m)}  "
            f"6月 {field_pct(card.volume_price.momentum_6m)}  "
            f"12-1 {field_pct(card.volume_price.momentum_12_1)}",
        ),
        _line(
            "拥挤度",
            f"{num(card.crowding.crowding_score, 0)}/100   "
            f"换手 {num(card.crowding.turnover_pct, 0)} | "
            f"波动 {num(card.crowding.rvol_pct, 0)} | "
            f"乖离 {num(card.crowding.extension_pct, 0)} | "
            f"相关抬升 {num(card.crowding.corr_uplift, 2)}",
        ),
        _line(
            "",
            f"空头占比 {field_number(card.crowding.short_percent_of_float, 1)}%"
            "（独立展示，不计入合成分）",
        ),
        _line(
            "基本面",
            f"营收YoY {field_pct(card.fundamentals.revenue_yoy_annual)} | "
            f"季营收YoY {field_pct(card.fundamentals.revenue_yoy_quarter)} | "
            f"ROE {field_pct(card.fundamentals.roe)} | "
            f"D/E {num(card.fundamentals.debt_to_equity, 2)}",
        ),
        _line(
            "分析师面",
            f"覆盖 {num(card.analyst.n_analysts, 0)} · "
            f"均值 {num(card.analyst.recommendation_mean, 1)}"
            f"({_rating_label(card.analyst.recommendation_mean.value)}) · "
            f"目标价 {money_field(card.analyst.target_mean)}"
            f"({field_pct(card.analyst.target_upside_pct)}) · "
            f"前瞻PE {num(card.analyst.forward_pe, 1)} · "
            f"90日预期修正 {field_pct(card.analyst.eps_revision_90d_pct)} "
            f"(↑{num(card.analyst.eps_up_30d, 0)}/↓{num(card.analyst.eps_down_30d, 0)})",
        ),
        _line(
            "估值分位",
            f"PE {num(card.valuation.pe_ttm_pct, 0)} | "
            f"PS {num(card.valuation.ps_ttm_pct, 0)} | "
            f"EV/S {num(card.valuation.ev_sales_pct, 0)}   "
            f"(对自身 {num(card.valuation.depth_years, 1)} 年历史; "
            f"当前PE {num(card.valuation.pe_ttm_current, 1)})",
        ),
        _line(
            "相对强弱",
            f"vs QQQ 年化斜率 {field_pct(card.relative.rs_vs_qqq_slope_20d)} · "
            f"3月分位 {num(card.relative.rs_vs_qqq_pct_3m, 0)} · "
            f"{card.relative.flags}",
        ),
        _line(
            "今日归因",
            f"{card.attribution.classification} · "
            f"市场 {field_pct(card.attribution.market_component)} | "
            f"板块 {field_pct(card.attribution.sector_component)} | "
            f"残差 {field_pct(card.attribution.residual)} "
            f"(z={num(card.attribution.residual_z, 1)}, "
            f"R²={num(card.attribution.r_squared, 2)}, "
            f"ω={field_number(card.attribution.residual_vol_annualized, 1)}%)",
        ),
        _line(
            "财报事件",
            f"距下次 {num(card.days_to_next_earnings, 0)} 天 · "
            f"上次惊喜 {field_number(card.last_earnings_surprise_pct, 1)}%",
        ),
        _line("", "估值分位为相对自身历史，非跨股比较；shares/EV 用当前值近似"),
        _line("", card.analyst.note),
    ]
    if card.provenance.stale:
        rows.append(Text("STALE: 使用缓存降级数据", style="yellow"))
    return Panel(Group(*rows), title=title, border_style="cyan")


def render_history(rows: list[dict[str, Any]]) -> Table:
    table = Table(title="状态时间线")
    for column in ("date", "state", "crowding_score", "classification", "close", "volume_pct"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["date"]),
            str(row["state"]),
            _raw(row["crowding_score"], 0),
            str(row["classification"]),
            _raw(row["close"], 2),
            _raw(row["volume_pct"], 0),
        )
    return table


def render_explain(card: StockStateCard, family: str) -> Table:
    payload = getattr(card, family)
    table = Table(title=f"{card.ticker} · explain {family}")
    table.add_column("field")
    table.add_column("value")
    table.add_column("reason")
    for key, value in payload.model_dump().items():
        if isinstance(value, dict) and "value" in value:
            table.add_row(key, _raw(value["value"], 4), str(value.get("reason") or ""))
        else:
            table.add_row(key, str(value), "")
    return table


def render_watchlist_table(
    cards: list[StockStateCard],
    cross_section: dict[str, dict[str, object]],
) -> Table:
    table = Table(title="Watchlist 状态面板")
    columns = [
        "ticker",
        "close",
        "day%",
        "state",
        "归因",
        "crowding",
        "E/P",
        "mom_6m",
        "RS_3m",
        "ROE",
        "目标空间",
        "财报天数",
    ]
    for column in columns:
        table.add_column(column)
    for card in cards:
        ranks = cross_section.get(card.ticker, {})
        table.add_row(
            card.ticker,
            money(card.close),
            pct(card.day_return_pct),
            card.volume_price.state,
            card.attribution.classification,
            _rank(ranks, "crowding_score"),
            _rank(ranks, "ep_yield"),
            _rank(ranks, "momentum_6m"),
            _rank(ranks, "rs_vs_qqq_pct_3m"),
            _rank(ranks, "roe"),
            _rank(ranks, "target_upside_pct"),
            num(card.days_to_next_earnings, 0),
        )
    table.caption = "组内排名基于自选股小样本，非全市场统计"
    return table


def _line(label: str, body: str) -> Text:
    prefix = f"{label:<6}  " if label else " " * 10
    return Text(prefix, style="bold") + Text(body)


def _obv_arrow(trend: str | None) -> str:
    return {"rising": "↑", "falling": "↓", "flat": "→"}.get(trend or "", "?")


def _rating_label(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value <= 1.8:
        return "买入"
    if value <= 2.5:
        return "偏多"
    if value <= 3.5:
        return "持有"
    return "偏空"


def num(value: NAField, digits: int = 0) -> str:
    return field_number(value, digits)


def field_number(value: NAField, digits: int = 1) -> str:
    if value.value is None:
        return f"N/A({value.reason})"
    return f"{value.value:.{digits}f}"


def field_pct(value: NAField) -> str:
    if value.value is None:
        return f"N/A({value.reason})"
    return pct(value.value)


def pct(value: float) -> str:
    return f"{value * 100:+.1f}%"


def money(value: float) -> str:
    return f"${value:,.2f}"


def money_field(value: NAField) -> str:
    if value.value is None:
        return f"N/A({value.reason})"
    return money(value.value)


def _raw(value: Any, digits: int) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _rank(ranks: dict[str, object], field_name: str) -> str:
    block = ranks.get(field_name)
    if not isinstance(block, dict) or block.get("rank") is None:
        return "N/A"
    return f"{block['rank']}/{block['n_effective']}"

