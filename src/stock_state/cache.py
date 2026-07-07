from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

import pandas as pd

from stock_state.config import Defaults
from stock_state.providers.base import ProviderError

T = TypeVar("T")


@dataclass(frozen=True)
class CacheResult(Generic[T]):
    data: T
    fetched_at: datetime
    cache_hit: bool
    stale: bool


def cache_dir(root: Path | str = ".") -> Path:
    path = Path(root) / "data_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_judgement_event(root: Path | str, card: Any) -> None:
    base = cache_dir(root)
    path = base / "judgement_log.parquet"
    row = pd.DataFrame(
        [
            {
                "date": str(card.as_of),
                "ticker": card.ticker,
                "stance": card.judgement.stance,
                "risk_flags": ",".join(card.judgement.risk_flags),
                "confidence_score": card.judgement.confidence_score,
                "version": card.judgement.version,
            }
        ]
    )
    if path.exists():
        existing = pd.read_parquet(path)
        existing = existing[
            ~(
                (existing["date"].astype(str) == str(card.as_of))
                & (existing["ticker"].astype(str) == card.ticker)
            )
        ]
        row = pd.concat([existing, row], ignore_index=True)
    row.sort_values(["date", "ticker"]).to_parquet(path, index=False)


def previous_closed_weekday(today: date | None = None) -> date:
    current = today or datetime.now(timezone.utc).date()
    candidate = current - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def price_cache_fresh(path: Path, fetched_at: datetime, config: Defaults) -> bool:
    if not path.exists():
        return False
    try:
        prices = pd.read_parquet(path)
    except Exception:
        return False
    if prices.empty:
        return False
    latest = pd.to_datetime(prices.index.max()).date()
    if latest < previous_closed_weekday():
        return False
    return not _ttl_expired(fetched_at, config)


def meta_cache_fresh(fetched_at: datetime, config: Defaults) -> bool:
    return not _ttl_expired(fetched_at, config)


def get_or_fetch_frame(
    *,
    root: Path | str,
    ticker: str,
    kind: str,
    fetch: Callable[[], pd.DataFrame],
    config: Defaults,
    refresh: bool = False,
    offline: bool = False,
    price_like: bool = False,
    optional: bool = False,
) -> CacheResult[pd.DataFrame]:
    base = cache_dir(root)
    frame_path = base / f"{ticker.upper()}_{kind}.parquet"
    meta_path = base / f"{ticker.upper()}_{kind}_meta.json"
    cached = _read_frame(frame_path)
    fetched_at = _read_fetched_at(meta_path)
    fresh = False
    if cached is not None and fetched_at is not None:
        fresh = (
            price_cache_fresh(frame_path, fetched_at, config)
            if price_like
            else meta_cache_fresh(fetched_at, config)
        )
    if offline:
        if cached is None or fetched_at is None:
            if optional:
                return CacheResult(pd.DataFrame(), _now(), True, True)
            raise ProviderError(f"offline cache missing for {ticker.upper()} {kind}")
        return CacheResult(cached, fetched_at, True, not fresh)
    if cached is not None and fetched_at is not None and fresh and not refresh:
        return CacheResult(cached, fetched_at, True, False)
    try:
        data = fetch()
        fetched = _now()
        _write_frame(frame_path, data)
        _write_meta(meta_path, fetched)
        return CacheResult(data, fetched, False, False)
    except Exception as exc:
        if cached is not None and fetched_at is not None:
            return CacheResult(cached, fetched_at, True, True)
        if optional:
            return CacheResult(pd.DataFrame(), _now(), False, True)
        raise ProviderError(str(exc)) from exc


def get_or_fetch_json(
    *,
    root: Path | str,
    ticker: str,
    kind: str,
    fetch: Callable[[], dict[str, Any]],
    config: Defaults,
    refresh: bool = False,
    offline: bool = False,
    optional: bool = False,
) -> CacheResult[dict[str, Any]]:
    base = cache_dir(root)
    json_path = base / f"{ticker.upper()}_{kind}.json"
    meta_path = base / f"{ticker.upper()}_{kind}_meta.json"
    cached = _read_json(json_path)
    fetched_at = _read_fetched_at(meta_path)
    fresh = fetched_at is not None and meta_cache_fresh(fetched_at, config)
    if offline:
        if cached is None or fetched_at is None:
            if optional:
                return CacheResult({}, _now(), True, True)
            raise ProviderError(f"offline cache missing for {ticker.upper()} {kind}")
        return CacheResult(cached, fetched_at, True, not fresh)
    if cached is not None and fetched_at is not None and fresh and not refresh:
        return CacheResult(cached, fetched_at, True, False)
    try:
        data = fetch()
        fetched = _now()
        _write_json(json_path, data)
        _write_meta(meta_path, fetched)
        return CacheResult(data, fetched, False, False)
    except Exception as exc:
        if cached is not None and fetched_at is not None:
            return CacheResult(cached, fetched_at, True, True)
        if optional:
            return CacheResult({}, _now(), False, True)
        raise ProviderError(str(exc)) from exc


def _ttl_expired(fetched_at: datetime, config: Defaults) -> bool:
    return _now() - fetched_at > timedelta(hours=config.CACHE_TTL_HOURS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_frame(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _write_frame(path: Path, data: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(data), handle, ensure_ascii=False, indent=2)


def _read_fetched_at(path: Path) -> datetime | None:
    payload = _read_json(path)
    if not payload:
        return None
    raw = payload.get("fetched_at")
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _write_meta(path: Path, fetched_at: datetime) -> None:
    _write_json(path, {"fetched_at": fetched_at.isoformat()})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return {
            "__kind__": "dataframe",
            "payload": json.loads(value.to_json(orient="split", date_format="iso")),
        }
    if isinstance(value, pd.Series):
        return {
            "__kind__": "series",
            "payload": json.loads(value.to_json(orient="split", date_format="iso")),
        }
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (list, tuple, dict)) else False:
        return None
    return value


def json_to_frames(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__kind__") == "dataframe":
        payload = value["payload"]
        frame = pd.DataFrame(data=payload["data"], columns=payload["columns"])
        frame.index = _maybe_datetime_index(payload["index"])
        return frame
    if isinstance(value, dict) and value.get("__kind__") == "series":
        payload = value["payload"]
        series = pd.Series(data=payload["data"], index=payload["index"])
        series.index = _maybe_datetime_index(series.index)
        return series
    if isinstance(value, dict):
        return {key: json_to_frames(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_to_frames(item) for item in value]
    return value


def _maybe_datetime_index(values: Any) -> Any:
    items = list(values)
    if not items:
        return values
    if not all(
        isinstance(item, str) and re.match(r"^\d{4}-\d{2}-\d{2}", item)
        for item in items
    ):
        return values
    try:
        parsed = pd.to_datetime(items)
    except Exception:
        return values
    return parsed
