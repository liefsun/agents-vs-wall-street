"""Provisioning agent — the LLM reasons over the DATA CATALOG + each methodology's input
requirements and decides, per metric, HOW to provide the inputs each methodology needs
(and whether that is feasible). Grounded + bounded: it works only over the structured
catalog and can never mark a methodology feasible if feature-control rejects the features.
The LLM never invents data. Cached (reproducible); deterministic fallback with no key.
"""
from __future__ import annotations

import json

from . import catalog as _cat, feature_control as _fc, methodology
from .llm import LLM
from .forecast import company_spec


def _det_reason(cat, fc):
    if fc["m2_feasible"]:
        return f"M1 ✓; M2 ✓ — {cat['series_periods']}q series, var {cat['yoy_var']}, cov {int(cat['coverage']*100)}%"
    return f"M1 ✓; M2 ✗ — {fc['m2_reason']}"


def _llm_provision(ticker, cat, fc_by, llm):
    rows = [{"label": l, "M1_input_available": cat[l]["m1_point_available"], "M1_basis": cat[l]["m1_basis"],
             "series_periods": cat[l]["series_periods"], "yoy_variance": cat[l]["yoy_var"],
             "coverage": cat[l]["coverage"], "has_guidance": cat[l]["has_guidance"],
             "feature_control_says_M2_feasible": fc_by[l]["m2_feasible"]} for l in cat]
    inp = methodology.INPUT_SPECS
    system = ("You are a data-PROVISIONING agent. Given a DATA CATALOG (what features are available per metric) "
              "and two methodologies' input requirements, decide for EACH metric whether each methodology's "
              "inputs can be provided, and which features you would use. You NEVER invent data — use only "
              "features the catalog reports, and you MUST respect feature_control_says_M2_feasible (if false, "
              "M2 is not feasible). JSON only.")
    user = (f"Company {ticker}.\nMethodology-1 needs: {inp['methodology-1']['needs'][0]}\n"
            f"Methodology-2 needs: {'; '.join(inp['methodology-2']['needs'])}\n"
            f"Catalog:\n{json.dumps(rows)}\n"
            'For each metric reply {"label":"","m1_feasible":true,"m2_feasible":false,'
            '"features_for_m2":"which catalog features","reason":"<=18 words"}. '
            'Reply exactly {"provision":[...]}.')
    raw = llm.complete_json(system, user, max_tokens=1000)
    if not raw:
        return None
    try:
        return {d["label"]: d for d in json.loads(raw).get("provision", [])}
    except Exception:
        return None


def provision(ticker: str, llm: LLM | None = None) -> dict:
    llm = llm or LLM()
    cat = _cat.catalog(ticker)
    fc_by = {l: _fc.check(cat[l]) for l in cat}
    plan = _llm_provision(ticker, cat, fc_by, llm) if llm.available else None
    out = []
    for l in cat:
        fc = fc_by[l]
        p = (plan or {}).get(l, {})
        # Feasibility is decided by FEATURE-CONTROL (deterministic stats-control on the
        # features) — the agent does NOT flip it with fuzzy judgement. The agent's job is
        # the abstraction: WHICH catalog features to provision + the reasoning.
        m2 = fc["m2_feasible"]
        feats = ((p.get("features_for_m2") if (plan and m2) else None)
                 or (f"{cat[l]['series_periods']}q series → yoy/qoq/momentum/vol snapshot"
                     if fc["m2_feasible"] else "—"))
        out.append({"label": l, "units": cat[l]["units"],
                    "m1_feasible": fc["m1_feasible"], "m2_feasible": m2,
                    "features_for_m2": feats,
                    "reason": _det_reason(cat[l], fc),
                    "checks_m2": fc["checks_m2"], "m2_control_reason": fc["m2_reason"],
                    "by": "agent" if plan else "control"})
    spec = company_spec(ticker)
    return {"ticker": ticker, "company": spec["company"], "period": spec["period"],
            "agent": bool(plan), "provision": out}
