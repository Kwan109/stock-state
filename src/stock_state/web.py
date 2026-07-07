from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import click

from stock_state.card import build_stock_state_card
from stock_state.config import DEFAULTS
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


if __name__ == "__main__":
    main()

