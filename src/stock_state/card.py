from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, field_serializer, model_validator

from stock_state.cache import (
    CacheResult,
    get_or_fetch_frame,
    get_or_fetch_json,
    json_to_frames,
    log_judgement_event,
)
from stock_state.config import DEFAULTS, Defaults
from stock_state.indicators import current_return
from stock_state.providers.base import DataProvider, ProviderError


class Provenance(BaseModel):
    provider: str
    freshness: str
    as_of: date
    fetched_at: datetime
    cache_hit: bool
    stale: bool = False


class NAField(BaseModel):
    value: float | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _reason_required(self) -> "NAField":
        if self.value is None and not self.reason:
            self.reason = "not available"
        return self


class VolumePriceFamily(BaseModel):
    state: str
    volume_pct: NAField
    atr_pct: NAField
    dollar_volume: NAField
    obv_norm_slope_20d: NAField
    obv_trend: str | None
    updown_vol_ratio_10d: NAField
    mfi_14: NAField
    momentum_3m: NAField
    momentum_6m: NAField
    momentum_12_1: NAField
    sma50: NAField
    sma200: NAField
    pct_from_252d_high: NAField
    days_below_sma200: NAField
    hv_down_days_10d: NAField
    hv_up_days_10d: NAField


class CrowdingFamily(BaseModel):
    crowding_score: NAField
    turnover_pct: NAField
    rvol_pct: NAField
    extension_pct: NAField
    corr_uplift: NAField
    short_percent_of_float: NAField


class ValuationFamily(BaseModel):
    pe_ttm_pct: NAField
    ps_ttm_pct: NAField
    ev_sales_pct: NAField
    pe_ttm_current: NAField
    ps_ttm_current: NAField
    depth_years: NAField
    note: str = (
        "percentile vs own history only; shares/EV use current values (approx); "
        "PE percentile computed on E/P yield"
    )


class RelativeFamily(BaseModel):
    rs_vs_qqq_slope_20d: NAField
    rs_vs_qqq_pct_3m: NAField
    rs_vs_sector_slope_20d: NAField
    rs_vs_sector_pct_3m: NAField
    flags: list[str]


class AttributionFamily(BaseModel):
    classification: str
    market_component: NAField
    sector_component: NAField
    residual: NAField
    residual_z: NAField
    beta_market: NAField
    beta_sector: NAField
    r_squared: NAField
    mode: str
    residual_vol_annualized: NAField


class FundamentalsFamily(BaseModel):
    revenue_yoy_annual: NAField
    revenue_yoy_quarter: NAField
    eps_yoy_annual: NAField
    gross_margin: NAField
    gross_margin_trend: NAField
    roe: NAField
    debt_to_equity: NAField
    log_market_cap: NAField
    market_cap: NAField
    dividend_yield: NAField


class AnalystFamily(BaseModel):
    n_analysts: NAField
    rating_counts: dict[str, int] | None
    recommendation_mean: NAField
    target_mean: NAField
    target_median: NAField
    target_low: NAField
    target_high: NAField
    target_upside_pct: NAField
    forward_pe: NAField
    eps_revision_90d_pct: NAField
    eps_up_30d: NAField
    eps_down_30d: NAField
    note: str = "snapshot-level consensus; limited history; coverage gaps possible"


class JudgementBlock(BaseModel):
    stance: str
    earnings_overlay: bool
    trend_state: str
    tape_state: str
    crowding_risk: str
    valuation_context: str
    rs_context: str
    attribution_context: str
    risk_flags: list[str]
    entry_context: str
    exit_context: str
    confidence: str
    confidence_score: float
    evidence: list[str]
    caveat: str = (
        "规则型技术判读，未经前向收益验证；confidence 度量证据完整度，非盈利概率"
    )
    version: str = "judgement-v2.0"


class StockStateCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: date
    close: float
    day_return_pct: float
    sector: str | None
    sector_etf: str | None
    volume_price: VolumePriceFamily
    crowding: CrowdingFamily
    valuation: ValuationFamily
    relative: RelativeFamily
    attribution: AttributionFamily
    fundamentals: FundamentalsFamily
    analyst: AnalystFamily
    days_to_next_earnings: NAField
    last_earnings_surprise_pct: NAField
    judgement: JudgementBlock
    provenance: Provenance

    @field_serializer("as_of")
    def _date(self, value: date) -> str:
        return value.isoformat()


def field(value: float | int | None, reason: str = "not available") -> NAField:
    if value is None:
        return NAField(value=None, reason=reason)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return NAField(value=None, reason=reason)
    if pd.isna(numeric):
        return NAField(value=None, reason=reason)
    return NAField(value=numeric)


def na(reason: str) -> NAField:
    return NAField(value=None, reason=reason)


@dataclass(frozen=True)
class LoadedInputs:
    ticker: str
    prices: pd.DataFrame
    market_prices: pd.DataFrame
    sector_prices: pd.DataFrame | None
    info: dict[str, Any]
    annual_financials: pd.DataFrame
    quarterly_financials: pd.DataFrame
    balance_sheet: pd.DataFrame
    earnings_dates: pd.DataFrame
    analyst_data: dict[str, Any]
    provider_name: str
    sector: str | None
    sector_etf: str | None
    fetched_at: datetime
    cache_hit: bool
    stale: bool


def load_inputs(
    ticker: str,
    provider: DataProvider,
    *,
    config: Defaults = DEFAULTS,
    root: Path | str = ".",
    refresh: bool = False,
    offline: bool = False,
) -> LoadedInputs:
    symbol = ticker.upper()
    info_result = get_or_fetch_json(
        root=root,
        ticker=symbol,
        kind="info",
        fetch=lambda: provider.get_info(symbol),
        config=config,
        refresh=refresh,
        offline=offline,
        optional=True,
    )
    info = info_result.data
    sector = _clean_str(info.get("sector"))
    sector_etf = config.SECTOR_ETF_MAP.get(sector) if sector else None
    price_result = _load_price(
        symbol, provider, config=config, root=root, refresh=refresh, offline=offline
    )
    if price_result.data.empty:
        raise ProviderError(f"{symbol}: no price history returned")
    market_result = _load_price(
        config.MARKET_BENCH,
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    sector_result: CacheResult[pd.DataFrame] | None = None
    if sector_etf:
        sector_result = _load_price(
            sector_etf,
            provider,
            config=config,
            root=root,
            refresh=refresh,
            offline=offline,
            optional=True,
        )
    annual_result = _load_frame_kind(
        symbol,
        "annual",
        lambda: provider.get_annual_financials(symbol),
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    quarterly_result = _load_frame_kind(
        symbol,
        "quarterly",
        lambda: provider.get_quarterly_financials(symbol),
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    balance_result = _load_frame_kind(
        symbol,
        "balance",
        lambda: provider.get_balance_sheet(symbol),
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    earnings_result = _load_frame_kind(
        symbol,
        "earnings",
        lambda: provider.get_earnings_dates(symbol),
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    analyst_result = get_or_fetch_json(
        root=root,
        ticker=symbol,
        kind="analyst",
        fetch=lambda: provider.get_analyst_data(symbol),
        config=config,
        refresh=refresh,
        offline=offline,
        optional=True,
    )
    results: list[CacheResult[Any]] = [
        info_result,
        price_result,
        market_result,
        annual_result,
        quarterly_result,
        balance_result,
        earnings_result,
        analyst_result,
    ]
    if sector_result is not None:
        results.append(sector_result)
    fetched_at = max(result.fetched_at for result in results)
    return LoadedInputs(
        ticker=symbol,
        prices=price_result.data,
        market_prices=market_result.data,
        sector_prices=sector_result.data if sector_result is not None else None,
        info=info,
        annual_financials=annual_result.data,
        quarterly_financials=quarterly_result.data,
        balance_sheet=balance_result.data,
        earnings_dates=earnings_result.data,
        analyst_data=json_to_frames(analyst_result.data),
        provider_name=provider.name,
        sector=sector,
        sector_etf=sector_etf,
        fetched_at=fetched_at,
        cache_hit=all(result.cache_hit for result in results),
        stale=any(result.stale for result in results),
    )


def _load_price(
    symbol: str,
    provider: DataProvider,
    *,
    config: Defaults,
    root: Path | str,
    refresh: bool,
    offline: bool,
    optional: bool = False,
) -> CacheResult[pd.DataFrame]:
    return get_or_fetch_frame(
        root=root,
        ticker=symbol,
        kind="prices",
        fetch=lambda: provider.get_price_history(symbol, config.LOOKBACK),
        config=config,
        refresh=refresh,
        offline=offline,
        price_like=True,
        optional=optional,
    )


def _load_frame_kind(
    symbol: str,
    kind: str,
    fetch: Any,
    provider: DataProvider,
    *,
    config: Defaults,
    root: Path | str,
    refresh: bool,
    offline: bool,
) -> CacheResult[pd.DataFrame]:
    _ = provider
    return get_or_fetch_frame(
        root=root,
        ticker=symbol,
        kind=kind,
        fetch=fetch,
        config=config,
        refresh=refresh,
        offline=offline,
        optional=True,
    )


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_stock_state_card(
    ticker: str,
    provider: DataProvider,
    *,
    config: Defaults = DEFAULTS,
    root: Path | str = ".",
    refresh: bool = False,
    offline: bool = False,
) -> StockStateCard:
    inputs = load_inputs(
        ticker,
        provider,
        config=config,
        root=root,
        refresh=refresh,
        offline=offline,
    )
    card = build_card_from_inputs(inputs, config=config)
    try:
        log_judgement_event(root, card)
    except Exception:
        pass
    return card


def build_card_from_inputs(
    inputs: LoadedInputs,
    *,
    config: Defaults = DEFAULTS,
    as_of: date | None = None,
) -> StockStateCard:
    from stock_state.families.analyst import compute_analyst
    from stock_state.families.attribution import compute_attribution
    from stock_state.families.crowding import compute_crowding
    from stock_state.families.fundamentals import compute_fundamentals
    from stock_state.families.relative import compute_relative
    from stock_state.families.valuation import compute_valuation
    from stock_state.families.volume_price import compute_volume_price
    from stock_state.judgement.engine import evaluate_judgement

    prices = _slice_to_date(inputs.prices, as_of)
    market_prices = _slice_to_date(inputs.market_prices, as_of)
    sector_prices = (
        _slice_to_date(inputs.sector_prices, as_of)
        if inputs.sector_prices is not None
        else None
    )
    if prices.empty:
        raise ProviderError(f"{inputs.ticker}: no price history returned")
    if len(prices) < 2:
        raise ProviderError(f"{inputs.ticker}: insufficient price history")
    as_of_date = pd.to_datetime(prices.index[-1]).date()
    close = float(prices["close"].iloc[-1])
    day_return = current_return(prices)
    attribution = compute_attribution(prices, market_prices, sector_prices, config)
    volume_price = compute_volume_price(prices, config)
    crowding = compute_crowding(prices, sector_prices, inputs.info, config)
    valuation = compute_valuation(
        prices,
        _slice_statement(inputs.annual_financials, as_of_date),
        _slice_statement(inputs.balance_sheet, as_of_date),
        inputs.info,
        config,
    )
    relative = compute_relative(
        prices,
        market_prices,
        sector_prices,
        attribution.classification,
        config,
    )
    fundamentals = compute_fundamentals(
        _slice_statement(inputs.annual_financials, as_of_date),
        _slice_statement(inputs.quarterly_financials, as_of_date),
        _slice_statement(inputs.balance_sheet, as_of_date),
        inputs.info,
        config,
    )
    analyst = compute_analyst(inputs.analyst_data, inputs.info, close, config)
    days_to_next_earnings = _days_to_next_earnings(inputs.earnings_dates, as_of_date)
    last_earnings_surprise_pct = _last_earnings_surprise(inputs.earnings_dates, as_of_date)
    judgement = evaluate_judgement(
        as_of=as_of_date,
        close=close,
        sector=inputs.sector,
        prices=prices,
        market_prices=market_prices,
        sector_prices=sector_prices,
        volume_price=volume_price,
        crowding=crowding,
        valuation=valuation,
        relative=relative,
        attribution=attribution,
        fundamentals=fundamentals,
        analyst=analyst,
        days_to_next_earnings=days_to_next_earnings,
        provenance_stale=inputs.stale,
        config=config,
    )
    return StockStateCard(
        ticker=inputs.ticker,
        as_of=as_of_date,
        close=close,
        day_return_pct=0.0 if day_return is None else day_return,
        sector=inputs.sector,
        sector_etf=inputs.sector_etf,
        volume_price=volume_price,
        crowding=crowding,
        valuation=valuation,
        relative=relative,
        attribution=attribution,
        fundamentals=fundamentals,
        analyst=analyst,
        days_to_next_earnings=days_to_next_earnings,
        last_earnings_surprise_pct=last_earnings_surprise_pct,
        judgement=judgement,
        provenance=Provenance(
            provider=inputs.provider_name,
            freshness="EOD_OR_DELAYED",
            as_of=as_of_date,
            fetched_at=inputs.fetched_at,
            cache_hit=inputs.cache_hit,
            stale=inputs.stale,
        ),
    )


def build_history_rows(
    inputs: LoadedInputs,
    *,
    days: int,
    config: Defaults = DEFAULTS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dates = list(pd.to_datetime(inputs.prices.index).date)[-days:]
    for item in dates:
        card = build_card_from_inputs(inputs, config=config, as_of=item)
        rows.append(
            {
                "date": card.as_of.isoformat(),
                "state": card.volume_price.state,
                "stance": card.judgement.stance,
                "crowding_score": card.crowding.crowding_score.value,
                "classification": card.attribution.classification,
                "close": card.close,
                "volume_pct": card.volume_price.volume_pct.value,
            }
        )
    return rows


def _slice_to_date(frame: pd.DataFrame | None, as_of: date | None) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if as_of is None:
        return frame.copy()
    index_dates = pd.to_datetime(frame.index).date
    return frame.loc[index_dates <= as_of].copy()


def _slice_statement(frame: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    index_dates = pd.to_datetime(frame.index).date
    return frame.loc[index_dates <= as_of].copy()


def _days_to_next_earnings(earnings_dates: pd.DataFrame, as_of: date) -> NAField:
    if earnings_dates is None or earnings_dates.empty:
        return na("missing earnings calendar")
    dates = pd.to_datetime(earnings_dates.index).date
    future = sorted(item for item in dates if item > as_of)
    if not future:
        return na("no future earnings date")
    return field((future[0] - as_of).days)


def _last_earnings_surprise(earnings_dates: pd.DataFrame, as_of: date) -> NAField:
    if earnings_dates is None or earnings_dates.empty:
        return na("missing earnings calendar")
    frame = earnings_dates.copy()
    dates = pd.to_datetime(frame.index).date
    frame = frame.loc[dates <= as_of]
    if frame.empty:
        return na("no historical earnings date")
    row = frame.iloc[-1]
    for key in ("Surprise(%)", "Surprise %", "surprisePercent", "surprise_pct"):
        if key in row.index:
            return field(row.get(key), "missing surprise")
    return na("missing surprise")
