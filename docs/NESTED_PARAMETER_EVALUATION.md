# Nested causal parameter evaluation

> Snapshot: 2026-08-16. This is sensitivity evidence across 10 of 12 target metrics;
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

Protocols are pre-registered by reporting frequency. Quarterly series use trailing 12
inner origins, at least 6 paired inner origins, and 8 outer rounds. Hays H1/FY series
use season 2 with 6 inner origins, at least 3 paired inner origins, and 4 outer rounds.
Both evaluate `current`, `responsive`, `diversified`, and `strict`.

## Nested outer results

The nested policy produced 66 genuinely unseen predictions over 28 company-local outer
rounds. Aggregate relative MAE was **0.781**, equivalent to **21.9% skill** versus the
paired seasonal-naive baseline.

| Metric | Outer origins | Method MAE | Baseline MAE | Relative MAE | Skill |
|---|---:|---:|---:|---:|---:|
| ADI Adjusted diluted EPS | 8 | 0.262 | 0.616 | 0.425 | 57.5% |
| ADI Adjusted gross margin | 8 | 1.152 | 2.337 | 0.493 | 50.7% |
| ADI Revenue | 8 | 291.339 | 580.000 | 0.502 | 49.8% |
| DE Diluted EPS (GAAP) | 8 | 1.789 | 1.946 | 0.919 | 8.1% |
| DE Production & Precision Ag operating profit | 8 | 394.959 | 535.500 | 0.738 | 26.2% |
| DE Worldwide net sales and revenues | 6 | 1,870.063 | 2,575.333 | 0.726 | 27.4% |
| Hays Net fees | 4 | 113.050 | 113.050 | 1.000 | 0.0% |
| Hays Pre-exceptional basic EPS | 4 | 2.322 | 2.297 | 1.011 | -1.1% |
| Hays Pre-exceptional operating profit | 4 | 48.139 | 47.850 | 1.006 | -0.6% |
| HD Net sales | 8 | 1,843.163 | 2,237.500 | 0.824 | 17.6% |

Using all completed history, deployment recommendations are **HD=`strict`**,
**ADI=`responsive`**, **DE=`current`**, and **HAS=`current`**. These choices are
operational guidance, not part of the 21.9% outer performance estimate.

## Guarded forecast impact

A nested point is used only with at least three outer origins, positive outer skill,
no seasonal-naive fallback and positive deployment ensemble skill.

| Metric | Direct point | Guarded final point | Decision |
|---|---:|---:|---|
| HD Net sales | 46,886.00 | 45,885.91 | nested |
| ADI Revenue | 3,900.00 | 3,514.10 | nested |
| ADI Adjusted diluted EPS | 3.30 | 2.8621 | nested |
| ADI Adjusted gross margin | 74.00 | 71.6259 | nested |
| DE Worldwide net sales and revenues | 11,657.00 | 12,227.76 | nested |
| DE Diluted EPS (GAAP) | 4.88 | 5.4055 | nested |
| DE Production & Precision Ag operating profit | 1,154.00 | 592.88 | nested |

HD adjusted EPS and comparable sales remain direct because their exact histories are
too short. All three Hays metrics now have semiannual nested evidence but remain direct
because their outer skill is not positive and deployment falls back to seasonal naive.

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
