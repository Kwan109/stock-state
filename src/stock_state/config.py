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

