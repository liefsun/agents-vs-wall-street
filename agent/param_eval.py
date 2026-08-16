"""Parameter eval — pulled from quant-projects (garch_var `compare_models` +
regime_signal `sensitivity_analysis`).

For each metric with a backtestable series we:
  · compare a GRID of candidate models by prequential (walk-forward) error, rank them,
    pick the best and check whether it beats the Seasonal-Naive baseline
    (the `compare_models` GARCH-vs-EGARCH-vs-Constant analog), and
  · run a sensitivity grid over the backtest window to see if the winner is robust or
    fragile (the `sensitivity_analysis` threshold×exposure grid analog).

This is the "which model / parameter is best, and is it robust" evaluation the
single-model backtest was missing.
"""
from __future__ import annotations

from . import candidates, prequential

# candidate models to compare; seasonal_naive is the mandatory baseline (like 'Constant')
_CANDIDATES = {
    "seasonal_naive": candidates.seasonal_naive,
    "naive_last": candidates.naive_last,
    "drift_mult": candidates.drift_mult,
    "drift_add": candidates.drift_add,
    "trend_mult": candidates.trend_mult,
    "ar_lag": candidates.ar_lag,
    "ets_hw": candidates.ets_hw,
}


def _err(r: dict) -> float:
    if r.get("insufficient"):
        return float("inf")
    return r["mae"] if r.get("kind") == "pct" else r["wape"]


def compare(ticker: str, label: str, kind: str) -> dict:
    """compare_models analog: rank candidate models by prequential out-of-sample error."""
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return {"insufficient": True}
    gbk = prequential.guidance_for(ticker, label)
    rows = []
    for name, fn in _CANDIDATES.items():
        r = prequential.run(axis, values, kind, model_fn=fn, model_name=name)
        if not r.get("insufficient"):
            rows.append({"model": name, "err": _err(r), "kind": kind, "wape": r["wape"],
                         "mae": r["mae"], "n": r["n_origins"], "kupiec": r.get("kupiec_pvalue")})
    if gbk:                                            # guidance competes too, where issued
        r = prequential.run(axis, values, kind, approach="guidance", guidance_by_key=gbk)
        if not r.get("insufficient"):
            rows.append({"model": "guidance", "err": _err(r), "kind": kind, "wape": r["wape"],
                         "mae": r["mae"], "n": r["n_origins"], "kupiec": r.get("kupiec_pvalue")})
    if not rows:
        return {"insufficient": True}
    rows.sort(key=lambda x: x["err"])
    best = rows[0]
    baseline = next((x for x in rows if x["model"] == "seasonal_naive"), None)
    errs = [x["err"] for x in rows]
    sens = sensitivity(ticker, label, kind, best["model"])
    return {"insufficient": False, "kind": kind, "rows": rows, "n_models": len(rows),
            "best": best["model"], "best_err": best["err"],
            "baseline_err": (baseline["err"] if baseline else None),
            "beats_baseline": bool(baseline and best["err"] < baseline["err"]),
            "spread": max(errs) - min(errs), "sensitivity": sens}


def sensitivity(ticker: str, label: str, kind: str, model_name: str | None = None) -> dict | None:
    """sensitivity_analysis analog: grid over the backtest window; report the error range."""
    axis, values = prequential.series_for(ticker, label)
    if not axis:
        return None
    fn = _CANDIDATES.get(model_name)
    saved = prequential.ORIGIN_WINDOW
    out = []
    try:
        for w in (12, 16, 20, 24):
            prequential.ORIGIN_WINDOW = w
            r = (prequential.run(axis, values, kind, model_fn=fn, model_name=model_name) if fn
                 else prequential.run(axis, values, kind,
                                      approach="guidance", guidance_by_key=prequential.guidance_for(ticker, label)))
            if not r.get("insufficient"):
                out.append({"window": w, "err": _err(r)})
    finally:
        prequential.ORIGIN_WINDOW = saved
    if not out:
        return None
    errs = [o["err"] for o in out]
    rng = max(errs) - min(errs)
    return {"grid": out, "range": rng, "min": min(errs), "max": max(errs),
            "robust": rng < (2.0 if kind == "pct" else 0.10)}


def compare_all() -> list[dict]:
    from .forecast import company_spec, METRIC_MAP
    from .prequential import _kind_from_units
    rows = []
    for t in ("HD", "ADI", "HAS", "DE"):
        spec = company_spec(t)
        for m in spec["metrics"]:
            kind = METRIC_MAP.get(t, {}).get(m["label"], (None, None))[1] or _kind_from_units(m["units"])
            c = compare(t, m["label"], kind)
            rows.append({"ticker": t, "company": spec["company"], "label": m["label"],
                         "units": m["units"], **c})
    return rows
