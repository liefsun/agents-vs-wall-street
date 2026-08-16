"""Methodology-level selection — run Methodology 1 and Methodology 2, backtest both
point-in-time PER metric, then gate → select or capped-ensemble → fallback.

Selection granularity is company × period × metric (never one methodology for a whole
company). If M2 can't clear its gate (too few analogues / doesn't beat seasonal-naive /
worse than M1) it falls back to Methodology 1, with the reason recorded.
"""
from __future__ import annotations

import numpy as np

from . import prequential, analogue, candidates
from .backtest import _series

# a single default config; the full K × distance × half-life grid in METHODOLOGY_2 is staged
M2 = {"K": 5, "distance": "Manhattan", "half_life": 12}
WINDOW = 24
MIN_ORIGINS = 6


def _err(a, p, kind):
    a, p = np.array(a, float), np.array(p, float)
    if kind == "pct":
        return float(np.mean(np.abs(a - p)))                       # MAE in points
    return float(np.sum(np.abs(a - p)) / (np.sum(np.abs(a)) or 1))  # WAPE


def m2_predict(y, k):
    return analogue.predict(y, k, M2["K"], M2["distance"], M2["half_life"])


def m2_forecast(ticker, label, kind):
    """Methodology-2 forecast for the next period after the series (point + scenarios).
    Attaches the historical PERIOD to each analogue for the provenance trace."""
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return {"insufficient": True, "reason": "no historical series for analogue matching"}
    axis2, y, _ = _series(axis, values)
    r = m2_predict(y, len(y))
    if not r:
        return {"insufficient": True, "reason": "too few valid analogues"}
    from .extract import key_to_period
    for a in r["analogues"]:
        a["period"] = key_to_period(axis2[a["t"]]) if 0 <= a["t"] < len(axis2) else "?"
    return {"insufficient": False, "kind": kind, **r}


def backtest_m2(ticker, label, kind):
    """Walk-forward PIT backtest of Methodology 2 on a metric series."""
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return {"insufficient": True}
    _, y, filled = _series(axis, values)
    if len(y) < 14:
        return {"insufficient": True}
    start = max(10, len(y) - WINDOW)
    pairs, nan = [], 0
    for k in range(start, len(y)):
        if filled[k]:
            continue
        r = m2_predict(y, k)
        if not r:
            nan += 1
            continue
        pairs.append((y[k], r["point"]))
    if len(pairs) < MIN_ORIGINS:
        return {"insufficient": True, "n": len(pairs)}
    a = [x[0] for x in pairs]
    p = [x[1] for x in pairs]
    return {"insufficient": False, "kind": kind, "n_origins": len(pairs),
            "err": _err(a, p, kind), "model": "analogue+scenarios"}


def _seasonal_naive_err(ticker, label, kind):
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return None
    r = prequential.run(axis, values, kind, model_fn=candidates.seasonal_naive, model_name="seasonal_naive")
    if r.get("insufficient"):
        return None
    return r["mae"] if kind == "pct" else r["wape"]


def compare(ticker, label, kind):
    """Compare M1 (its approach) vs M2 (analogue) PIT → gate → selected + fallback reason."""
    m1 = prequential.backtest_metric(ticker, label, kind)
    m1_err = None if m1.get("insufficient") else (m1["mae"] if kind == "pct" else m1["wape"])
    m2 = backtest_m2(ticker, label, kind)
    m2_err = None if m2.get("insufficient") else m2["err"]
    snaive = _seasonal_naive_err(ticker, label, kind)

    out = {"ticker": ticker, "label": label, "kind": kind,
           "m1_err": m1_err, "m2_err": m2_err, "seasonal_naive_err": snaive,
           "m2_origins": m2.get("n_origins")}

    if m2_err is None:
        out.update(selected="methodology-1", winner="methodology-1", ensemble=False,
                   fallback_reason=(m2.get("reason") or "M2 gate not cleared (too few analogues/origins)"))
        return out
    # M2 gate: must beat seasonal-naive
    if snaive is not None and m2_err > snaive:
        out.update(selected="methodology-1", winner="methodology-1", ensemble=False,
                   fallback_reason="M2 did not beat seasonal-naive")
        return out
    if m1_err is None:
        out.update(selected="methodology-2", winner="methodology-2", ensemble=False, fallback_reason=None)
        return out
    # both valid — select lower error; capped ensemble if within 5% (neither dominates unbounded)
    rel = abs(m1_err - m2_err) / (max(m1_err, m2_err) or 1)
    if rel < 0.05:
        out.update(selected="ensemble", winner="tie", ensemble=True, fallback_reason=None)
    elif m2_err < m1_err:
        out.update(selected="methodology-2", winner="methodology-2", ensemble=False, fallback_reason=None)
    else:
        out.update(selected="methodology-1", winner="methodology-1", ensemble=False,
                   fallback_reason="M1 lower PIT error")
    return out


def compare_all():
    from .forecast import company_spec, METRIC_MAP
    from .prequential import _kind_from_units
    rows = []
    for t in ("HD", "ADI", "HAS", "DE"):
        spec = company_spec(t)
        for m in spec["metrics"]:
            kind = METRIC_MAP.get(t, {}).get(m["label"], (None, None))[1] or _kind_from_units(m["units"])
            rows.append({"units": m["units"], "company": spec["company"], "period": spec["period"],
                         **compare(t, m["label"], kind)})
    return rows


def report_all():
    """Two-methodology comparison per metric: M1 point vs M2 point + Bear/Base/Bull +
    which the PIT gate selected. (Output workbooks still use M1; this is the report.)"""
    from .forecast import company_spec, METRIC_MAP
    from .prequential import _kind_from_units
    from . import direct
    rows = []
    for t in ("HD", "ADI", "HAS", "DE"):
        spec = company_spec(t)
        d = direct.forecast(t)                                   # Methodology 1
        for m in spec["metrics"]:
            lbl = m["label"]
            kind = METRIC_MAP.get(t, {}).get(lbl, (None, None))[1] or _kind_from_units(m["units"])
            m1 = d["metrics"].get(lbl)
            m2 = m2_forecast(t, lbl, kind)                       # Methodology 2 (runs the analogue)
            cmp = compare(t, lbl, kind)
            rows.append({
                "ticker": t, "company": spec["company"], "period": spec["period"],
                "label": lbl, "units": m["units"], "kind": kind,
                "m1_point": (m1["point"] if m1 else None),
                "m2_ok": (not m2.get("insufficient")),
                "m2_point": (m2.get("point")), "m2_bear": m2.get("bear"),
                "m2_base": m2.get("base"), "m2_bull": m2.get("bull"),
                "m2_n": m2.get("n"), "m2_reason": m2.get("reason"),
                "m1_err": cmp["m1_err"], "m2_err": cmp["m2_err"],
                "selected": cmp["selected"], "fallback_reason": cmp.get("fallback_reason"),
            })
    return rows
