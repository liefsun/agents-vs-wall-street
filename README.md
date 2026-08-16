# Agents vs Wall Street

Agents vs Wall Street is a one-day hackathon presented by Primer, OpenStocks, AI Tinkerers and OpenAI. Around 50 people will build 20–25 forecasting agents, working alone or in teams of up to four.

The challenge covers four companies: Home Depot, Analog Devices, Hays plc and Deere & Company. Your agent forecasts three reported figures for each.

The repository includes a frozen historical corpus of 1,139 filings, call-transcript sections and slide documents for the four known companies. Start at [challenge/offline-data/INDEX.md](challenge/offline-data/INDEX.md) or search the Markdown files directly.

Your agent should be able to do the research, make the financial judgements and produce completed OpenStocks workbooks with as little manual help as possible.

## What the day is for

1. **Build something real.** Create a repeatable agent that researches companies, makes financial judgements and produces completed forecast workbooks.
2. **Show what is possible.** Help us learn what works and show how powerful this technology can be when it is assembled properly.

OpenStocks offers ongoing $100 prizes for individual earnings events after the hackathon, so build an agent you can use again.

## The challenge at a glance

- Doors open at 10:00 on Sunday 16 August 2026 at Ground Floor, 33 Johns Mews, London WC1N 2QL. The competition briefing begins at 10:30 and building starts at 11:15.
- Teams can have one to four people.
- Each individual or team enters one agent.
- Each team receives $50 of Codex credit, kindly provided by OpenAI.
- Competition-specific work must be built during the event; evidence of a pre-made entry means disqualification from all prizes.
- Your agent must forecast three figures for each of four companies.
- The final run starts at 17:15 and must finish before the 18:00 deadline.
- OpenStocks opens for challenge uploads at 17:30.
- Your final command must produce all four `.xlsx` workbooks.
- Upload each workbook manually to the matching company Forecast Model on [openstocks.com](https://openstocks.com).
- If you upload more than once, the last valid workbook uploaded for each company before 18:00 is your final forecast.

## What you need to submit

1. A completed private `entry.json` with the agent name, every team member and email address, technical setup and final-run details. Upload it through openstocks.com/hackathon; no account is needed for this private team-entry form.
2. Your code repository and the commit used for the final run.
3. The completed self-contained `architecture/index.html`, uploaded through the same private form. You do not need to host it anywhere.
4. A timestamped log from a clear run of the system.
5. Four completed company workbooks in `submission/`.

Complete [ENTRY.md](ENTRY.md), then read [SUBMISSION.md](SUBMISSION.md) before the final run. The full event rules are in [RULES.md](RULES.md), the day is set out in [SCHEDULE.md](SCHEDULE.md), and the judging process is explained in [JUDGING.md](JUDGING.md).

By submitting the private team entry, your team accepts the hackathon and prize rules in [RULES.md](RULES.md).

## Expected final output

Your final command can use any language or framework, and it can run the four companies one after another or at the same time. It must finish by creating these exact files:

```text
submission/
├── ADI-FY2026Q3.xlsx
├── DE-FY2026Q3.xlsx
├── HAS-FY2026.xlsx
└── HD-FY2026Q2.xlsx
```

Start from the supplied files in `challenge/templates/`. Do not rename the `Summary` sheet, metric labels, units or fiscal-period column.

Run `npm install` and `npm run setup:entry` once. Complete the private `entry.json` and `architecture/index.html`, then use `npm run check:submission` before uploading. It checks the entry record, architecture file and four workbooks. It does not judge whether the forecasts are good.

## Current forecasting agent

The implemented pipeline combines filing-based direct forecasts with guarded nested
causal model selection. A nested forecast replaces the direct value only when it has
at least three unseen outer origins, positive outer skill against seasonal naive, and
a non-fallback deployment ensemble with positive skill. Metrics without enough history
remain on the auditable direct forecast.

Historical ingestion is point-in-time and frequency-aware: quarterly US series use
season 4, while Hays H1/FY observations use a semiannual season 2. The frozen corpus
currently supports honest prequential diagnostics for 10 of 12 target metrics.

### Research agent (`agent/research.py`)

The reading step is done by an LLM working to an analyst brief per metric, not by a
hand-written regular expression. For each target metric the agent retrieves the candidate
earnings releases, reads focused excerpts around the metric's own language, and returns
the figure **that document reports for its own period**, together with the sentence it
took it from.

Nothing the agent says is trusted on its word. Every extraction must pass a validation
gate before it can enter a series:

| Check | Rejects |
| --- | --- |
| Verbatim quote | a supporting sentence that does not appear in the source document |
| Plausible range | a value outside the metric's order-of-magnitude bounds |
| Stated confidence | anything the agent itself marks `low` |
| Declared basis | a GAAP figure where the target is adjusted, a segment where the target is group |
| Cross-check | a period where the agent and the deterministic parser disagree by more than 2% |

`tests/test_research.py` drives each rejection path with a stubbed driver, including a
fabricated quote, so the gate is shown to reject before any pass is believed.

The agent extracts **reported historical facts**, never a forecast — that boundary is what
keeps the numbers auditable. Completions are temperature 0 and disk-cached under
`agent/cache/research/`; once the cache is warm the final run makes no network calls, so
the clear run is reproducible offline. With no OpenAI key configured the agent is simply
unavailable and the deterministic parsers in `agent/history.py` take over, so the pipeline
never silently loses a stage.

```bash
cp .env.example .env        # then set OPENAI_API_KEY (and optionally OPENAI_MODEL)
```

```bash
uv run --with-requirements agent/requirements.txt python -m agent.run
npm run check:forecasts
```

The final command writes all four workbooks plus ignored runtime reports under
`outputs/`. See [the tracked nested-evaluation report](docs/NESTED_PARAMETER_EVALUATION.md)
for the causal contract, outer results and forecast impact.

## Optional document-search helper

[`starter/search.py`](starter/search.py) is a small, dependency-free example of searching the supplied Markdown corpus and producing a cited research note. It does not make forecasts or edit a workbook.

```bash
python3 starter/search.py --company HD
less research/HD.md
```

Use `HD`, `ADI`, `HAS` or `DE` for the four challenge companies. The output contains search leads rather than verified financial history, so check each figure in its cited document. Read [starter/README.md](starter/README.md) for narrower searches and testing instructions.

## Repository map

```text
challenge/                 Companies, metrics, workbooks and historical documents
architecture/index.html    Template for the required architecture explanation
entry.template.json        Template for private team and agent details
submission/                Put the four completed workbooks here
logs/                      Save the final clear-run log here
scripts/                   Local entry and workbook checks
starter/                   Optional historical-document search helper
agent/                     Forecasting, causal backtest and guarded selection pipeline
docs/                      Run contract and tracked evaluation report
tests/                     Causality, pairing, selection and organiser helper tests
```

## Licence

The original code and documentation in this repository are available under the [MIT License](LICENSE). The historical company documents under `challenge/offline-data/` are excluded; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
