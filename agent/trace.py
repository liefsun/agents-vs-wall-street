"""Provenance trace — how RAW DATA becomes the final number, per metric.

Assembles the full audit chain the methodology requires (§11 auditability, §13
reproducibility): sources → extraction → Methodology-1 path → Methodology-2 path
(with the historical analogues) → parameter eval → point-in-time backtest → agent
decision → stats-control → final number. Written to outputs/trace.json.
"""
from __future__ import annotations

from . import direct, methodology_compare as mc, prequential, param_eval, orchestrator, stats_control
from .forecast import company_spec, METRIC_MAP
from .prequential import _kind_from_units

TICKERS = ["HD", "ADI", "HAS", "DE"]


def _series_tail(ticker, label, n=6):
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return []
    from .extract import key_to_period
    pv = [(key_to_period(a), v) for a, v in zip(axis, values) if v is not None]
    return pv[-n:]


def trace_metric(ticker, label, kind, units, m1, dec):
    """One metric's full chain. m1 = direct forecast dict; dec = agent decision dict."""
    m2 = mc.m2_forecast(ticker, label, kind)
    bt = prequential.backtest_metric(ticker, label, kind)
    pe = param_eval.compare(ticker, label, kind)
    tail = _series_tail(ticker, label)

    step_m2 = {"insufficient": True, "reason": m2.get("reason")}
    if not m2.get("insufficient"):
        step_m2 = {"insufficient": False, "base": m2["base"], "bear": m2["bear"], "bull": m2["bull"],
                   "n": m2["n"], "anchor": m2["anchor"],
                   "analogues": [{"period": a["period"], "dist": round(a["dist"], 2),
                                  "weight": round(a["weight"], 3), "next_growth": round(a["growth"], 3)}
                                 for a in m2["analogues"]]}
    step_pe = {"insufficient": True}
    if not pe.get("insufficient"):
        step_pe = {"best": pe["best"], "beats_baseline": pe["beats_baseline"],
                   "robust": bool((pe.get("sensitivity") or {}).get("robust")),
                   "ranking": [r["model"] for r in pe["rows"][:5]]}
    step_bt = {"insufficient": True, "reason": bt.get("reason")}
    if not bt.get("insufficient"):
        step_bt = {"model": bt["model"], "n_origins": bt["n_origins"], "wape": bt["wape"],
                   "mae": bt["mae"], "breach_rate": bt["breach_rate"],
                   "expected_breach": bt["expected_breach"], "kupiec_pvalue": bt["kupiec_pvalue"]}

    sc = stats_control.validate([{"label": label, "kind": kind,
                                  "point": dec.get("point"), "band": None}])[label]

    return {
        "ticker": ticker, "label": label, "units": units, "kind": kind,
        "sources": (m1.get("sources") if m1 else []) or [],
        "extraction": {"series_tail": tail, "n_periods": len(tail)},
        "methodology_1": {"approach": methodology_approach(ticker, label), "basis": (m1 or {}).get("basis"),
                          "point": (m1 or {}).get("point")},
        "methodology_2": step_m2,
        "parameter_eval": step_pe,
        "backtest": {"m1_err": (bt["mae"] if kind == "pct" else bt.get("wape")) if not bt.get("insufficient") else None,
                     "detail": step_bt},
        "agent": {"selected": dec.get("selected"), "regime": dec.get("regime"),
                  "reason": dec.get("reason"), "confidence": dec.get("confidence"), "by": dec.get("by")},
        "stats_control": {"verdict": sc["verdict"],
                          "failed": [c["name"] for c in sc["checks"] if not c["ok"]]},
        "final": {"point": dec.get("point"), "methodology": dec.get("selected")},
    }


def methodology_approach(ticker, label):
    from . import methodology as _m
    return _m.metric_plan(ticker, label).get("approach")


def trace_all():
    rows = []
    for t in TICKERS:
        spec = company_spec(t)
        d = direct.forecast(t)
        orch = orchestrator.orchestrate(t)
        dec_by = {x["label"]: x for x in orch["decisions"]}
        agent_on = orch["agent"]
        for m in spec["metrics"]:
            lbl = m["label"]
            kind = METRIC_MAP.get(t, {}).get(lbl, (None, None))[1] or _kind_from_units(m["units"])
            m1 = d["metrics"].get(lbl)
            tr = trace_metric(t, lbl, kind, m["units"], m1, dec_by.get(lbl, {}))
            tr["company"] = spec["company"]
            tr["period"] = spec["period"]
            tr["agent_on"] = agent_on
            rows.append(tr)
    return rows
