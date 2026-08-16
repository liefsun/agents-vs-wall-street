# Build log

This log records competition-specific work created after the official build start.

## 2026-08-16 11:15 BST — Build started

- Starting point: organiser commit `b289674`.
- Team repository: `https://github.com/liefsun/agents-vs-wall-street`.
- No pre-built forecasting agent, challenge-specific code, prompts, research,
  forecasts, workflows or architecture explanation was imported.
- Allowed starting components: the organiser repository and its document-search
  helper, public libraries, and the team's normal unmodified coding harness.
- First implementation objective: establish a repeatable run contract for all four
  companies before adding retrieval, forecasting and workbook-writing stages.

## 2026-08-16 — Forecasting and causal evaluation implemented

- Added filing/guidance direct forecasts and workbook generation for all 12 metrics.
- Added causal gap filling, paired seasonal-naive comparisons and immutable
  `BacktestConfig` policies.
- Added nested inner selection and unseen outer evaluation with MAE-first reporting.
- Connected the recommended configuration through an explicit evidence gate; six
  metrics use nested forecasts and six retain direct fallbacks.
- Final verification: 19 tests pass and all four workbooks pass the organiser checker.
