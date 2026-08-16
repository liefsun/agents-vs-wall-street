# Clear-run evidence log

_A timestamped record of what the final system did on this run — every figure, its source and any fallback or retry — with API keys and other secrets removed._

## Run
- generated: `2026-08-16T17:58:46+01:00`
- started: `2026-08-16T17:58:33+01:00` · finished: `2026-08-16T17:58:46+01:00` · duration: 13.0s
- final command: `uv run --with-requirements agent/requirements.txt python -m agent.run`
- final commit: `6787ba6793` (branch `main`)
- methodology: **guarded nested selection** — the Methodology 1 causal ensemble is promoted only where it beats seasonal-naive on origins it never saw; otherwise the sourced direct forecast (guidance / seasonal anchor / accounting bridge) is kept
- series source: research agent (verbatim-quote gated) replaying committed answers in `agent/cache/research/` + deterministic parser gap-fill — reproduces offline byte-identical, no API key required
- environment: Python 3.11.15 on Windows · no network calls · OPENAI_API_KEY absent (not required)
- human input during the run: **none** (headless); a person only checks the four files and uploads them to OpenStocks

## HD · Home Depot — FY2026Q2
_processed at 2026-08-16T17:58:41+01:00_

| metric | forecast | units | source | outer skill | origins | direct baseline | band |
|---|---|---|---|---|---|---|---|
| Net sales | 4.589e+04 | USDm | nested | +0.25 | 8 | 4.689e+04 | 4.439e+04–4.74e+04 |
| Adjusted diluted EPS | 4.51 | USD / share | direct | — | 0 | 4.51 | 4.39–4.63 |
| Comparable sales, total company | 0.8437 | % | nested | +0.38 | 8 | 0.84 | -1.678–3.365 |

- **Net sales** — nested ensemble promoted (strict config) — outer skill +0.25 on 8 unseen origins. Basis: nested causal ensemble (strict config); outer skill 24.9% across 8 unseen origins; direct cross-check 46886.0 _[M2 checked: analogue skill -0.00 on 24 origins — M2 skill -0.00 below the 0.15 meaningful-skill bar]_
- **Adjusted diluted EPS** — guarded fallback → direct: no nested outer evidence; no deployment forecast. Basis: PY Q2 4.68 × (1+-3.7% latest-YoY)
- **Comparable sales, total company** — nested ensemble promoted (strict config) — outer skill +0.38 on 8 unseen origins. Basis: nested causal ensemble (strict config); outer skill 37.9% across 8 unseen origins; direct cross-check 0.84 _[M2 checked: analogue skill +0.30 on 22 origins — M2 skill +0.30 does not beat guarded-nested M1 +0.38 by ≥5%]_

**Extraction provenance** — research agent → point-in-time series (offline cache replay):
- **Net sales**: 51 documents read · 48 admitted · 3 rejected (agent found no figure on the requested basis ×3) → 46 PIT observations (46 research-read, 0 parser-filled)
    - e.g. FY 2014 = 1.916e+04 — "| NET SALES | $ 19,162 | $ 17,696 | 8.3 | $ 83,176 | $ 78,812 | 5.5 | % |" (2015-02-24__hd-us-20150224-q4-8k__437618.md)
- **Adjusted diluted EPS**: 49 documents read · 10 admitted · 39 rejected (agent found no figure on the requested basis ×39) → 8 PIT observations (8 research-read, 0 parser-filled)
    - e.g. Q2 2024 = 4.67 — "Adjusted diluted earnings per share for the second quarter of fiscal 2024 were $4.67, compared with adjusted diluted earnings per " (2024-08-13__hd-us-20240813-q2-8k__101849.md)
- **Comparable sales, total company**: 46 documents read · 33 admitted · 13 rejected (value 31.0 outside plausible range [-30.0, 30.0] ×1, reported value does not appear in its own supporting ×9, agent found no figure on the requested basis ×3) → 39 PIT observations (31 research-read, 8 parser-filled)
    - e.g. Q1 2016 = 6.5 — "Comparable store sales for the first quarter of fiscal 2016 were positive 6.5 percent, and comp sales for U.S. stores were positiv" (2016-05-17__hd-us-20160517-q1-8k__437610.md)
- → workbook written: `submission\HD-FY2026Q2.xlsx`

## ADI · Analog Devices — FY2026Q3
_processed at 2026-08-16T17:58:42+01:00_

| metric | forecast | units | source | outer skill | origins | direct baseline | band |
|---|---|---|---|---|---|---|---|
| Revenue | 3653 | USDm | nested | +0.62 | 8 | 3900 | 3288–3717 |
| Adjusted diluted EPS | 3.06 | USD / share | nested | +0.56 | 8 | 3.3 | 2.611–3.124 |
| Adjusted gross margin | 71.56 | % | nested | +0.54 | 8 | 74 | 70.51–72.61 |

- **Revenue** — nested ensemble promoted (responsive config) — outer skill +0.62 on 8 unseen origins. Basis: nested causal ensemble (responsive config); outer skill 62.1% across 8 unseen origins; direct cross-check 3900.0 _[M2 checked: analogue skill +0.55 on 24 origins — M2 skill +0.55 does not beat guarded-nested M1 +0.62 by ≥5%]_
- **Adjusted diluted EPS** — nested ensemble promoted (responsive config) — outer skill +0.56 on 8 unseen origins. Basis: nested causal ensemble (responsive config); outer skill 55.6% across 8 unseen origins; direct cross-check 3.3 _[M2 checked: analogue skill +0.41 on 24 origins — M2 skill +0.41 does not beat guarded-nested M1 +0.56 by ≥5%]_
- **Adjusted gross margin** — nested ensemble promoted (responsive config) — outer skill +0.54 on 8 unseen origins. Basis: nested causal ensemble (responsive config); outer skill 53.9% across 8 unseen origins; direct cross-check 74.0 _[M2 checked: analogue skill +0.39 on 24 origins — M2 skill +0.39 does not beat guarded-nested M1 +0.54 by ≥5%]_

**Reconciliation guard** — guidance blends + anchorless flags (deterministic accuracy pass):
- **Revenue**: blended toward issued guidance 3900 — 3502 → **3653** (was 10% off; model weight 0.62 = bounded outer skill)
- **Adjusted diluted EPS**: blended toward issued guidance 3.3 — 2.867 → **3.06** (was 13% off; model weight 0.56 = bounded outer skill)

**Extraction provenance** — research agent → point-in-time series (offline cache replay):
- **Revenue**: 51 documents read · 48 admitted · 3 rejected (agent found no figure on the requested basis ×2, value 13.6 outside plausible range [200.0, 20000.0] ×1) → 46 PIT observations (46 research-read, 0 parser-filled)
    - ⚑ agent overrode parser at FY 2017: agent 1540 vs parser 1440 (gap 6%) — kept the quote-corroborated value
    - ⚑ agent overrode parser at Q1 2018: agent 1520 vs parser 1430 (gap 6%) — kept the quote-corroborated value
    - ⚑ agent overrode parser at Q2 2018: agent 1513 vs parser 1470 (gap 3%) — kept the quote-corroborated value
    - ⚑ agent overrode parser at Q3 2020: agent 1456 vs parser 8200 (gap 82%) — kept the quote-corroborated value
    - ⚑ agent overrode parser at FY 2021: agent 2340 vs parser 1560 (gap 33%) — kept the quote-corroborated value
    - e.g. Q1 2015 = 772 — "Revenue totaled $772 million, down 5% sequentially, and up 23% year-over-year" (2015-02-17__adi-us-20150217-q1-8k__486332.md)
- **Adjusted diluted EPS**: 33 documents read · 32 admitted · 1 rejected (agent found no figure on the requested basis ×1) → 32 PIT observations (30 research-read, 2 parser-filled)
    - ⚑ agent overrode parser at FY 2021: agent 1.73 vs parser 1.44 (gap 17%) — kept the quote-corroborated value
    - e.g. Q1 2019 = 1.33 — "| Adjusted diluted earnings per share | $ 1.33 | $ 1.49 | (11)% |" (2019-02-20__adi-us-20190220-q1-8k__487684.md)
- **Adjusted gross margin**: 48 documents read · 48 admitted · 0 rejected → 46 PIT observations (46 research-read, 0 parser-filled)
    - e.g. Q1 2015 = 65.6 — "GAAP gross margin of 65.2% of revenue; Non-GAAP gross margin of 65.6% of revenue" (2015-02-17__adi-us-20150217-q1-8k__486332.md)
- → workbook written: `submission\ADI-FY2026Q3.xlsx`

## HAS · Hays plc — FY2026
_processed at 2026-08-16T17:58:45+01:00_

| metric | forecast | units | source | outer skill | origins | direct baseline | band |
|---|---|---|---|---|---|---|---|
| Net fees | 924 | GBPm | direct | +0.00 | 4 | 924 | 896–951 |
| Pre-exceptional basic EPS | 2.05 | GBp | direct | -0.01 | 4 | 2.05 | 1.59–2.5 |
| Pre-exceptional operating profit | 45.5 | GBPm | direct | -0.01 | 4 | 45.5 | 37–46 |

- **Net fees** — guarded fallback → direct: outer skill is not positive; deployment forecast fell back to seasonal naive. Basis: FY2025 net fees £972m × (1+-5% reported YoY) _[M2 checked: analogue skill -0.19 on 12 origins — M2 skill -0.19 below the 0.15 meaningful-skill bar]_
- **Pre-exceptional basic EPS** — guarded fallback → direct: outer skill is not positive; deployment forecast fell back to seasonal naive. Basis: bridge: operating profit × approx after-tax/share ratio (pence) — coarse, refine with shares/tax _[M2 checked: analogue skill +0.07 on 12 origins — M2 skill +0.07 below the 0.15 meaningful-skill bar]_
- **Pre-exceptional operating profit** — guarded fallback → direct: outer skill is not positive; deployment forecast fell back to seasonal naive. Basis: stated top of £37–46m; consensus £Nonem → ~£45.5m _[M2 checked: analogue skill -0.02 on 12 origins — M2 skill -0.02 below the 0.15 meaningful-skill bar]_

**Extraction provenance** — research agent → point-in-time series (offline cache replay):
- **Net fees**: 58 documents read · 20 admitted · 38 rejected (agent found no figure on the requested basis ×38) → 19 PIT observations (15 research-read, 4 parser-filled)
    - e.g. H1 2019 = 568 — "| Net fees (1) | 568.0 | 525.8 | 8% | 9% |" (2019-02-21__has-ln-20190221-h1-8k__545552.md)
- **Pre-exceptional basic EPS**: 26 documents read · 17 admitted · 9 rejected (agent found no figure on the requested basis ×9) → 19 PIT observations (12 research-read, 7 parser-filled)
    - e.g. FY 2019 = 11.92 — "Basic earnings per share (before exceptional items) | 11.92p | 11.44p | 4% | |" (2019-08-29__has-ln-20190829-h2-8k-2__671212.md)
- **Pre-exceptional operating profit**: 55 documents read · 25 admitted · 30 rejected (reported value does not appear in its own supporting ×1, agent found no figure on the requested basis ×28, quote does not appear verbatim in the source documen ×1) → 19 PIT observations (18 research-read, 1 parser-filled)
    - e.g. FY 2015 = 164.1 — "OPERATING PROFIT (1) (2014: £140.3m) £164.1m" (2015-09-18__has-ln-20150918-h2-8k__671208.md)
- → workbook written: `submission\HAS-FY2026.xlsx`

## DE · Deere & Company — FY2026Q3
_processed at 2026-08-16T17:58:46+01:00_

| metric | forecast | units | source | outer skill | origins | direct baseline | band |
|---|---|---|---|---|---|---|---|
| Worldwide net sales and revenues | 1.238e+04 | USDm | nested | +0.27 | 8 | 1.166e+04 | 1.07e+04–1.406e+04 |
| Diluted EPS (GAAP) | 5.203 | USD / share | nested | +0.06 | 8 | 4.88 | 3.508–6.898 |
| Production & Precision Ag operating profit | 569.8 | USDm | nested | +0.07 | 8 | 1154 | 385.5–754.1 |

- **Worldwide net sales and revenues** — nested ensemble promoted (strict config) — outer skill +0.27 on 8 unseen origins. Basis: nested causal ensemble (strict config); outer skill 27.3% across 8 unseen origins; direct cross-check 11657.0 _[M2 checked: analogue skill +0.25 on 24 origins — M2 skill +0.25 does not beat guarded-nested M1 +0.27 by ≥5%]_
- **Diluted EPS (GAAP)** — nested ensemble promoted (strict config) — outer skill +0.06 on 8 unseen origins. Basis: nested causal ensemble (strict config); outer skill 5.8% across 8 unseen origins; direct cross-check 4.88 _[M2 checked: analogue skill +0.11 on 24 origins — M2 skill +0.11 below the 0.15 meaningful-skill bar]_
- **Production & Precision Ag operating profit** — nested ensemble promoted (strict config) — outer skill +0.07 on 8 unseen origins. Basis: nested causal ensemble (strict config); outer skill 6.9% across 8 unseen origins; direct cross-check 1154.0 _[M2 checked: analogue skill -0.36 on 12 origins — M2 skill -0.36 below the 0.15 meaningful-skill bar]_

**Reconciliation guard** — guidance blends + anchorless flags (deterministic accuracy pass):
- ⚑ **Production & Precision Ag operating profit**: 569.8 vs direct 1154 (51% apart) — large disagreement with the sourced direct forecast and no reliable guidance anchor — kept the measured-skill value for review

**Extraction provenance** — research agent → point-in-time series (offline cache replay):
- **Worldwide net sales and revenues**: 47 documents read · 47 admitted · 0 rejected → 46 PIT observations (46 research-read, 0 parser-filled)
    - e.g. Q1 2015 = 6383 — "Worldwide net sales and revenues for the first quarter decreased 17 percent, to $6.383 billion, compared with $7.654 billion last " (2015-02-20__de-us-20150220-q1-8k__784661.md)
- **Diluted EPS (GAAP)**: 47 documents read · 45 admitted · 2 rejected (value -1.66 outside plausible range [0.1, 40.0] ×1, quote does not appear verbatim in the source documen ×1) → 46 PIT observations (44 research-read, 2 parser-filled)
    - e.g. Q1 2015 = 1.12 — "Net income attributable to Deere & Company was $386.8 million, or $1.12 per share, for the first quarter ended January 31, compare" (2015-02-20__de-us-20150220-q1-8k__784661.md)
- **Production & Precision Ag operating profit**: 25 documents read · 23 admitted · 2 rejected (agent found no figure on the requested basis ×2) → 22 PIT observations (22 research-read, 0 parser-filled)
    - e.g. Q1 2021 = 643 — "| Operating profit | $ 643 | $ 218 | 195% |" (2021-02-19__de-us-20210219-q1-8k__105842.md)
- → workbook written: `submission\DE-FY2026Q3.xlsx`

## Summary
- **12/12 numbers filled** · 8 promoted to the nested ensemble · 4 on the guarded direct fallback · 0 failure(s)
- direct-fallback metrics (the evidence gate declined to promote these): HD Adjusted diluted EPS, HAS Net fees, HAS Pre-exceptional basic EPS, HAS Pre-exceptional operating profit
- nested-evaluation evidence (per-origin scores): `outputs\nested-parameter-evaluation.md`
- deliverables: four `submission/*.xlsx` workbooks + this log (`logs/clear-run.md`)
- validation: `npm run check:forecasts` confirms every workbook keeps the Summary contract (labels, units, period header, numeric forecasts)
- retries during this run: **none** (a crash would be fixed and re-run inside the 45-minute submission window, producing a new commit + a fresh log)

## Stage log (timestamped)
- `2026-08-16T17:58:33+01:00` — loaded manifest — 4 companies, 12 target numbers
- `2026-08-16T17:58:41+01:00` — HD: 3/3 numbers (2 nested, 1 direct) → wrote HD-FY2026Q2.xlsx
- `2026-08-16T17:58:42+01:00` — ADI: 3/3 numbers (3 nested, 0 direct, 2 guidance-guarded) → wrote ADI-FY2026Q3.xlsx
- `2026-08-16T17:58:45+01:00` — HAS: 3/3 numbers (0 nested, 3 direct) → wrote HAS-FY2026.xlsx
- `2026-08-16T17:58:46+01:00` — DE: 3/3 numbers (3 nested, 0 direct) → wrote DE-FY2026Q3.xlsx
- `2026-08-16T17:58:46+01:00` — wrote nested-parameter-evaluation report

