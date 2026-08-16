"""Methodology layer — the governing HOW of the forecast, separated from the models.

This is the control plane. It holds NAMED methodologies; the active one is read by
every other layer. The agent must read the active methodology and obey it: what the
data sources are, how evidence is abstracted, which models are allowed, and how the
final numbers are produced. Methodologies are FIXED / constitutional — you author a
new one (Methodology 2, …) to change the approach, you do not hot-swap it like a model.

Methodology 1 (this file) = Filing-based quantitative baseline + management-guidance
calibration + calls/slides qualitative state adjustment. Causal prequential evaluation
is active on the ADI reference panel; portfolio-wide coverage, hazard/regime and SMC
remain deferred while the first working form produces the other results directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── Methodology 1: the full, agent-readable specification ─────────────────────────
METHODOLOGY_1 = {
    "id": "methodology-1",
    "name": "Methodology 1 · Filing-based quantitative baseline + guidance calibration",
    "goal": ("A reproducible, auditable forecasting system. One final command processes four "
             "companies and writes four official workbooks holding 12 company-period-metric numbers."),
    "approach": [
        "Filing-based quantitative baseline",
        "+ Management-guidance calibration",
        "+ Calls/slides qualitative state adjustment",
        "+ Optional external-data nowcast (deferred)",
        "+ Hazard/regime model (deferred)",
        "+ Sequential Monte Carlo (deferred)",
        "+ Accounting-consistency bridge",
    ],
    "principles": [
        "Filings are the primary source of historical actuals, metric definitions, accounting basis and numeric guidance.",
        "Calls and slides identify demand direction, cycle state, management confidence, operating drivers and risks.",
        "Calls/slides may NOT set the numeric baseline alone, nor turn subjective wording into unconstrained numbers.",
        "One earnings event can appear across 8-K / 10-Q / slides / call presentation / Q&A — event-level dedup, not five independent pieces of evidence.",
        "Every final number must trace back to source, assumptions and calculation.",
    ],
    "flow": [
        "read documents", "classify + event-dedup", "extract historical actuals",
        "build quarterly panel", "extract management guidance", "quantitative baseline",
        "calls/slides signal extraction", "hazard/regime update (deferred)",
        "SMC scenarios (deferred)", "accounting-identity mapping",
        "units + consistency checks", "write four Excel templates",
    ],
    "data": {
        "corpus": "challenge/offline-data/ — filings, call-transcript sections, slide documents (frozen)",
        "priority": [
            "1 formal financial statements & quarterly reports",
            "2 numbers in the formal earnings release",
            "3 numeric tables in company slides",
            "4 management statements on the call",
            "5 qualitative judgements in Q&A",
        ],
        "quality": [
            "same event appears in multiple documents — dedup by event",
            "some documents contain duplicated converted text",
            "some period metadata may be wrong; some source_url empty",
            "slides have extracted text + image descriptions only",
            "always check period, units and GAAP/adjusted basis",
        ],
    },
    "evidence_schema": {
        "fields": ["company", "published_at", "fiscal_period", "event_id", "document_type",
                   "information_type (actual|guidance|driver|risk|definition)", "metric", "value",
                   "units", "lower_bound", "upper_bound", "qualitative_signal", "confidence",
                   "source_file", "source_excerpt"],
        "event_id": "company + publication date + fiscal period + event type; link filing/slides/presentation/Q&A of one event",
    },
    "panel": [
        "per company, prefer the most recent 8–12 quarters",
        "historical actuals for the 12 target metrics + revenue/margin/operating-profit/tax/shares",
        "YoY and QoQ, same-quarter seasonality, management guidance history, guidance-vs-actual error, key drivers",
        "never mix money / percentages / EPS",
        "transforms: revenue/net-fees in log-level or growth; percentages in points or logit; "
        "operating profit via revenue×margin; EPS via after-tax profit ÷ shares (never a blind independent series)",
    ],
    "baseline": {
        "formula": "next = seasonal anchor + recent-trend adjustment + guidance calibration + company operating adjustment",
        "components": ["latest quarter actual", "same-quarter seasonality", "recent-quarters trend",
                       "current numeric guidance", "historical guidance bias", "accounting relationships"],
        "allowed": ["robust regression", "shrinkage", "weighted historical median", "dynamic linear model",
                    "Bayesian priors", "low-dimensional state-space"],
        "forbidden": "high-parameter neural nets (only ~40–55 quarters per company)",
    },
    "signals": {
        "dimensions": ["demand", "volume", "pricing", "product mix", "inventory", "capacity utilisation",
                       "operating costs", "management confidence", "guidance direction", "risks"],
        "scale": "-2 materially deteriorating · -1 · 0 stable/mixed · +1 · +2 materially improving",
        "rule": "signals only adjust regime probability / scenario weights — never let the LLM overwrite the baseline directly",
        "keep": ["source", "excerpt", "confidence", "affected metric", "affected direction"],
    },
    "adapters": {
        # per-company: drivers + how each target metric is produced (the direct baseline reads `metrics`)
        "HD": {
            "name": "Home Depot", "period": "FY2026Q2",
            "drivers": ["transactions", "average ticket", "comparable sales", "new stores",
                        "acquisition contribution", "gross/operating margin", "tax", "diluted shares"],
            "relations": ["Net sales ← comparable sales + stores + M&A + other growth",
                          "Adjusted EPS ← sales × adj operating margin − interest − tax ÷ shares"],
            "metrics": {
                "Net sales": {"approach": "seasonal", "note": "PY same-quarter × (1 + total-sales-growth guide)"},
                "Adjusted diluted EPS": {"approach": "seasonal", "note": "PY same-quarter adj EPS × (1 + EPS growth); bridge cross-check"},
                "Comparable sales, total company": {"approach": "guide_reversion", "note": "AR(1) toward FY comp-sales guide midpoint"},
            },
            "guidance": "FY2026: total sales growth ~2.5–4.5%; comparable sales ~flat to +2.0%; ~15 new stores",
        },
        "ADI": {
            "name": "Analog Devices", "period": "FY2026Q3",
            "drivers": ["bookings/demand", "inventory cycle", "end-market mix", "utilisation",
                        "adjusted gross margin", "opex", "tax", "shares"],
            "relations": ["Q3 guidance is a strong anchor; judge where in the range the actual lands",
                          "derive adjusted gross margin separately"],
            "metrics": {
                "Revenue": {"approach": "guidance", "note": "Q3 guide $3.9bn ±$100m; position in range from bookings momentum"},
                "Adjusted diluted EPS": {"approach": "guidance", "note": "Q3 guide $3.30 ±$0.15; revenue flow-through"},
                "Adjusted gross margin": {"approach": "series_trend", "note": "GM ~ f(revenue); cross-check via adj op-margin 49% guide"},
            },
            "guidance": "FY2026 Q3: Revenue ~$3.9bn ±$100m; Adjusted EPS ~$3.30 ±$0.15; adj op-margin ~49%",
        },
        "HAS": {
            "name": "Hays plc", "period": "FY2026",
            "drivers": ["Temp & Contracting volume", "Permanent placement volume", "fee rates", "geography",
                        "consultant productivity", "cost savings", "FX", "interest", "tax", "shares"],
            "relations": ["FY2026 already ended → accounting reconstruction + nowcasting",
                          "Pre-exceptional operating profit ← net fees × conversion rate",
                          "Pre-exceptional EPS ← (operating profit − net finance − tax) ÷ basic shares (pence)"],
            "metrics": {
                "Net fees": {"approach": "series_growth", "note": "FY2025 continuing net fees × (1 + reported YoY ≈ −4%)"},
                "Pre-exceptional operating profit": {"approach": "stated", "note": "top of £37–46m range; consensus £43.5m → ~£45.5m"},
                "Pre-exceptional basic EPS": {"approach": "bridge", "note": "operating-profit → after-tax ÷ basic shares, in pence"},
            },
            "guidance": "Q4 update: Group net fees −5% LFL (−4% actual); FY26 pre-exceptional OP top of £37–46m; consensus ~£43.5m",
        },
        "DE": {
            "name": "Deere & Company", "period": "FY2026Q3",
            "drivers": ["shipment volume", "price/mix", "dealer inventory", "production cost", "PPA margin",
                        "other-segment contribution", "Financial Services", "tax", "diluted shares"],
            "relations": ["segment model → worldwide net sales & revenues, PPA operating profit, consolidated GAAP EPS",
                          "FY net-income guidance → H2 residual → Q3 share ÷ shares"],
            "metrics": {
                "Worldwide net sales and revenues": {"approach": "seasonal_segment", "note": "PY Q3 × segment-blended FY %Δ; or FY-implied × Q3 share"},
                "Diluted EPS (GAAP)": {"approach": "fy_ni_bridge", "note": "FY NI guide $4.5–5.0bn − H1 → Q3 share ÷ diluted shares"},
                "Production & Precision Ag operating profit": {"approach": "segment_margin", "note": "PPA sales (FY −5–10%) × segment margin"},
            },
            "guidance": "FY2026: net income $4.5–5.0bn; Production & Precision Ag net sales down 5–10% (FX +3%, price +1%)",
        },
    },
    "output": {
        "files": ["submission/HD-FY2026Q2.xlsx", "submission/ADI-FY2026Q3.xlsx",
                  "submission/HAS-FY2026.xlsx", "submission/DE-FY2026Q3.xlsx"],
        "intermediate": ["research/<T>-evidence.json", "data/quarterly-panel.csv",
                         "outputs/forecasts.json (per output_id: point, p10/p50/p90, baseline, adjustments, sources, confidence)",
                         "logs/timestamped-final-run.log"],
        "rules": ["start from challenge/templates; fill only the yellow forecast cells",
                  "do not change the Summary sheet, labels, units or period",
                  "percentages: 4.5 means 4.5% (not 0.045); Hays EPS 6.2 means 6.2 pence",
                  "12 company-period-metric combinations = 12 independent output IDs",
                  "run npm run check:submission; never upload to OpenStocks programmatically"],
    },
    "implementation": [
        "simple baseline first, SMC later",
        "make the four workbooks generate correctly before adding complex models",
        "every forecast reproducible; every number has a source or a clear model assumption",
        "never hide failures, retries or human input",
        "never store API keys in the repo, logs, entry.json or HTML",
        "all competition-specific code/prompts/workflows created after the event starts",
    ],
    "deferred": ["portfolio-wide backtesting beyond the ADI reference panel", "hazard/regime", "Sequential Monte Carlo",
                 "external-data nowcast"],
    "current_form": ("Direct output: for each metric use the adapter's approach — guidance anchor "
                     "(calibrated by historical guidance bias) where available, else seasonal + trend "
                     "on the extracted actual series, with accounting bridges for EPS / operating profit. "
                     "Causal prequential evaluation is active for the ADI reference panel; portfolio-wide "
                     "coverage remains deferred while the other extractors are wired."),
}


# ── the model approaches Methodology 1 OWNS (formulas + description) ───────────────
MODEL_APPROACHES = {
    "app_guidance": {
        "name": "Guidance anchor",
        "desc": ("Anchor to management's own published numbers — the strongest signal (Methodology 1 §5 "
                 "guidance calibration). Used where the company gives an explicit numeric guide."),
        "formulas": [
            "midpoint:    f = (guide_low + guide_high) / 2",
            "reversion:   f = φ·y_last + (1−φ)·guide_mid,   φ = 0.4",
            "stated:      f = top-of-range, blended with company-compiled consensus",
        ],
        "metrics": ["ADI Revenue", "ADI Adjusted diluted EPS", "HD Comparable sales", "HAS Pre-exc operating profit"],
    },
    "app_seasonal": {
        "name": "Seasonal + trend",
        "desc": ("Same-quarter seasonal anchor plus a recent-trend / growth adjustment on the extracted "
                 "actual series (Methodology 1 §5). Low-dimensional only — no high-parameter models."),
        "formulas": [
            "seasonal × growth:   f = y[t−4] · (1 + g),   g = sales-growth guide or median YoY",
            "recent trend:        f = y[t−4] · (1 + YoY_latest)",
            "net fees:            f = FY_prev · (1 + YoY_reported)",
        ],
        "metrics": ["HD Net sales", "HD Adjusted diluted EPS", "ADI Adjusted gross margin", "HAS Net fees", "DE Worldwide net sales"],
    },
    "app_bridge": {
        "name": "Accounting bridge",
        "desc": ("Derive the target via accounting identities rather than a blind time series "
                 "(Methodology 1 §4 / §9). Keeps money, margins, EPS and shares consistent."),
        "formulas": [
            "EPS:        EPS = NetIncome_after_tax / diluted_shares",
            "DE EPS:     NI_Q3 = (NI_FY_guide − NI_H1) · s_Q3;   EPS = NI_Q3 / shares",
            "op profit:  OP = revenue · operating_margin",
            "Hays OP:    OP = net_fees · conversion_rate",
            "segment:    OP_PPA = sales_PPA · margin_PPA",
        ],
        "metrics": ["DE Diluted EPS (GAAP)", "DE PPA operating profit", "HAS Pre-exc basic EPS"],
    },
}


def adapter(ticker: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {})


def metric_plan(ticker: str, label: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {}).get("metrics", {}).get(label, {})


# ── backtest / selection parameters (active for structured quarterly panels) ──
@dataclass(frozen=True)
class Methodology:
    name: str = METHODOLOGY_1["name"]
    origin_window: int = 16
    min_train: int = 8
    min_origins: int = 6
    weight_cap: float = 0.60
    baseline_weight_floor: float = 0.20
    min_improvement: float = 0.05
    season: int = 4
    baseline: str = "seasonal_naive"

    loss: dict = field(default_factory=lambda: {
        "money": "WAPE = Σ|a−p| / Σ|a|", "eps": "MAE = mean|a−p| ($/share)",
        "pct": "MAE in percentage points"})
    gate: str = "a candidate must beat Seasonal Naive by at least 5% on paired origins or it is dropped"
    pit: str = "point-in-time: at each origin fit only on data available then; guidance only if issued before the target"
    ensemble: str = "survivors weighted from prior-origin paired relative MAE; model cap 0.60; baseline floor 0.20"
    guardrail: str = "point ± realized causal ensemble MAE (diagnostic band, not a calibrated interval)"

    def loss_kind(self, kind: str) -> str:
        return "wape" if kind == "money" else "mae"

    def summary(self) -> dict:
        return {
            "current form": METHODOLOGY_1["current_form"],
            "baseline formula": METHODOLOGY_1["baseline"]["formula"],
            "deferred": ", ".join(METHODOLOGY_1["deferred"]),
        }


METHOD = Methodology()
