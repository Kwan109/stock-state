# stock-state implementation spec summary

This repository implements the merged behavior of:

- `stock_state_codex_build_spec.md` v1.0
- `stock_state_spec_addendum_v1.1.md`

The implementation keeps the original contracts:

- Standalone Python package with `stock-state = stock_state.cli:main`.
- `DataProvider` protocol, implemented by `YFinanceProvider`; `IBKRProvider`
  is a reserved stub that raises a friendly not-implemented error.
- Pure indicator functions without TA libraries.
- Centralized thresholds/windows in `stock_state.config.Defaults`.
- Missing values are represented as `NAField(value=None, reason=...)`.
- Card JSON follows the Pydantic `StockStateCard` model.
- Watchlist cross-section ranks are computed after cards are complete and do
  not mutate card bodies.

The original detailed build instructions remain the source of truth for formula
definitions and acceptance criteria.

