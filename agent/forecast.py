"""Orchestration: panel -> per-metric rolling-origin forecast -> fused point + band.

Maps the challenge's exact metric labels/units (from challenge/companies.json) to
the internal extractor keys, runs the backtest+ensemble per metric, and packages a
result with the guidance anchor and the evidence trail for the demo app + workbook.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import extract
from .backtest import forecast_metric
from .corpus import ROOT

# challenge metric label -> (internal extractor key, loss kind)
#   kind: money (WAPE), eps (MAE $), pct (MAE points)
METRIC_MAP = {
    "ADI": {
        "Revenue": ("revenue", "money"),
        "Adjusted gross margin": ("adj_gross_margin", "pct"),
        "Adjusted diluted EPS": ("adj_eps", "eps"),
    },
    # HD / DE / HAS extractors follow the same shape (added next).
}


def _companies_json() -> dict:
    with open(os.path.join(ROOT, "challenge", "companies.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def company_spec(ticker: str) -> dict:
    for c in _companies_json()["companies"]:
        if c["ticker"].split(":")[-1] == ticker:
            return c
    raise KeyError(ticker)


@dataclass
class MetricForecast:
    label: str
    units: str
    internal: str
    kind: str
    point: float | None
    band: tuple | None
    guidance_anchor: float | None
    result: dict = field(default_factory=dict)      # full backtest payload (leaderboard etc.)
    series: dict = field(default_factory=dict)       # axis + values for the chart
    evidence: list = field(default_factory=list)


def _guidance_by_key(panel, internal_metric) -> dict:
    """{target_period_key: guidance value the company issued for it}."""
    out = {}
    for r in panel:
        g = r.guidance_next.get(internal_metric)
        if g is not None:
            out[r.key + 1] = g
    return out


def forecast_company(ticker: str) -> dict:
    spec = company_spec(ticker)
    panel = extract.build_panel(ticker)
    mmap = METRIC_MAP.get(ticker, {})
    metrics: list[MetricForecast] = []
    for m in spec["metrics"]:
        label, units = m["label"], m["units"]
        internal, kind = mmap.get(label, (None, "money"))
        if internal is None:
            metrics.append(MetricForecast(label, units, "", kind, None, None, None,
                                          {"unmapped": True}, {}, []))
            continue
        axis, vals = extract.metric_series(panel, internal)
        gbk = _guidance_by_key(panel, internal)
        res = forecast_metric(axis, vals, kind, gbk)
        anchor = gbk.get(res.get("target_key")) if not res.get("insufficient") else None
        ev = [r.evidence.get(f"actual.{internal}") for r in panel[-4:] if r.evidence.get(f"actual.{internal}")]
        metrics.append(MetricForecast(
            label=label, units=units, internal=internal, kind=kind,
            point=res.get("point"), band=res.get("band"), guidance_anchor=anchor,
            result=res, series={"axis": axis, "values": vals}, evidence=ev,
        ))
    return {"ticker": ticker, "company": spec["company"], "period": spec["period"],
            "output_file": spec["outputFile"], "panel_rows": len(panel), "metrics": metrics}
