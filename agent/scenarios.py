"""Methodology 2 — weighted quantiles → Bear / Base / Bull scenarios.

Deterministic weighted quantiles over the analogues' forward outcomes. Bear = P20,
Base = P50 (default point), Bull = P80. Evidence (calls/slides) would adjust the
scenario probabilities, not the values (staged).
"""
from __future__ import annotations

import numpy as np


def weighted_quantiles(values, weights, qs) -> dict:
    v = np.array(values, float)
    w = np.array(weights, float)
    if v.size == 0:
        return {q: 0.0 for q in qs}
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    cw = cw / cw[-1] if cw[-1] > 0 else np.linspace(0, 1, len(v))
    # midpoint-adjusted cumulative weights for a smoother quantile
    cwm = cw - 0.5 * (w / (w.sum() or 1.0))
    return {q: float(np.interp(q, cwm, v)) for q in qs}


def scenario_probabilities(signals: dict | None = None) -> dict:
    """Bear/Base/Bull probabilities; nudged by a net qualitative signal in [-2, +2]
    (evidence adjusts probabilities, never the numbers). Default is centred on Base."""
    base = {"bear": 0.25, "base": 0.50, "bull": 0.25}
    if not signals:
        return base
    net = max(-2.0, min(2.0, float(signals.get("net", 0.0))))
    shift = 0.06 * net
    p = {"bear": base["bear"] - shift, "base": base["base"], "bull": base["bull"] + shift}
    lo = min(p.values())
    if lo < 0:                                   # keep non-negative
        for k in p:
            p[k] -= lo
    s = sum(p.values())
    return {k: v / s for k, v in p.items()}
