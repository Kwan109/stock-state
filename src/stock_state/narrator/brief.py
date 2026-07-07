from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

from stock_state.card import StockStateCard
from stock_state.config import DEFAULTS, Defaults
from stock_state.narrator.client import NarratorClient, NarratorUnavailable, make_client
from stock_state.narrator.digest import build_digest
from stock_state.narrator.validator import ValidationResult, validate_brief


@dataclass(frozen=True)
class BriefResult:
    text: str
    available: bool
    from_cache: bool
    validation: ValidationResult | None
    digest: dict[str, Any] | None
    path: Path | None
    provider: str | None = None
    model: str | None = None
    error: str | None = None

    @property
    def display_text(self) -> str:
        if self.validation and not self.validation.passed:
            details = "; ".join(self.validation.violations)
            return f"> 叙述未通过忠实性校验：{details}\n\n{self.text}"
        return self.text


def generate_brief(
    cards: list[StockStateCard],
    *,
    cross_section: dict[str, dict[str, object]] | None = None,
    root: Path | str = ".",
    refresh: bool = False,
    client: NarratorClient | None = None,
    provider: str | None = None,
    model: str | None = None,
    config: Defaults = DEFAULTS,
) -> BriefResult:
    if not config.NARRATOR_ENABLED:
        return _unavailable("narrator disabled")
    if not cards:
        return _unavailable("no cards available for briefing")
    digest = build_digest(cards, cross_section, config=config)
    base = _briefing_dir(root)
    stem = _cache_stem(cards)
    brief_path = base / f"{stem}.md"
    digest_path = base / f"{stem}.digest.json"
    meta_path = base / f"{stem}.meta.json"
    if brief_path.exists() and digest_path.exists() and not refresh:
        text = brief_path.read_text(encoding="utf-8")
        cached_digest = json.loads(digest_path.read_text(encoding="utf-8"))
        validation = validate_brief(text, cached_digest)
        return BriefResult(
            text=text,
            available=True,
            from_cache=True,
            validation=validation,
            digest=cached_digest,
            path=brief_path,
            provider=_meta_value(meta_path, "provider"),
            model=_meta_value(meta_path, "model"),
        )
    try:
        prompt = _load_prompt()
        selected_client = client or make_client(provider=provider, model=model, config=config)
    except NarratorUnavailable as exc:
        return _unavailable(f"晨报不可用: {exc}", digest=digest, path=brief_path)
    started = time.perf_counter()
    try:
        text = selected_client.generate(prompt=prompt, digest=digest)
    except NarratorUnavailable as exc:
        _write_meta(meta_path, digest, None, selected_client, 0.0, False, [str(exc)])
        return _unavailable(f"晨报不可用: {exc}", digest=digest, path=brief_path)
    except Exception as exc:
        elapsed = time.perf_counter() - started
        _write_meta(meta_path, digest, None, selected_client, elapsed, False, [str(exc)])
        return _unavailable(f"晨报不可用: {type(exc).__name__}: {exc}", digest=digest, path=brief_path)
    elapsed = time.perf_counter() - started
    text = text.strip()
    validation = validate_brief(text, digest)
    brief_path.write_text(text, encoding="utf-8")
    digest_path.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_meta(
        meta_path,
        digest,
        text,
        selected_client,
        elapsed,
        validation.passed,
        validation.violations,
    )
    return BriefResult(
        text=text,
        available=True,
        from_cache=False,
        validation=validation,
        digest=digest,
        path=brief_path,
        provider=selected_client.provider,
        model=selected_client.model,
    )


def _unavailable(
    message: str,
    *,
    digest: dict[str, Any] | None = None,
    path: Path | None = None,
) -> BriefResult:
    return BriefResult(
        text=message,
        available=False,
        from_cache=False,
        validation=None,
        digest=digest,
        path=path,
        error=message,
    )


def _briefing_dir(root: Path | str) -> Path:
    path = Path(root) / "data_cache" / "briefings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_stem(cards: list[StockStateCard]) -> str:
    date = str(cards[0].as_of)
    tickers = ",".join(sorted(card.ticker for card in cards))
    digest = sha1(tickers.encode("utf-8")).hexdigest()[:8]
    return f"{date}_{digest}"


def _load_prompt() -> str:
    candidates = [
        Path.cwd() / "prompts" / "briefing_v1.md",
        Path(__file__).resolve().parents[3] / "prompts" / "briefing_v1.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise NarratorUnavailable("prompt file prompts/briefing_v1.md not found")


def _write_meta(
    path: Path,
    digest: dict[str, Any],
    raw_response: str | None,
    client: NarratorClient,
    elapsed: float,
    validation_passed: bool,
    violations: list[str],
) -> None:
    meta = {
        "provider": client.provider,
        "model": client.model,
        "elapsed_seconds": round(elapsed, 3),
        "validation_passed": validation_passed,
        "violations": violations,
        "digest": digest,
        "raw_response": raw_response,
    }
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _meta_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get(key) or "")
    except Exception:
        return None
