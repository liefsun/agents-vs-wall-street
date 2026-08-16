"""Agent orchestrator — the LLM actually RUNS the pipeline's decision layer.

Per company the agent reads BOTH methodologies' forecasts + their point-in-time backtest
errors, then for each metric SELECTS the methodology to use, classifies the regime, and
gives a short reason + confidence. It never invents a number (the methodology constraint)
— it chooses between two deterministic forecasts and explains. Bounded: it may only pick
M2 where M2 produced a value, and it is told the gate's recommendation. Cached at
temperature 0 for reproducibility; with no OpenAI key it falls back to the deterministic
gate, so the pipeline still runs.
"""
from __future__ import annotations

import json

from . import methodology_compare as mc, direct
from .llm import LLM
from .forecast import company_spec, METRIC_MAP
from .prequential import _kind_from_units


def _norm(sel: str) -> str:
    s = str(sel or "").lower()
    if "2" in s or "analog" in s:
        return "methodology-2"
    if "ens" in s:
        return "ensemble"
    return "methodology-1"


def _apply(sel: str, c: dict):
    s = _norm(sel)
    if s == "methodology-2" and c["m2_point"] is not None:
        return c["m2_point"]
    if s == "ensemble" and c["m2_point"] is not None and c["m1_point"] is not None:
        return 0.5 * (c["m1_point"] + c["m2_point"])
    return c["m1_point"]


def _context(ticker: str):
    spec = company_spec(ticker)
    d = direct.forecast(ticker)                                  # Methodology 1
    ctx = []
    for m in spec["metrics"]:
        lbl = m["label"]
        kind = METRIC_MAP.get(ticker, {}).get(lbl, (None, None))[1] or _kind_from_units(m["units"])
        m1 = d["metrics"].get(lbl)
        m2 = mc.m2_forecast(ticker, lbl, kind)                   # Methodology 2 (analogue)
        cmp = mc.compare(ticker, lbl, kind)
        ctx.append({"label": lbl, "units": m["units"], "kind": kind,
                    "m1_point": (m1["point"] if m1 else None),
                    "m2_point": (m2.get("point") if not m2.get("insufficient") else None),
                    "m1_err": cmp["m1_err"], "m2_err": cmp["m2_err"],
                    "gate_selected": cmp["selected"], "gate_reason": cmp.get("fallback_reason")})
    return spec, ctx


def _llm_decide(ticker, spec, ctx, llm):
    rows = [{"label": c["label"], "units": c["units"], "M1": c["m1_point"], "M2": c["m2_point"],
             "M1_backtest_err": c["m1_err"], "M2_backtest_err": c["m2_err"],
             "gate_hint": c["gate_selected"]} for c in ctx]
    system = ("You are a forecasting ORCHESTRATION agent. You NEVER invent numbers — you SELECT which of "
              "two deterministic forecasts to use per metric and explain briefly. Rules: prefer the "
              "methodology with the lower point-in-time backtest error; you may only pick 'M2' if its value "
              "is not null; if M1 and M2 are within ~5% choose 'ensemble'; otherwise respect the gate_hint. "
              "Output JSON only.")
    user = (f"Company {ticker} — {spec['company']}, target {spec['period']}. For EACH metric choose "
            f"selected in {{'M1','M2','ensemble'}}, regime in {{'contraction','stabilisation','recovery'}}, "
            f"a reason (<=20 words), and confidence in {{'high','medium','low'}}.\n"
            f"Metrics:\n{json.dumps(rows)}\n"
            'Reply exactly {"decisions":[{"label":"","selected":"","regime":"","reason":"","confidence":""}]}')
    raw = llm.complete_json(system, user, max_tokens=900)
    if not raw:
        return None
    try:
        return {d["label"]: d for d in json.loads(raw).get("decisions", [])}
    except Exception:
        return None


def orchestrate(ticker: str, llm: LLM | None = None) -> dict:
    """Run the agent's decision layer for one company. Returns per-metric decisions +
    the resulting point (the deterministic forecast of the chosen methodology)."""
    llm = llm or LLM()
    spec, ctx = _context(ticker)
    decided = _llm_decide(ticker, spec, ctx, llm) if llm.available else None
    out = []
    for c in ctx:
        dec = (decided or {}).get(c["label"], {})
        sel = dec.get("selected") or c["gate_selected"]
        if _norm(sel) == "methodology-2" and c["m2_point"] is None:      # bound: M2 must have a value
            sel = "methodology-1"
        out.append({**c, "selected": _norm(sel), "regime": dec.get("regime"),
                    "reason": (dec.get("reason") or c["gate_reason"] or "lower PIT error"),
                    "confidence": dec.get("confidence") or "—",
                    "point": _apply(sel, c), "by": "agent" if dec else "gate"})
    return {"ticker": ticker, "company": spec["company"], "period": spec["period"],
            "agent": bool(decided), "decisions": out}
