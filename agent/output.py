"""Output layer — the explicit contract for what the pipeline must emit, plus one
run that pushes all four companies through the same pipeline to produce it.

The point of a declared output layer (mirroring the lab's constitutional P5):
downstream never has to guess the deliverable. `output_spec()` is the single
source of truth for WHAT we owe the challenge; `run_pipeline()` is the single
command that produces it for all four companies at once.
"""
from __future__ import annotations

from . import workbook, direct, methodology
from .forecast import company_spec, _companies_json

TICKERS = ["HD", "ADI", "HAS", "DE"]


def output_spec() -> dict:
    """Declarative deliverable, derived from challenge/companies.json (the truth)."""
    files = []
    for c in _companies_json()["companies"]:
        t = c["ticker"].split(":")[-1]
        files.append({
            "ticker": t, "company": c["company"], "period": c["period"],
            "file": c["outputFile"], "wired": bool(methodology.adapter(t).get("metrics")),
            "metrics": [{"label": m["label"], "units": m["units"]} for m in c["metrics"]],
        })
    return {
        "deliverable": "Four OpenStocks workbooks written to submission/",
        "files": files,
        "n_numbers": sum(len(f["metrics"]) for f in files),
        "final_command": "uv run --with-requirements agent/requirements.txt python -m agent.run",
        "checker": "npm run check:submission",
        "upload": "Manual upload of each .xlsx to its OpenStocks Forecast Model (no programmatic submit).",
        "contract": [
            "Start from the supplied template; keep the Summary sheet, metric labels, units and period column unchanged.",
            "Header row: 'Metric | Units | <fiscal period>'.",
            "Each metric row: label + units match exactly; the value in the period column is a finite number.",
            "Percentages entered as points (4.5 = 4.5%). Hays EPS in pence (GBp). Money in USDm / GBPm.",
            "One final command produces all four files; scored vs Wall Street (cap 5.0 per metric).",
        ],
    }


def run_pipeline(write: bool = False) -> dict:
    """Run all four companies through the one pipeline (Methodology 1, direct output).
    Returns a manifest; if write=True also emits the workbooks to submission/."""
    companies = []
    for t in TICKERS:
        spec = company_spec(t)
        d = direct.forecast(t)
        metrics = []
        for m in spec["metrics"]:
            mm = d["metrics"].get(m["label"])
            metrics.append({"label": m["label"], "units": m["units"],
                            "point": mm["point"] if mm else None,
                            "kind": mm["kind"] if mm else None,
                            "band": mm["band"] if mm else None,
                            "basis": mm["basis"] if mm else None,
                            "sources": mm["sources"] if mm else []})
        path = workbook.write_direct(spec["outputFile"], spec["period"], metrics) if write else None
        companies.append({"ticker": t, "company": spec["company"], "period": spec["period"],
                          "file": spec["outputFile"], "wired": bool(d["metrics"]),
                          "written": path, "metrics": metrics})
    filled = sum(1 for f in companies for m in f["metrics"] if m["point"] is not None)
    total = sum(len(f["metrics"]) for f in companies)
    return {"companies": companies, "n_filled": filled, "n_total": total,
            "wired": sum(1 for f in companies if f["wired"]),
            "ready": all(f["wired"] and all(m["point"] is not None for m in f["metrics"])
                         for f in companies)}
