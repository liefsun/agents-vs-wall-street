# Nested causal parameter evaluation

> Status: sensitivity evidence only across 3 structured series; this report does not claim portfolio-wide parameter optimality.

## Evaluation contract

- Inner selection uses only common paired origins strictly before each outer target.
- One configuration is shared across all available metrics at an outer target.
- Primary loss is MAE within a metric and median relative MAE versus seasonal-naive across metrics.
- Deployment recommendation uses only completed history and is excluded from outer performance.
- Protocol: trailing 12 inner origins (minimum 6); at least 3 series; last 8 eligible outer rounds.

## Candidate configurations

| Config | Window | Min train | Min origins | Cap | Baseline floor | Gate |
|---|---:|---:|---:|---:|---:|---:|
| current | 16 | 8 | 6 | 0.60 | 0.20 | 5% |
| responsive | 8 | 8 | 4 | 0.60 | 0.20 | 5% |
| diversified | 12 | 8 | 6 | 0.50 | 0.25 | 5% |
| strict | 16 | 12 | 8 | 0.50 | 0.20 | 10% |

## Nested outer evaluation

Outer rounds: **8** · predictions: **24** · aggregate relative MAE: **0.493** · skill: **50.7%**

| Metric | Origins | Method MAE | Baseline MAE | Relative MAE | Skill | Wins |
|---|---:|---:|---:|---:|---:|---:|
| ADI · Adjusted diluted EPS (USD / share) | 8 | 0.262 | 0.616 | 0.425 | 57.5% | 8/8 |
| ADI · Adjusted gross margin (%) | 8 | 1.152 | 2.337 | 0.493 | 50.7% | 7/8 |
| ADI · Revenue (USDm) | 8 | 291.339 | 580.000 | 0.502 | 49.8% | 8/8 |

### Outer decisions

| Target | Selected config | Inner relative MAE | Last inner target |
|---|---|---:|---|
| Q3 2024 | current | 0.683 | Q2 2024 |
| Q4 2024 | responsive | 0.500 | Q3 2024 |
| Q1 2025 | responsive | 0.480 | Q4 2024 |
| Q2 2025 | responsive | 0.442 | Q1 2025 |
| Q3 2025 | responsive | 0.425 | Q2 2025 |
| Q4 2025 | responsive | 0.430 | Q3 2025 |
| Q1 2026 | responsive | 0.421 | Q4 2025 |
| Q2 2026 | responsive | 0.448 | Q1 2026 |

## Fixed-config sensitivity on the same outer targets

| Config | Predictions | Aggregate relative MAE | Skill |
|---|---:|---:|---:|
| current | 24 | 0.497 | 50.3% |
| responsive | 24 | 0.469 | 53.1% |
| diversified | 24 | 0.497 | 50.3% |
| strict | 24 | 0.469 | 53.1% |

## Deployment recommendation

Use **responsive** for the next forecast. Its latest-window relative MAE is **0.497**. This choice is operational guidance, not part of the outer performance estimate.
