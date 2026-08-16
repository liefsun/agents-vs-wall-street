"""Non-nested candidate-model diagnostic retained for UI compatibility.

For each metric with a backtestable series we:
  · compare a GRID of candidate models by prequential (walk-forward) error, rank them,
    pick the best and check whether it beats the Seasonal-Naive baseline
    (the `compare_models` GARCH-vs-EGARCH-vs-Constant analog), and
  · run a sensitivity grid over the backtest window to see if the winner is robust or
    fragile (the `sensitivity_analysis` threshold×exposure grid analog).

Formal parameter conclusions live in :mod:`agent.parameter_evaluation`; this module
only screens individual model functions and must not be cited as unbiased uplift.
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
    return r["mae"]


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
    out = []
    for window in (12, 16, 20, 24):
        r = (
            prequential.run(
                axis,
                values,
                kind,
                model_fn=fn,
                model_name=model_name,
                origin_window=window,
            )
            if fn
            else prequential.run(
                axis,
                values,
                kind,
                approach="guidance",
                guidance_by_key=prequential.guidance_for(ticker, label),
                origin_window=window,
            )
        )
        if not r.get("insufficient"):
            out.append({"window": window, "err": _err(r)})
    if not out:
        return None
    errs = [o["err"] for o in out]
    rng = max(errs) - min(errs)
    relative_range = rng / max(min(errs), 1e-9)
    return {"grid": out, "range": rng, "min": min(errs), "max": max(errs),
            "relative_range": relative_range, "robust": relative_range < 0.25}


def compare_all() -> list[dict]:
    from .forecast import METRIC_MAP, company_spec
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
