# stock-state implementation spec summary

This repository implements the merged behavior of:

- `stock_state_codex_build_spec.md` v1.0
- `stock_state_spec_addendum_v1.1.md`
- `stock_state_v2_judgement_review.md` v2 judgement layer

The implementation keeps the original contracts:

- Standalone Python package with `stock-state = stock_state.cli:main`.
- `DataProvider` protocol, implemented by `YFinanceProvider`; `IBKRProvider`
  is a reserved stub that raises a friendly not-implemented error.
- Pure indicator functions without TA libraries.
- Centralized thresholds/windows in `stock_state.config.Defaults`.
- Missing values are represented as `NAField(value=None, reason=...)`.
- Card JSON follows the Pydantic `StockStateCard` model.
- Card JSON includes `judgement`, a deterministic rule-based technical
  interpretation block with stance, evidence, risk flags, entry/exit context,
  and confidence.
- Judgement JSON includes profile template and attribution sequence diagnostics
  (`residual_5d_z`, `amplifier_days_20d`, `defiant_days_20d`,
  `market_5d_return`) so sequence-based rulings are auditable.
- The UI separates decision-surface metrics from explain/debug metrics. MFI,
  EV/S, recommendation mean, target upside, and correlation uplift are shown in
  the Debug / Explain drawer rather than driving the headline.
- Relative accumulation during market pressure cannot produce
  `actionable_long`; capitulation flushes remain `avoid_until_reclaim` until
  trend repair.
- Accepted v2.1 deviations: capitulation handling is evaluated before
  `breakdown_risk` because its definition already requires a deep/high-volume
  flush; earnings-window actionable setups are conservatively downgraded to
  `constructive_watch` while the overlay still renders the event wrapper.
- Optional narrator-v1 layer summarizes deterministic card/watchlist outputs
  from a whitelisted digest only. It never reads raw price series, never changes
  stance, and is guarded by ticker/numeric/stance/directive/caveat validation.
  Anthropic (`claude-sonnet-4-6`) is the default provider; OpenAI is available
  as a provider override. API keys are read only from environment variables.
- Narrator failures are non-blocking. Briefs are cached with paired digest and
  meta audit files under ignored local cache.
- Watchlist cross-section ranks are computed after cards are complete and do
  not mutate card bodies.

The judgement layer is not a Buy/Sell recommender. Its caveat is part of the
model: confidence measures evidence coverage/consistency, not forward return
probability. Judgement logs are written to ignored local cache for future
forward-return validation.

The original detailed build instructions remain the source of truth for formula
definitions and acceptance criteria.
