"""Data catalog — the structured inventory of what data / features are AVAILABLE per
metric. The provisioning agent reasons over THIS (not raw prose), so it is grounded: it
can only claim a feature the catalog actually reports.

Per metric it records: whether Methodology 1 produced a point (and its basis), the length
and quality of the historical series (for Methodology 2's snapshots/analogues), guidance
availability, and feature-quality signals (YoY-growth variance, coverage). Deterministic.
"""
from __future__ import annotations

from . import direct, prequential
from .forecast import company_spec, METRIC_MAP
from .prequential import _kind_from_units
from .backtest import _series


def catalog_metric(ticker, label, kind, m1):
    axis, values = prequential.series_for(ticker, label)
    if axis:
        _, y, filled = _series(axis, values)
        n = len(y)
        coverage = 1.0 - (sum(filled) / n if n else 0.0)
        yoy = [y[i] / y[i - 4] - 1 for i in range(4, n) if y[i - 4]]
        if len(yoy) >= 2:
            mu = sum(yoy) / len(yoy)
            yoy_var = sum((v - mu) ** 2 for v in yoy) / len(yoy)
        else:
            yoy_var = 0.0
        vmin, vmax = (float(min(y)), float(max(y))) if y else (None, None)
    else:
        n, coverage, yoy_var, vmin, vmax = 0, 0.0, 0.0, None, None
    g = prequential.guidance_for(ticker, label)
    return {
        "units": None, "kind": kind,
        "m1_point_available": bool(m1 and m1.get("point") is not None),
        "m1_basis": (m1.get("basis") if m1 else None),
        "series_periods": n,
        "coverage": round(coverage, 2),
        "has_guidance": len(g) > 0,
        "yoy_var": round(yoy_var, 5),
        "value_range": (round(vmin, 2) if vmin is not None else None,
                        round(vmax, 2) if vmax is not None else None),
        "snapshot_ok": n >= 14,
        "analogue_ok": n >= 14,
    }


def catalog(ticker: str) -> dict:
    d = direct.forecast(ticker)
    spec = company_spec(ticker)
    out = {}
    for m in spec["metrics"]:
        lbl = m["label"]
        kind = METRIC_MAP.get(ticker, {}).get(lbl, (None, None))[1] or _kind_from_units(m["units"])
        c = catalog_metric(ticker, lbl, kind, d["metrics"].get(lbl))
        c["units"] = m["units"]
        out[lbl] = c
    return out
