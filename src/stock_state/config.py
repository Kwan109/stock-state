from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Defaults:
    PCTL_WINDOW: int = 252
    VOL_WINDOW: int = 60
    VOL_HIGH: float = 80.0
    VOL_LOW: float = 40.0
    DIR_ATR_MULT: float = 0.5
    ATR_WINDOW: int = 20
    OBV_WINDOW: int = 20
    OBV_FLAT_BAND: float = 0.05
    UPDOWN_WINDOW: int = 10
    RATIO_CAP: float = 10.0
    MFI_WINDOW: int = 14
    RVOL_WINDOW: int = 20
    SMA_LONG: int = 200
    CORR_WINDOW: int = 60
    ATTR_WINDOW: int = 120
    MKT_DOWN: float = -0.005
    Z_AMPLIFIER: float = -1.0
    Z_DEFIANT: float = 1.0
    Z_IDIO: float = -1.5
    RS_SLOPE_WINDOW: int = 20
    RS_PCTL_WINDOW: int = 63
    REPORT_LAG_DAYS: int = 90
    LOOKBACK: str = "5y"
    CACHE_TTL_HOURS: int = 12
    MIN_PCTL_COVERAGE: float = 0.6
    MARKET_BENCH: str = "QQQ"
    MOM_3M: int = 63
    MOM_6M: int = 126
    MOM_12M: int = 252
    MOM_SKIP: int = 21
    MARGIN_TREND_YEARS: int = 3
    EPS_TREND_HORIZON: str = "0y"
    SMA_MID: int = 50
    HIGH_WINDOW: int = 252
    JUDGEMENT_HV_WINDOW: int = 10
    JUDGEMENT_ATTR_COUNT_WINDOW: int = 20
    JUDGEMENT_RESIDUAL_WINDOW: int = 5
    JUDGEMENT_NEAR_HIGH_PCT: float = -0.05
    JUDGEMENT_HIGH_VOLUME_PCT: float = 80.0
    JUDGEMENT_EXTREME_VOLUME_PCT: float = 95.0
    JUDGEMENT_HV_DOWN_THRESHOLD: int = 3
    JUDGEMENT_HV_UP_HOT_THRESHOLD: int = 4
    JUDGEMENT_CROWDING_LOW: float = 40.0
    JUDGEMENT_CROWDING_ELEVATED: float = 70.0
    JUDGEMENT_CROWDING_EXTREME: float = 85.0
    JUDGEMENT_EXTENDED_PCTL: float = 90.0
    JUDGEMENT_CHEAP_PCTL: float = 30.0
    JUDGEMENT_RICH_PCTL: float = 70.0
    JUDGEMENT_VERY_RICH_PCTL: float = 90.0
    JUDGEMENT_RS_LEADER_PCTL: float = 80.0
    JUDGEMENT_RS_LAGGING_PCTL: float = 50.0
    JUDGEMENT_RESIDUAL_STRONG_Z: float = 1.5
    JUDGEMENT_REL_ACCUM_Z: float = 1.0
    JUDGEMENT_MARKET_PRESSURE_5D: float = -0.03
    JUDGEMENT_EARNINGS_WINDOW_DAYS: int = 5
    JUDGEMENT_HIGH_SHORT_PERCENT: float = 15.0
    JUDGEMENT_NEGATIVE_REVISION: float = -0.05
    JUDGEMENT_MARGIN_DETERIORATION_PP: float = -3.0
    JUDGEMENT_HIGH_LEVERAGE_DE: float = 2.0
    JUDGEMENT_THIN_COVERAGE: float = 5.0
    JUDGEMENT_BREAKDOWN_MAX_DAYS: int = 10
    JUDGEMENT_CONF_HIGH: float = 0.75
    JUDGEMENT_CONF_MEDIUM: float = 0.5
    JUDGEMENT_MIN_COVERAGE: float = 0.6
    NARRATOR_ENABLED: bool = True
    NARRATOR_PROVIDER: str = "anthropic"
    NARRATOR_MODEL: str = "claude-sonnet-4-6"
    NARRATOR_OPENAI_MODEL: str = "gpt-5.5"
    NARRATOR_MAX_TOKENS: int = 1200
    NARRATOR_TEMPERATURE: float = 0.2
    NARRATOR_MAX_BRIEF_CHARS: int = 1600
    NARRATOR_DIGEST_EVIDENCE_N: int = 3
    CS_RANK_FIELDS: tuple[str, ...] = (
        "crowding_score",
        "ep_yield",
        "momentum_6m",
        "rs_vs_qqq_pct_3m",
        "roe",
        "target_upside_pct",
    )
    SECTOR_ETF_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "Technology": "XLK",
            "Financial Services": "XLF",
            "Healthcare": "XLV",
            "Consumer Cyclical": "XLY",
            "Consumer Defensive": "XLP",
            "Energy": "XLE",
            "Industrials": "XLI",
            "Basic Materials": "XLB",
            "Real Estate": "XLRE",
            "Utilities": "XLU",
            "Communication Services": "XLC",
        }
    )


DEFAULTS = Defaults()
