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

The judgement block also exposes attribution sequence diagnostics used by the
rules: `residual_5d_z`, `amplifier_days_20d`, `defiant_days_20d`, and
`market_5d_return`. This keeps the headline auditable instead of hiding the
sequence layer inside the engine.

Market-pressure relative accumulation is intentionally conservative: it can
upgrade the context to `constructive_watch`, but it cannot produce
`actionable_long` by itself. Capitulation flushes are also descriptive only and
remain `avoid_until_reclaim` until long-term trend repair.

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

The UI includes a verdict band, profile-aware panel ordering
(`momentum_leader`, `stable_compounder`, `pre_profit`, or `default`), and a
Debug / Explain drawer. Explain-layer metrics such as MFI, EV/S,
recommendation mean, target upside, and correlation uplift are kept out of the
main decision surface and shown in that drawer with key thresholds and NA
reasons.

## AI Narrator

The optional narrator layer turns the deterministic card or watchlist output
into a short daily briefing. It is a narrator only: it receives a whitelisted
digest of `judgement`, evidence, flags, contexts, and selected metrics. It does
not see raw price history and cannot replace the rule-based stance.

Install optional SDKs:

```bash
python3 -m pip install -e ".[narrator]"
```

Set one API key:

```bash
export ANTHROPIC_API_KEY=...
# or
export OPENAI_API_KEY=...
```

Usage:

```bash
stock-state AAPL --brief
stock-state AAPL --brief-only
stock-state --watchlist ws.yaml --table --brief
stock-state --watchlist ws.yaml --brief-only
stock-state AAPL --brief --narrator-provider openai
```

The default provider is Anthropic with `claude-sonnet-4-6`. OpenAI is available
as a fallback provider. Without a key or when the API fails, the card/table still
renders and the briefing shows a short unavailable message. Briefings are cached
under `data_cache/briefings/` with the exact digest and meta audit files.

Each single-card or watchlist run appends an idempotent row to
`data_cache/judgement_log.parquet` with ticker, date, stance, flags, confidence,
and judgement version. This file is intentionally ignored by git.

Each AI briefing writes a paired `.md`, `.digest.json`, and `.meta.json` under
`data_cache/briefings/`. These files are also ignored by git.

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
