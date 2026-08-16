# Nested causal parameter evaluation

> Snapshot: 2026-08-16. This is sensitivity evidence across 6 of 12 target metrics;
> it does not claim portfolio-wide parameter optimality.

## Evaluation contract

- Every historical forecast uses only information available before its target.
- Missing history is filled from the same prior seasonal position or last prior value;
  later observations are never used to fill earlier gaps.
- Each candidate is compared with seasonal naive on identical paired origins.
- Inner selection uses only origins strictly before the outer target.
- Config selection is company-local; fiscal keys are never ordered across companies.
- Primary loss is MAE within each metric. Cross-metric aggregation uses median paired
  relative MAE versus seasonal naive, so different reporting units remain comparable.
- The deployment recommendation uses completed history and is excluded from reported
  outer performance.

Protocol: trailing 12 inner origins, at least 6 paired inner origins, and the last 8
eligible outer rounds. Four pre-registered configurations are evaluated: `current`,
`responsive`, `diversified`, and `strict`.

## Nested outer results

The nested policy produced 46 genuinely unseen predictions over 24 company-local outer
rounds (8 per company). Aggregate relative MAE was **0.515**, equivalent to **48.5% skill** versus the paired
seasonal-naive baseline.

| Metric | Outer origins | Method MAE | Baseline MAE | Relative MAE | Skill |
|---|---:|---:|---:|---:|---:|
| ADI Adjusted diluted EPS | 8 | 0.262 | 0.616 | 0.425 | 57.5% |
| ADI Adjusted gross margin | 8 | 1.152 | 2.337 | 0.493 | 50.7% |
| ADI Revenue | 8 | 291.339 | 580.000 | 0.502 | 49.8% |
| DE Diluted EPS (GAAP) | 8 | 1.487 | 2.034 | 0.731 | 26.9% |
| DE Worldwide net sales and revenues | 6 | 1,827.657 | 3,469.167 | 0.527 | 47.3% |
| HD Net sales | 8 | 1,310.052 | 1,625.000 | 0.806 | 19.4% |

The company-local outer loops selected `current` 8 times, `responsive` 14 times and
`strict` 2 times. Using all completed history, deployment recommendations are
**HD=`current`**, **ADI=`responsive`**, and **DE=`responsive`**. These choices are
operational guidance, not part of the 48.5% outer performance estimate.

## Guarded forecast impact

A nested point is used only with at least three outer origins, positive outer skill,
no seasonal-naive fallback and positive deployment ensemble skill.

| Metric | Direct point | Guarded final point | Decision |
|---|---:|---:|---|
| HD Net sales | 46,886.00 | 46,239.91 | nested |
| ADI Revenue | 3,900.00 | 3,514.10 | nested |
| ADI Adjusted diluted EPS | 3.30 | 2.8621 | nested |
| ADI Adjusted gross margin | 74.00 | 71.6259 | nested |
| DE Worldwide net sales and revenues | 11,657.00 | 12,354.77 | nested |
| DE Diluted EPS (GAAP) | 4.88 | 4.9169 | nested |

HD adjusted EPS and comparable sales, all three Hays metrics, and DE Production &
Precision Ag operating profit remain on sourced direct forecasts because their current
histories do not satisfy the nested evidence gate.

## Reproduce

```bash
uv run --with-requirements agent/requirements.txt \
  python -m agent.parameter_evaluation \
  --markdown outputs/nested-parameter-evaluation.md \
  --json outputs/nested-parameter-evaluation.json

uv run --with-requirements agent/requirements.txt python -m agent.run
npm run check:forecasts
```

Runtime reports under `outputs/` are ignored; this file is the tracked review snapshot.
