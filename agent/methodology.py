"""Methodology layer — the governing HOW of the forecast, separated from the models.

This is the control plane. It holds NAMED methodologies; the active one is read by
every other layer. The agent must read the active methodology and obey it: what the
data sources are, how evidence is abstracted, which models are allowed, and how the
final numbers are produced. Methodologies are FIXED / constitutional — you author a
new one (Methodology 2, …) to change the approach, you do not hot-swap it like a model.

Methodology 1 (this file) = Filing-based quantitative baseline + management-guidance
calibration + calls/slides qualitative state adjustment, with hazard/regime, SMC and
backtesting described but DEFERRED — the first working form produces results directly.
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
    "deferred": ["backtesting (rolling-origin)", "hazard/regime", "Sequential Monte Carlo",
                 "external-data nowcast"],
    "current_form": ("Direct output: for each metric use the adapter's approach — guidance anchor "
                     "(calibrated by historical guidance bias) where available, else seasonal + trend "
                     "on the extracted actual series, with accounting bridges for EPS / operating profit. "
                     "Backtesting is deferred; results are produced directly."),
}


# ── the model approaches Methodology 1 OWNS (formulas + description) ───────────────
MODEL_APPROACHES = {
    "app_guidance": {
        "name": "Guidance anchor",
        "desc": ("Anchor to management's own published numbers — the strongest signal (Methodology 1 §5 "
                 "guidance calibration). Used where the company gives an explicit numeric guide."),
        "latex": [
            (r"f = \tfrac{1}{2}\,(g_{\text{lo}} + g_{\text{hi}})", "guidance midpoint"),
            (r"f = \varphi\,y_{t-1} + (1-\varphi)\,g_{\text{mid}},\quad \varphi = 0.4", "reversion to guide"),
            (r"f = \text{top-of-range}\ \oplus\ \text{consensus}", "stated range"),
        ],
        "metrics": ["ADI Revenue", "ADI Adjusted diluted EPS", "HD Comparable sales", "HAS Pre-exc operating profit"],
    },
    "app_seasonal": {
        "name": "Seasonal + trend",
        "desc": ("Same-quarter seasonal anchor plus a recent-trend / growth adjustment on the extracted "
                 "actual series (Methodology 1 §5). Low-dimensional only — no high-parameter models."),
        "latex": [
            (r"f = y_{t-4}\,(1 + g),\quad g = \text{guide or } \operatorname{median}_i \tfrac{y_i}{y_{i-4}}", "seasonal × growth"),
            (r"f = y_{t-4}\,(1 + \mathrm{YoY}_{\text{latest}})", "recent trend"),
            (r"f = \mathrm{FY}_{\text{prev}}\,(1 + \mathrm{YoY}_{\text{reported}})", "net fees"),
        ],
        "metrics": ["HD Net sales", "HD Adjusted diluted EPS", "ADI Adjusted gross margin", "HAS Net fees", "DE Worldwide net sales"],
    },
    "app_bridge": {
        "name": "Accounting bridge",
        "desc": ("Derive the target via accounting identities rather than a blind time series "
                 "(Methodology 1 §4 / §9). Keeps money, margins, EPS and shares consistent."),
        "latex": [
            (r"\mathrm{EPS} = \dfrac{\mathrm{NI}_{\text{after-tax}}}{\text{shares}_{\text{dil}}}", "EPS identity"),
            (r"\mathrm{NI}_{Q3} = (\mathrm{NI}_{FY} - \mathrm{NI}_{H1})\,s_{Q3},\quad \mathrm{EPS}=\dfrac{\mathrm{NI}_{Q3}}{\text{shares}}", "DE quarterly EPS"),
            (r"\mathrm{OP} = \text{revenue}\times m_{\text{op}}", "operating profit"),
            (r"\mathrm{OP} = \text{net-fees}\times c\quad(c=\text{conversion rate})", "Hays OP"),
            (r"\mathrm{OP}_{\mathrm{PPA}} = \text{sales}_{\mathrm{PPA}}\times m_{\mathrm{PPA}}", "segment OP"),
        ],
        "metrics": ["DE Diluted EPS (GAAP)", "DE PPA operating profit", "HAS Pre-exc basic EPS"],
    },
}

# candidate models (param-eval grid) + backtest math, in LaTeX — shown in the package view
MODELS_LATEX = [
    ("seasonal_naive", r"\hat y_t = y_{t-4}", "baseline — same quarter last year"),
    ("naive_last", r"\hat y_t = y_{t-1}", "last quarter"),
    ("drift_mult", r"\hat y_t = y_{t-4}\cdot \operatorname{median}_i \tfrac{y_i}{y_{i-4}}", "seasonal × median YoY growth"),
    ("drift_add", r"\hat y_t = y_{t-4} + \operatorname{median}_i (y_i - y_{i-4})", "seasonal + median YoY change"),
    ("trend_mult", r"\hat y_t = y_{t-4}\,(1 + b_0 + b_1 t)", "seasonal + linear growth trend"),
    ("ar_lag", r"\hat y_t = \beta_0 + \beta_1 y_{t-1} + \beta_2 y_{t-4}", "lagged OLS / AR"),
    ("ets_hw", r"\hat y_t = \ell_t + b_t + s_{t-m}", "Holt-Winters (level+trend+season)"),
]
BACKTEST_LATEX = [
    (r"\mathrm{WAPE} = \dfrac{\sum_t |a_t - \hat y_t|}{\sum_t |a_t|}", "point error (money/EPS); pct uses MAE in points"),
    (r"\text{breach}_t = \mathbb{1}\!\left[\,|a_t - \hat y_t| > z\,\sigma_{<t}\,\right],\quad z_{80\%}=1.28", "VaR-style band coverage (PIT σ)"),
    (r"LR = -2\ln\dfrac{(1-p_0)^{n-x}\,p_0^{x}}{(1-\hat p)^{n-x}\,\hat p^{x}},\quad \hat p=\tfrac{x}{n}\sim\chi^2_1", "Kupiec POF calibration test"),
]


def adapter(ticker: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {})


def metric_plan(ticker: str, label: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {}).get("metrics", {}).get(label, {})


# ── backtest / selection parameters (DEFERRED layer; kept for when it is switched on) ──
@dataclass(frozen=True)
class Methodology:
    name: str = METHODOLOGY_1["name"]
    origin_window: int = 16
    min_train: int = 8
    min_origins: int = 6
    weight_cap: float = 0.60
    baseline: str = "seasonal_naive"

    loss: dict = field(default_factory=lambda: {
        "money": "WAPE = Σ|a−p| / Σ|a|", "eps": "MAE = mean|a−p| ($/share)",
        "pct": "MAE in percentage points"})
    gate: str = "a candidate must beat Seasonal Naive or it is dropped"
    pit: str = "point-in-time: at each origin fit only on data available then; guidance only if issued before the target"
    ensemble: str = "survivors weighted by 1/error, capped, renormalised; fall back to baseline"
    guardrail: str = "point ± ensemble error → band (money multiplicative, eps/pct additive)"

    def loss_kind(self, kind: str) -> str:
        return "wape" if kind == "money" else "mae"

    def summary(self) -> dict:
        return {
            "current form": METHODOLOGY_1["current_form"],
            "baseline formula": METHODOLOGY_1["baseline"]["formula"],
            "deferred": ", ".join(METHODOLOGY_1["deferred"]),
        }


METHOD = Methodology()
