from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console

from stock_state.card import (
    build_card_from_inputs,
    build_history_rows,
    build_stock_state_card,
    load_inputs,
)
from stock_state.cache import log_judgement_event
from stock_state.config import DEFAULTS
from stock_state.cross_section import compute_cross_section
from stock_state.providers.base import ProviderError, ProviderNotAvailableError
from stock_state.providers.ibkr_provider import IBKRProvider
from stock_state.providers.yfinance_provider import YFinanceProvider
from stock_state.render import (
    render_card,
    render_explain,
    render_history,
    render_watchlist_table,
)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("ticker", required=False)
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON.")
@click.option("--watchlist", type=click.Path(exists=True, dir_okay=False), help="YAML watchlist.")
@click.option("--table", "as_table", is_flag=True, help="Render watchlist comparison table.")
@click.option("--history", type=int, help="Render recent N-day state timeline.")
@click.option("--explain", type=click.Choice(["volume_price", "crowding", "valuation", "relative", "attribution", "fundamentals", "analyst", "judgement"]), help="Explain a family.")
@click.option("--refresh", is_flag=True, help="Force cache refresh.")
@click.option("--offline", is_flag=True, help="Read cache only.")
@click.option("--provider", type=click.Choice(["yfinance", "ibkr"]), default="yfinance", show_default=True)
def main(
    ticker: str | None,
    as_json: bool,
    watchlist: str | None,
    as_table: bool,
    history: int | None,
    explain: str | None,
    refresh: bool,
    offline: bool,
    provider: str,
) -> None:
    console = Console()
    data_provider = _provider(provider)
    if watchlist:
        _run_watchlist(
            Path(watchlist),
            data_provider,
            as_json=as_json,
            as_table=as_table,
            refresh=refresh,
            offline=offline,
            console=console,
        )
        return
    if not ticker:
        raise click.UsageError("ticker is required unless --watchlist is provided")
    try:
        if history:
            inputs = load_inputs(
                ticker,
                data_provider,
                config=DEFAULTS,
                refresh=refresh,
                offline=offline,
            )
            rows = build_history_rows(inputs, days=history, config=DEFAULTS)
            if as_json:
                click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                console.print(render_history(rows))
            return
        card = build_stock_state_card(
            ticker,
            data_provider,
            config=DEFAULTS,
            refresh=refresh,
            offline=offline,
        )
        if as_json:
            click.echo(card.model_dump_json(indent=2))
        elif explain:
            console.print(render_explain(card, explain))
        else:
            console.print(render_card(card))
    except ProviderNotAvailableError as exc:
        raise click.ClickException(str(exc)) from exc
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


def _run_watchlist(
    path: Path,
    data_provider: Any,
    *,
    as_json: bool,
    as_table: bool,
    refresh: bool,
    offline: bool,
    console: Console,
) -> None:
    tickers = _read_watchlist(path)
    cards = []
    failures: list[str] = []
    for ticker in tickers:
        try:
            inputs = load_inputs(
                ticker,
                data_provider,
                config=DEFAULTS,
                refresh=refresh,
                offline=offline,
            )
            card = build_card_from_inputs(inputs, config=DEFAULTS)
            try:
                log_judgement_event(".", card)
            except Exception:
                pass
            cards.append(card)
        except Exception as exc:
            failures.append(f"{ticker}: {exc}")
    cross = compute_cross_section(cards, DEFAULTS)
    if as_json:
        payload = {
            "cards": {card.ticker: card.model_dump(mode="json") for card in cards},
            "cross_section": cross,
            "failures": failures,
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    elif as_table:
        console.print(render_watchlist_table(cards, cross))
        _print_failures(console, failures)
    else:
        for card in cards:
            console.print(render_card(card))
        _print_failures(console, failures)
    if failures and not cards:
        raise click.ClickException("; ".join(failures))


def _read_watchlist(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or []
    if isinstance(payload, list):
        tickers = payload
    elif isinstance(payload, dict):
        tickers = payload.get("tickers") or payload.get("symbols") or []
    else:
        tickers = []
    return [str(ticker).upper().strip() for ticker in tickers if str(ticker).strip()]


def _provider(name: str):
    if name == "ibkr":
        return IBKRProvider()
    return YFinanceProvider()


def _print_failures(console: Console, failures: list[str]) -> None:
    if not failures:
        return
    console.print("失败清单:", style="red")
    for failure in failures:
        console.print(f"- {failure}", style="red")


if __name__ == "__main__":
    main()
