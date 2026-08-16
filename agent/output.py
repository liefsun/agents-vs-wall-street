"""Output layer — the explicit contract for what the pipeline must emit, plus one
run that pushes all four companies through the same pipeline to produce it.

The point of a declared output layer (mirroring the lab's constitutional P5):
downstream never has to guess the deliverable. `output_spec()` is the single
source of truth for WHAT we owe the challenge; `run_pipeline()` is the single
command that produces it for all four companies at once.
"""
from __future__ import annotations

import datetime
import os

from . import methodology, selection, workbook
from .forecast import _companies_json, company_spec


def _stamp() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

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


def run_pipeline(write: bool = False, selection_mode: str = selection.GUARDED_NESTED_MODE) -> dict:
    """Run all four companies through the guarded Methodology 1 pipeline.
    Returns a manifest; if write=True also emits the workbooks to submission/."""
    started = _stamp()
    stages = [(started, f"loaded manifest — {len(TICKERS)} companies, "
                        f"{sum(len(company_spec(t)['metrics']) for t in TICKERS)} target numbers")]
    companies = []
    for t in TICKERS:
        spec = company_spec(t)
        d = selection.forecast(t, mode=selection_mode)
        from . import methodology_compare as mc
        metrics = []
        for m in spec["metrics"]:
            mm = d["metrics"].get(m["label"])
            metric = {"label": m["label"], "units": m["units"],
                      "point": mm["point"] if mm else None,
                      "kind": mm["kind"] if mm else None,
                      "band": mm["band"] if mm else None,
                      "basis": mm["basis"] if mm else None,
                      "sources": mm["sources"] if mm else [],
                      "selection": mm.get("selection") if mm else None,
                      "direct_point": mm.get("direct_point") if mm else None}
            # Dual-methodology: compare Methodology 2 (analogue) against the SUBMITTED
            # guarded-nested Methodology 1 in the same causal skill frame; switch to M2 only
            # where its measured out-of-sample skill is clearly higher (else keep M1).
            if metric["point"] is not None and metric["kind"]:
                sel = metric.get("selection") or {}
                choice = mc.m2_vs_m1_skill(t, m["label"], metric["kind"], sel.get("outer_skill"))
                metric["m2_decision"] = choice
                if choice.get("use_m2"):
                    metric["m1_point"] = metric["point"]
                    metric["point"] = choice["m2_point"]
                    metric["selection"] = {**sel, "source": "methodology-2",
                                           "outer_skill": choice["m2_skill"],
                                           "m2_skill": choice["m2_skill"], "m1_skill": choice.get("m1_skill"),
                                           "outer_origins": choice.get("m2_origins"),
                                           "methodology": "Methodology 2 · historical analogue"}
            metrics.append(metric)
        # deterministic reconciliation guard — blend toward issued guidance where the model
        # wanders off it (accuracy), flag anchorless large disagreements (safety). Runs before
        # the workbook is written so the guarded numbers are what ship.
        from . import reconcile
        recon = reconcile.apply(t, metrics)
        path = workbook.write_direct(spec["outputFile"], spec["period"], metrics) if write else None
        proc = _stamp()
        n_nested = sum(1 for m in metrics if (m.get("selection") or {}).get("source") == "nested")
        got = sum(1 for m in metrics if m["point"] is not None)
        n_guard = sum(1 for r in recon if r["action"] == "guidance-guard")
        stages.append((proc, f"{t}: {got}/{len(metrics)} numbers ({n_nested} nested, "
                             f"{got - n_nested} direct" + (f", {n_guard} guidance-guarded" if n_guard else "") + ")"
                             + (f" → wrote {os.path.basename(path)}" if path else "")))
        companies.append({"ticker": t, "company": spec["company"], "period": spec["period"],
                          "file": spec["outputFile"], "wired": bool(d["metrics"]),
                          "written": path, "processed_at": proc, "metrics": metrics,
                          "reconciliation": recon})
    filled = sum(1 for f in companies for m in f["metrics"] if m["point"] is not None)
    total = sum(len(f["metrics"]) for f in companies)
    report_paths = selection.write_nested_report() if write and selection_mode != selection.DIRECT_MODE else None
    finished = _stamp()
    if report_paths:
        stages.append((finished, "wrote nested-parameter-evaluation report"))
    dur = (datetime.datetime.fromisoformat(finished) - datetime.datetime.fromisoformat(started)).total_seconds()
    manifest = {"companies": companies, "n_filled": filled, "n_total": total,
                "selection_mode": selection_mode, "nested_report": report_paths,
                "started_at": started, "finished_at": finished, "duration_s": dur, "stages": stages,
                "wired": sum(1 for f in companies if f["wired"]),
                "ready": all(f["wired"] and all(m["point"] is not None for m in f["metrics"])
                             for f in companies)}
    if write:
        # Emit the clear-run evidence log alongside the workbooks (SUBMISSION.md).
        from . import runlog
        manifest["run_log"] = runlog.write_log(manifest)
    return manifest
