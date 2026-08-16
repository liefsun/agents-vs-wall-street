"""Methodology layer — the governing HOW of the forecast, separated from the models.

This is the control plane. It holds NAMED methodologies; the active one is read by
every other layer. The agent must read the active methodology and obey it: what the
data sources are, how evidence is abstracted, which models are allowed, and how the
final numbers are produced. Methodologies are FIXED / constitutional — you author a
new one (Methodology 2, …) to change the approach, you do not hot-swap it like a model.

Methodology 1 (this file) = Filing-based quantitative baseline + management-guidance
calibration + calls/slides qualitative state adjustment. Nested causal evaluation is
active where histories are scoreable; other metrics retain an auditable direct fallback.
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
        (
            "transforms: revenue/net-fees in log-level or growth; percentages in points or logit; "
            "operating profit via revenue×margin; EPS via after-tax profit ÷ shares "
            "(never a blind independent series)"
        ),
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
    "deferred": ["external first-report history for the remaining two HD metrics", "hazard/regime", "Sequential Monte Carlo",
                 "external-data nowcast"],
    "current_form": ("Guarded nested output: use the nested causal ensemble only when unseen outer "
                     "evidence and deployment skill are positive; otherwise retain the adapter's direct "
                     "guidance, seasonal or accounting-bridge forecast."),
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

# Candidate estimators in the inner ensemble pool, shown in the package view.
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
    (r"\mathrm{MAE} = \dfrac{1}{n}\sum_{t=1}^{n}|a_t-\hat y_t|", "primary point-error metric; percentage targets remain in percentage points"),
    (r"r = \dfrac{\mathrm{MAE}_{\mathrm{method}}}{\mathrm{MAE}_{\mathrm{seasonal}}},\qquad \mathrm{skill}=1-r", "paired comparison against seasonal naive on identical targets"),
    (r"\mathcal D_{\mathrm{inner}}(t) \subset \{s:s<t\}", "causal nesting: configuration selection cannot see the outer target"),
    (r"\text{breach}_t = \mathbb{1}\!\left[\,|a_t - \hat y_t| > z\,\sigma_{<t}\,\right],\quad z_{80\%}=1.28", "VaR-style band coverage (PIT σ)"),
    (r"LR = -2\ln\dfrac{(1-p_0)^{n-x}\,p_0^{x}}{(1-\hat p)^{n-x}\,\hat p^{x}},\quad \hat p=\tfrac{x}{n}\sim\chi^2_1", "Kupiec POF calibration test"),
]


def adapter(ticker: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {})


def metric_plan(ticker: str, label: str) -> dict:
    return METHODOLOGY_1["adapters"].get(ticker, {}).get("metrics", {}).get(label, {})


# ── backtest / selection parameters (active for structured histories) ──────────────
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
        "money": "MAE in reporting units", "eps": "MAE in $/share or pence/share",
        "pct": "MAE in percentage points"})
    gate: str = "a candidate must beat Seasonal Naive by at least 5% on paired origins"
    pit: str = "point-in-time: at each origin fit only on data available then; guidance only if issued before the target"
    ensemble: str = "paired relative-MAE weights; model cap 0.60; baseline floor 0.20"
    guardrail: str = "point ± realized causal ensemble MAE (diagnostic, not calibrated)"

    def loss_kind(self, kind: str) -> str:
        return "mae"

    def summary(self) -> dict:
        return {
            "current form": METHODOLOGY_1["current_form"],
            "baseline formula": METHODOLOGY_1["baseline"]["formula"],
            "deferred": ", ".join(METHODOLOGY_1["deferred"]),
        }


METHOD = Methodology()


# ══════════════════════════════════════════════════════════════════════════════════
# Methodology 2 — independent parallel methodology (historical analogue + scenarios).
# Kept as a self-contained block so the engine (Methodology 1) stays untouched; the
# agent orchestration layer reads BOTH and selects per metric.
# ══════════════════════════════════════════════════════════════════════════════════
METHODOLOGY_2 = {
    "id": "methodology-2",
    "name": "Methodology 2 · Historical Analogue + Evidence-Weighted Scenarios",
    "goal": ("For each company-period-metric, find the historical quarters whose operating STATE most "
             "resembles today, use their realized NEXT-period outcomes to build a forecast distribution, "
             "then reweight with guidance + calls/slides evidence into Bear/Base/Bull scenarios and a point."),
    "recipe": ["historical-state matching", "+ forward-outcome distribution",
               "+ evidence-weighted scenarios", "+ accounting reconciliation"],
    "core_idea": ("Not 'what is next-quarter revenue?' but 'which past quarters looked like now, and what "
                  "happened to revenue/margin/EPS right after them?'"),
    "flow": ["current company state", "find historical analogue quarters",
             "observe their next-period realized outcomes", "weight by similarity + recency",
             "reweight with current guidance + calls/slides evidence",
             "Bear/Base/Bull distribution", "accounting reconciliation", "output"],
    "snapshot_features": [
        "latest level", "YoY growth", "QoQ growth", "1-quarter momentum", "2-quarter momentum",
        "historical volatility", "latest margin", "margin change", "guidance midpoint",
        "guidance range width", "guidance change vs prior", "demand signal", "pricing signal",
        "inventory signal", "management-confidence signal", "current regime", "recency",
    ],
    "leakage_rules": [
        "snapshot at t uses ONLY info with published_at ≤ t",
        "standardisation mean/std from the then-available training set only",
        "the analogue TARGET is the next period actually reported AFTER t",
        "no calls/slides/filings published after the target result",
        "event-dedup multiple docs of one earnings event",
    ],
    "company_features": {
        "HD": ["comparable-sales level & direction", "transaction growth", "average-ticket growth",
               "total-sales growth", "Pro vs DIY", "gross/operating margin", "weather/housing", "M&A & store contribution"],
        "ADI": ["revenue growth", "end-market mix (Ind/Auto/Comms)", "bookings/demand", "inventory cycle",
                "adjusted gross margin", "adjusted operating margin", "guidance mid & width", "beat/miss history"],
        "HAS": ["Group net-fee growth", "Temp & Contracting growth", "Permanent growth", "geography mix",
               "consultant productivity", "headcount change", "cost savings", "conversion rate", "FX & portfolio"],
        "DE": ["worldwide sales growth", "PPA sales & operating margin", "shipment volume", "price/mix",
               "production cost", "dealer inventory", "segment outlook", "group net-income guidance"],
    },
    "parameters": {
        "K": [3, 5, 7, 9],
        "distance": ["Manhattan", "Euclidean"],
        "recency_half_life": [8, 12, 20, "inf"],
        "feature_sets": ["financial only", "financial + guidance", "financial + guidance + signals"],
        "regime_filter": ["off", "same-regime", "adjacent-regime"],
        "selected_via": "point-in-time rolling backtest across many origins + windows + sensitivity; "
                        "prefer low error AND cross-window stability (avoid fragile best-on-one-window configs)",
    },
    "gate": [
        "enough historical origins", "≥3 valid analogues", "analogue distances not all too large",
        "PIT MAE/WAPE beats seasonal-naive", "stable across backtest windows",
        "interval coverage not badly off", "passes unit + accounting-consistency checks",
        "else → fallback to Methodology 1; if M1≈M2 → capped ensemble (neither dominates unbounded)",
    ],
    "signals_role": ["set current regime", "adjust feature weights", "adjust analogue weights",
                     "adjust Bear/Base/Bull probabilities", "explain why now is (un)like the past — never set numbers"],
    "output_schema": ["methodology", "model", "selected_k", "distance", "recency_half_life", "current_features",
                      "analogues[origin_period, distance, weight, next_period_actual, sources]",
                      "bear", "base", "bull", "scenario_probabilities", "point_forecast",
                      "original_point", "reconciled_point", "confidence", "fallback_reason"],
    "constraints": [
        "LLM never sets the final number", "fixed random seed; same input → same output",
        "no future leakage", "never hide fallback", "every analogue has a source + historical period",
        "insufficient data → explicit fallback to Methodology 1", "still 12 numbers → 4 official workbooks",
    ],
    "point_rule": "default point = weighted median (Base scenario)",
    "current_form": ("Live: analogue KNN on PIT financial snapshots → recency×similarity-weighted next-period "
                     "YoY-growth distribution → Bear/Base/Bull (P20/P50/P80) applied to the seasonal anchor, "
                     "gated vs Methodology 1 + seasonal-naive. Guidance-constraint, regime-filter, qualitative "
                     "signal reweighting and cross-metric accounting reconciliation are specified and staged."),
}

# Methodology 2's OWNED approaches (registry) — with LaTeX
MODEL_APPROACHES_2 = {
    "m2_analogue_plain": {
        "name": "Analogue · plain",
        "desc": "Weighted distance on standardised snapshot features; take the K nearest historical quarters and use their next-period actuals.",
        "latex": [(r"d(i,\text{now}) = \sum_f w_f\,\lvert z_{i,f} - z_{\text{now},f}\rvert", "robust (Manhattan) distance"),
                  (r"z_{i,f} = \dfrac{x_{i,f} - \mu^{<t}_f}{\sigma^{<t}_f}", "PIT standardisation")],
    },
    "m2_recency_weighted": {
        "name": "Analogue · recency-weighted",
        "desc": "Combine similarity with time-decay so old cycles don't dominate.",
        "latex": [(r"w_i = \underbrace{\tfrac{1}{1+d_i}}_{\text{similarity}}\times\exp\!\left(-\tfrac{\text{age}_i}{h}\right)", "similarity × recency, half-life h")],
    },
    "m2_regime_filtered": {
        "name": "Analogue · regime-filtered",
        "desc": "Classify current state (contraction / stabilisation / recovery) and only match analogues in the same or adjacent regime.",
        "latex": [(r"\mathcal{A} = \{\,i : \text{regime}_i \in \{r_{\text{now}},\, r_{\text{now}}\pm 1\}\,\}", "regime-constrained analogue set")],
    },
    "m2_guidance_constrained": {
        "name": "Analogue · guidance-constrained",
        "desc": "Where guidance exists, let it act as a soft likelihood — down-weight analogues that conflict badly with the guide (never hard-clip the whole distribution).",
        "latex": [(r"w_i \leftarrow w_i \cdot \exp\!\left(-\lambda\,\lvert o_i - g_{\text{mid}}\rvert / g_{\text{width}}\right)", "soft guidance likelihood")],
    },
    "m2_scenario_weighted": {
        "name": "Scenario · Bear / Base / Bull",
        "desc": "Weighted quantiles of the analogues' next-period outcomes; calls/slides adjust the three probabilities, not the numbers.",
        "latex": [(r"\text{Bear}=Q_{0.2},\ \text{Base}=Q_{0.5},\ \text{Bull}=Q_{0.8}\ \text{(weighted)}", "scenario quantiles"),
                  (r"\hat f = \sum_s p_s\,Q_s,\quad \sum_s p_s = 1", "evidence-weighted point")],
    },
    "m2_accounting_reconciled": {
        "name": "Accounting reconciliation",
        "desc": "Push analogue forecasts through the company bridge (revenue→margin→OP→NI→EPS); reconcile conflicts, log original/adjusted/reason.",
        "latex": [(r"\text{Rev}\to m\to \text{OP}\to \text{NI}\to \text{EPS}", "consistency bridge")],
    },
}


METHODOLOGIES = {"methodology-1": METHODOLOGY_1, "methodology-2": METHODOLOGY_2}

# what INPUTS each methodology needs — the agent reasons about how to provision these
# from the data catalog, and feature-control validates the provisioned features.
INPUT_SPECS = {
    "methodology-1": {
        "needs": ["a produced point via one of: management guidance for the target period, "
                  "a same-quarter seasonal anchor (actual series ≥ 8 quarters), or an accounting "
                  "bridge (net income / shares, or revenue / margin)"],
        "min_series": 0,       # M1 has stated/guidance fallbacks — almost always provisionable
    },
    "methodology-2": {
        "needs": ["an actual metric series ≥ 14 quarters (to build PIT snapshots and find analogues)",
                  "non-degenerate features (YoY-growth variance > 0)",
                  "≥ 3 valid historical analogues"],
        "min_series": 14,
        "min_analogues": 3,
    },
}
