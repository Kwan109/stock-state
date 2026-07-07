from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import click

from stock_state.card import build_stock_state_card
from stock_state.config import DEFAULTS
from stock_state.cross_section import compute_cross_section
from stock_state.narrator.brief import generate_brief
from stock_state.providers.base import ProviderError
from stock_state.providers.yfinance_provider import YFinanceProvider


class StockStateRequestHandler(BaseHTTPRequestHandler):
    server_version = "stock-state-web/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html")
            return
        if parsed.path == "/api/card":
            self._send_card(parsed.query)
            return
        if parsed.path == "/api/brief":
            self._send_brief(parsed.query)
            return
        if parsed.path == "/api/watchlist":
            self._send_watchlist(parsed.query)
            return
        if parsed.path.startswith("/static/"):
            self._send_static(parsed.path.removeprefix("/static/"))
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_card(self, query: str) -> None:
        params = parse_qs(query)
        ticker = (params.get("ticker") or [""])[0].strip().upper()
        refresh = (params.get("refresh") or ["0"])[0] in {"1", "true", "yes"}
        if not ticker:
            self._send_json({"error": "ticker is required"}, status=400)
            return
        try:
            card = build_stock_state_card(
                ticker,
                YFinanceProvider(),
                config=DEFAULTS,
                refresh=refresh,
            )
        except ProviderError as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)
            return
        self._send_json({"card": card.model_dump(mode="json")})

    def _send_brief(self, query: str) -> None:
        params = parse_qs(query)
        raw = (params.get("tickers") or params.get("ticker") or [""])[0]
        tickers = _parse_tickers(raw)
        refresh = (params.get("refresh") or ["0"])[0] in {"1", "true", "yes"}
        if not tickers:
            self._send_json({"error": "ticker is required"}, status=400)
            return
        cards, failures = _load_cards(tickers, refresh=refresh)
        cross = compute_cross_section(cards, DEFAULTS)
        result = generate_brief(cards, cross_section=cross, refresh=refresh, config=DEFAULTS)
        self._send_json(
            {
                "brief": _brief_payload(result),
                "failures": failures,
            }
        )

    def _send_watchlist(self, query: str) -> None:
        params = parse_qs(query)
        raw = (params.get("tickers") or [""])[0]
        tickers = _parse_tickers(raw)
        refresh = (params.get("refresh") or ["0"])[0] in {"1", "true", "yes"}
        if not tickers:
            self._send_json({"error": "tickers are required"}, status=400)
            return
        cards, failures = _load_cards(tickers, refresh=refresh)
        cross = compute_cross_section(cards, DEFAULTS)
        result = generate_brief(cards, cross_section=cross, refresh=refresh, config=DEFAULTS)
        self._send_json(
            {
                "cards": {card.ticker: card.model_dump(mode="json") for card in cards},
                "cross_section": cross,
                "brief": _brief_payload(result),
                "failures": failures,
            }
        )

    def _send_static(self, name: str) -> None:
        if "/" in name or ".." in name:
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = (
                resources.files("stock_state")
                .joinpath("static")
                .joinpath(name)
                .read_bytes()
            )
        except FileNotFoundError:
            self._send_json({"error": "not found"}, status=404)
            return
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True, type=int)
def main(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), StockStateRequestHandler)
    url = f"http://{host}:{port}"
    click.echo(f"stock-state web UI running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("shutting down")
    finally:
        server.server_close()


def _parse_tickers(raw: str) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for item in re.split(r"[\s,]+", raw):
        ticker = item.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def _load_cards(tickers: list[str], *, refresh: bool) -> tuple[list[object], list[str]]:
    cards = []
    failures: list[str] = []
    provider = YFinanceProvider()
    for ticker in tickers:
        try:
            cards.append(
                build_stock_state_card(
                    ticker,
                    provider,
                    config=DEFAULTS,
                    refresh=refresh,
                )
            )
        except Exception as exc:
            failures.append(f"{ticker}: {exc}")
    return cards, failures


def _brief_payload(result: object) -> dict[str, object]:
    validation = getattr(result, "validation", None)
    return {
        "text": result.text,
        "display_text": result.display_text,
        "available": result.available,
        "from_cache": result.from_cache,
        "provider": result.provider,
        "model": result.model,
        "error": result.error,
        "validation": None
        if validation is None
        else {
            "passed": validation.passed,
            "violations": validation.violations,
        },
    }


if __name__ == "__main__":
    main()
