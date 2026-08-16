"""Methodology 2 core — historical-analogue matching (point-in-time).

Builds a PIT snapshot of the current operating state, finds the K historical quarters
whose (standardised) state is closest, and uses their realized NEXT-period YoY growth
as the forward-outcome sample. Similarity × recency weighting. Everything is strictly
point-in-time: predicting index k uses only y[:k]; an analogue at t is only usable once
its next period t+1 is already known (t+1 ≤ k−1). Deterministic (no RNG).

Financial-only snapshot for now (derivable from a single metric series); the richer
guidance/margin/qualitative features in METHODOLOGY_2 are staged.
"""
from __future__ import annotations

import math

import numpy as np

from . import scenarios

FEATURES = ["yoy", "qoq", "mom1", "mom2", "vol"]


def _snapshot(y, t) -> dict | None:
    """PIT feature vector at index t (uses y[:t+1] only)."""
    if t < 5:
        return None
    yoy = (y[t] / y[t - 4] - 1) if (t >= 4 and y[t - 4]) else 0.0
    qoq = (y[t] / y[t - 1] - 1) if y[t - 1] else 0.0
    mom1 = ((y[t] - y[t - 1]) / abs(y[t - 1])) if y[t - 1] else 0.0
    mom2 = ((y[t] - y[t - 2]) / abs(y[t - 2])) if y[t - 2] else 0.0
    gs = [y[i] / y[i - 4] - 1 for i in range(max(4, t - 8), t + 1) if y[i - 4]]
    vol = float(np.std(gs)) if len(gs) >= 2 else 0.0
    return {"yoy": yoy, "qoq": qoq, "mom1": mom1, "mom2": mom2, "vol": vol}


def _normalize(rows, current):
    """z-score features using mean/std over the training rows (PIT)."""
    arr = {f: np.array([r[1][f] for r in rows], float) for f in FEATURES}
    mu = {f: float(arr[f].mean()) for f in FEATURES}
    sd = {f: (float(arr[f].std()) or 1.0) for f in FEATURES}

    def z(s):
        return {f: (s[f] - mu[f]) / sd[f] for f in FEATURES}

    return [(t, z(s)) for t, s in rows], z(current)


def _dist(a, b, metric="Manhattan"):
    if metric == "Euclidean":
        return math.sqrt(sum((a[f] - b[f]) ** 2 for f in FEATURES))
    return sum(abs(a[f] - b[f]) for f in FEATURES)


def predict(y, k, K=5, distance="Manhattan", half_life=12):
    """Forecast index k of series y using only y[:k] (PIT). Returns point + Bear/Base/Bull
    + the chosen analogues, or None if not enough valid analogues."""
    if k < 8 or k > len(y):
        return None
    current = k - 1
    cur = _snapshot(y, current)
    if not cur:
        return None
    rows = [(t, s) for t in range(5, current) if (t + 1 <= current) for s in [_snapshot(y, t)] if s]
    if len(rows) < 3:
        return None
    normed, cur_n = _normalize(rows, cur)
    hl = None if half_life in ("inf", None) else float(half_life)
    ana = []
    for t, zt in normed:
        tgt = (y[t + 1] / y[t + 1 - 4] - 1) if (t + 1 >= 4 and y[t + 1 - 4]) else None
        if tgt is None:
            continue
        d = _dist(zt, cur_n, distance)
        rec = 1.0 if hl is None else math.exp(-(current - t) / hl)
        ana.append({"t": t, "dist": d, "weight": (1.0 / (1.0 + d)) * rec, "growth": tgt})
    ana.sort(key=lambda a: a["dist"])
    ana = ana[:K]
    if len(ana) < 3:
        return None
    q = scenarios.weighted_quantiles([a["growth"] for a in ana], [a["weight"] for a in ana], [0.2, 0.5, 0.8])
    anchor = y[k - 4] if (k >= 4 and y[k - 4]) else y[current]
    return {"point": anchor * (1 + q[0.5]), "bear": anchor * (1 + q[0.2]),
            "base": anchor * (1 + q[0.5]), "bull": anchor * (1 + q[0.8]),
            "anchor": anchor, "analogues": ana, "n": len(ana),
            "distance": distance, "K": K, "half_life": half_life}
