# stock-state

`stock-state` is a standalone Python CLI that builds a daily stock state card for
US equities. It answers four practical questions:

- Who is buying or selling, and how urgent is the tape?
- How crowded is the stock versus its own history?
- Is valuation expensive or cheap versus the stock's own history?
- Is today's move market-driven, sector-driven, or idiosyncratic?
- What rule-based technical stance best describes the current setup?

The default provider is `yfinance`, with file-based parquet/json caching under
`./data_cache`. `ibkr` is exposed as a reserved provider port and returns a clear
not-implemented message in v1.

## Judgement Layer

Every `StockStateCard` includes a deterministic v2 judgement block. It converts
the raw families into a named setup stance, evidence lines, risk flags, entry
context, exit context, and confidence:

- `actionable_long`
- `wait_for_pullback`
- `constructive_watch`
- `extended_do_not_chase`
- `distribution_risk`
- `breakdown_risk`
- `avoid_until_reclaim`
- `data_insufficient`
- `no_clear_setup`

These are rule-based technical labels, not trading instructions. The caveat is
included in JSON and UI: confidence measures evidence coverage/consistency, not
forward return probability.

## Install

```bash
python3 -m pip install -e .
```

For tests:

```bash
PYTHONPATH=src pytest -m "not network"
```

Network smoke tests require `yfinance` and external access:

```bash
PYTHONPATH=src pytest -m network
```

## Usage

```bash
stock-state NVDA
stock-state NVDA --json
stock-state NVDA --history 30
stock-state NVDA --explain crowding
stock-state NVDA --refresh
stock-state NVDA --offline
stock-state NVDA --provider ibkr
stock-state --watchlist ws.yaml --json
stock-state --watchlist ws.yaml --table
stock-state-web --host 127.0.0.1 --port 8765
```

Open the local UI at `http://127.0.0.1:8765`. It uses the same card builder as
the CLI and exposes `GET /api/card?ticker=AAPL`.

Each single-card or watchlist run appends an idempotent row to
`data_cache/judgement_log.parquet` with ticker, date, stance, flags, confidence,
and judgement version. This file is intentionally ignored by git.

Watchlist YAML can be either:

```yaml
- NVDA
- KO
- RKLB
```

or:

```yaml
tickers:
  - NVDA
  - KO
  - RKLB
```

## Data Caveats

`yfinance` is an unofficial Yahoo Finance wrapper and should be treated as
research/EOD-or-delayed data, not a production-grade market data entitlement.
All missing fields render as `N/A(reason)` and remain present in JSON.

Valuation percentiles are relative to the stock's own history, not a cross-stock
comparison. Shares outstanding and EV inputs use current values as an
approximation.

Watchlist cross-section ranks are attached outside each `StockStateCard`; the
same ticker/date card body is identical whether generated alone or inside a
watchlist.
