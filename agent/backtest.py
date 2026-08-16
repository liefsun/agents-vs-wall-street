"""Rolling-origin backtest + capped ensemble — ported verbatim in spirit from the
lab pipeline's forecast_metric, with two additions for this challenge:

  * `guidance` competes as a candidate model. It is exogenous (the number the
    company published for the next period), aligned by absolute fiscal key so the
    backtest stays strictly point-in-time: to "predict" period t we use only the
    guidance that was issued at t-1.
  * loss is metric-kind aware: money -> WAPE, eps -> MAE, pct -> MAE (in points).

Gate: any model that cannot beat Seasonal Naive is dropped. Survivors form a
capped inverse-error ensemble (no model > 60%). If everything fails, fall back to
the best validated baseline. Deterministic, reproducible, auditable.
"""
from __future__ import annotations

import numpy as np

from . import governance

WEIGHT_CAP = 0.60
MIN_TRAIN = 8          # a bit lower than the lab's 12: several metrics have ~20 clean quarters
MIN_ORIGINS = 6
ORIGIN_WINDOW = 16     # score only the most recent N origins — old history (mega-acquisition
                       # step-changes: ADI/Linear'17, ADI/Maxim'21) is a different regime and
                       # would otherwise dominate every model's error and wash out discrimination.
GUIDANCE_KEY = "guidance"
GUIDANCE_LABEL = "Company guidance (issued t-1)"


def _series(axis, values):
    """Trim to first..last known, linearly interpolate interior gaps (keeps the
    seasonal t-4 index aligned), return (axis2, y, filled)."""
    idx = [i for i, v in enumerate(values) if v is not None]
    if len(idx) < 2:
        return [], [], []
    lo, hi = idx[0], idx[-1]
    axis2 = axis[lo:hi + 1]
    seg = values[lo:hi + 1]
    xs = [i for i, v in enumerate(seg) if v is not None]
    vs = [float(v) for v in seg if v is not None]
    y, filled = [], []
    for i in range(len(seg)):
        if seg[i] is not None:
            y.append(float(seg[i])); filled.append(False)
        else:
            y.append(float(np.interp(i, xs, vs))); filled.append(True)
    return axis2, y, filled


def _score(pairs, kind):
    a = np.array([p[0] for p in pairs], float)
    p = np.array([p[1] for p in pairs], float)
    if kind == "money":
        denom = float(np.sum(np.abs(a))) or 1.0
        return float(np.sum(np.abs(a - p)) / denom)     # WAPE
    return float(np.mean(np.abs(a - p)))                # MAE (eps / pct-points)


def _cap(w, cap=WEIGHT_CAP):
    w = dict(w)
    for _ in range(12):
        over = {k: v for k, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            w[k] = cap
        under = {k: v for k, v in w.items() if k not in over}
        tot = sum(under.values())
        if tot <= 0:
            break
        for k in under:
            w[k] += excess * under[k] / tot
    s = sum(w.values())
    return {k: v / s for k, v in w.items()} if s > 0 else w


def forecast_metric(axis, values, kind, guidance_by_key=None, models=None):
    """Backtest every candidate on the series, gate + capped ensemble, next-period point.

    axis: absolute fiscal keys ; values: aligned actuals (None where missing).
    kind: 'money' | 'eps' | 'pct'. guidance_by_key: {target_key: issued_value}.
    models: list of governance.ModelNode (defaults to the active registry for this kind),
            so hot-swapped JSON nodes compete automatically.
    """
    guidance_by_key = guidance_by_key or {}
    models = models if models is not None else governance.active_models(kind)
    mmap = {m.id: m for m in models}
    BASELINE = governance.BASELINE
    axis2, y, filled = _series(axis, values)
    if len(y) < MIN_TRAIN + 1:
        return {"kind": kind, "point": None, "insufficient": True, "n_used": len(y)}

    errs = {m.id: [] for m in models}
    errs[GUIDANCE_KEY] = []
    start = max(MIN_TRAIN, len(y) - ORIGIN_WINDOW)      # trailing scoring window (current regime)
    for t in range(start, len(y)):
        if filled[t]:                                   # never score against an interpolated actual
            continue
        train, actual, tkey = y[:t], y[t], axis2[t]
        for m in models:
            p = m.predict(train)
            if p is not None and np.isfinite(p):
                errs[m.id].append((actual, p))
        g = guidance_by_key.get(tkey)
        if g is not None and np.isfinite(g):
            errs[GUIDANCE_KEY].append((actual, float(g)))

    counts = {k: len(v) for k, v in errs.items()}
    scores = {k: (_score(v, kind) if v else None) for k, v in errs.items()}
    naive_err = scores.get(BASELINE)

    survivors = {k: s for k, s in scores.items()
                 if s is not None and counts[k] >= MIN_ORIGINS
                 and (naive_err is None or s <= naive_err * 1.0001)}
    fallback = not survivors
    if fallback:
        survivors = {BASELINE: naive_err} if naive_err is not None else {}
    inv = {k: 1.0 / max(s, 1e-9) for k, s in survivors.items()}
    tot = sum(inv.values()) or 1.0
    weights = _cap({k: v / tot for k, v in inv.items()})

    # ── final point: predict the next period after the last actual ──
    target_key = axis2[-1] + 1
    final_pred = {}
    for m in models:
        pv = m.predict(y)
        if pv is not None and np.isfinite(pv):
            final_pred[m.id] = float(pv)
    gfin = guidance_by_key.get(target_key)
    if gfin is not None and np.isfinite(gfin):
        final_pred[GUIDANCE_KEY] = float(gfin)

    point, ens_err = None, None
    if weights:
        num, wsum = 0.0, 0.0
        for k, w in weights.items():
            pv = final_pred.get(k)
            if pv is None:
                pv = final_pred.get(BASELINE)
            if pv is not None:
                num += w * pv; wsum += w
        if wsum > 0:
            point = num / wsum
            ens_err = sum(weights[k] * scores[k] for k in weights if scores.get(k) is not None)

    band = None
    if point is not None and ens_err is not None:
        band = (point * (1 - ens_err), point * (1 + ens_err)) if kind == "money" else (point - ens_err, point + ens_err)

    def _lbl(k):
        if k == GUIDANCE_KEY:
            return GUIDANCE_LABEL
        return mmap[k].label if k in mmap else k

    def _plug(k):
        if k == GUIDANCE_KEY:
            return "hot"
        return mmap[k].plug if k in mmap else "code"

    leaderboard = [{"model": k, "label": _lbl(k), "plug": _plug(k), "error": scores[k],
                    "origins": counts[k], "eligible": k in survivors,
                    "weight": round(weights.get(k, 0.0), 3), "final_pred": final_pred.get(k)}
                   for k in [m.id for m in models] + [GUIDANCE_KEY]]
    leaderboard.sort(key=lambda r: (r["error"] is None, r["error"] if r["error"] is not None else 9e9))

    return {"kind": kind, "point": point, "band": band, "ens_error": ens_err,
            "baseline_error": naive_err, "weights": weights, "leaderboard": leaderboard,
            "n_used": len(y), "n_origins": max(counts.values()) if counts else 0,
            "target_key": target_key, "fallback": fallback, "insufficient": False}
