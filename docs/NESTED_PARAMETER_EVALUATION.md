# Nested causal parameter evaluation

> Snapshot: 2026-08-16, after the research agent replaced regular expressions as the reader.
> This is sensitivity evidence across all 12 target metrics; it does not claim
> portfolio-wide parameter optimality.

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

## Where the history comes from

The series are read by `agent/research.py`, an LLM working to a per-metric analyst brief,
and cross-checked against the deterministic parsers in `agent/history.py`. An observation
is admitted only if its supporting quote appears verbatim in the source document and
contains the reported number. Coverage is the union of both readers; a disagreement beyond
2% is recorded and resolved in favour of the reading that can show its evidence.

| Metric | Parser | Agent + parser |
|---|---:|---:|
| HD Comparable sales, total company | 13 | 39 |
| HD Net sales | 40 | 46 |
| HD Adjusted diluted EPS | 7 | 9 |
| ADI Revenue | 42 | 46 |
| ADI Adjusted gross margin | 41 | 46 |
| ADI Adjusted diluted EPS | 31 | 32 |
| DE Worldwide net sales and revenues | 42 | 46 |
| DE Diluted EPS (GAAP) | 33 | 46 |
| DE Production & Precision Ag operating profit | 22 | 23 |

## Nested outer results

The nested policy produced 83 genuinely unseen predictions over 28 company-local outer
rounds. Aggregate relative MAE was **0.783**, equivalent to **21.7% skill** versus the
paired seasonal-naive baseline.

| Metric | Outer origins | Method MAE | Baseline MAE | Relative MAE | Skill |
|---|---:|---:|---:|---:|---:|
| ADI Revenue | 8 | 214.549 | 566.625 | 0.379 | 62.1% |
| ADI Adjusted diluted EPS | 8 | 0.274 | 0.616 | 0.444 | 55.6% |
| ADI Adjusted gross margin | 8 | 1.077 | 2.337 | 0.461 | 53.9% |
| HD Comparable sales, total company | 8 | 1.320 | 2.125 | 0.621 | 37.9% |
| HD Net sales | 8 | 1,673.774 | 2,226.000 | 0.752 | 24.8% |
| DE Production & Precision Ag operating profit | 8 | 404.724 | 535.500 | 0.756 | 24.4% |
| DE Worldwide net sales and revenues | 8 | 1,739.859 | 2,145.125 | 0.811 | 18.9% |
| DE Diluted EPS (GAAP) | 8 | 1.909 | 1.946 | 0.981 | 1.9% |
| HD Adjusted diluted EPS | 7 | 0.444 | 0.444 | 1.000 | 0.0% |
| Hays Net fees | 4 | 113.050 | 113.050 | 1.000 | 0.0% |
| Hays Pre-exceptional operating profit | 4 | 48.272 | 48.000 | 1.006 | -0.6% |
| Hays Pre-exceptional basic EPS | 4 | 2.325 | 2.297 | 1.012 | -1.2% |

Using all completed history, deployment recommendations are **ADI=`responsive`**,
**DE=`strict`**, **HD=`strict`** and **HAS=`current`**. These choices are operational
guidance, not part of the 21.7% outer performance estimate.

### Comparison with the previous reader

Before the research agent, only 10 of the 12 metrics could be scored at all: 66 predictions
at 0.781 relative MAE, or 21.9% skill. The headline is essentially unchanged, but it is now
measured over a fifth more evidence with no metric excluded. Two movements are worth naming:

- **ADI Revenue rose from 49.8% to 62.1% skill.** The parser had been matching
  "expected revenue of $8.2 billion on a pro forma basis" from the Maxim merger
  announcement and recording it as Q3 2020 revenue. That quarter's 10-Q states
  `Revenue $ 1,456,136` in a thousands table.
- **HD Comparable sales became scoreable** at 37.9% skill, on 39 observations rather
  than 13, and now passes the production gate.

## Guarded forecast impact

A nested point is used only with at least three outer origins, positive outer skill,
no seasonal-naive fallback and positive deployment ensemble skill. Eight of twelve
metrics pass; four keep the sourced direct forecast.

| Metric | Decision | Why |
|---|---|---|
| ADI Revenue · Adjusted diluted EPS · Adjusted gross margin | nested | 53.9–62.1% outer skill |
| HD Net sales · Comparable sales | nested | 24.8% and 37.9% outer skill |
| DE Worldwide net sales · Diluted EPS (GAAP) · PPA operating profit | nested | 1.9–24.4% outer skill |
| HD Adjusted diluted EPS | direct | scoreable at last, but 0.0% outer skill |
| Hays Net fees · Pre-exceptional operating profit · Pre-exceptional basic EPS | direct | outer skill zero or negative; deployment falls back to seasonal naive |

## Reproduce

The committed answers under `agent/cache/research/` make this offline and key-free.

```bash
uv run --with-requirements agent/requirements.txt \
  python -m agent.parameter_evaluation \
  --markdown outputs/nested-parameter-evaluation.md \
  --json outputs/nested-parameter-evaluation.json

uv run --with-requirements agent/requirements.txt python -m agent.run
npm run check:forecasts
```

Runtime reports under `outputs/` are ignored; this file is the tracked review snapshot.
