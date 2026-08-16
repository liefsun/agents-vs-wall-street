"""Stats control — validate each model-approach output before it is written.

Runs AFTER the model approaches, BEFORE the output layer (Methodology 1 §11 units +
consistency checks; §13 never hide failures). Every number gets a verdict:
  pass  — all checks OK
  warn  — soft issue (wide band, near a bound) — surfaced, not blocking
  fail  — hard issue (non-finite, out of range, wrong sign) — surfaced, still written but flagged

This is the deferred backtesting layer's stand-in for the current direct form: not a
rolling-origin backtest, but a deterministic control gate on the produced numbers.
"""
from __future__ import annotations

import math

# kind → plausible bounds for a single company-quarter figure
BOUNDS = {"money": (0.0, 5_000_000.0), "eps": (-20.0, 60.0), "pct": (-60.0, 100.0)}

CHECKS_DOC = [
    "finite — the point is a finite number",
    "range — within plausible bounds for the metric kind (margin 0–100%)",
    "sign — money figures are positive",
    "band — the point sits inside its own uncertainty band",
    "band-width — the band is not implausibly wide (money ≤ ~40%)",
]


def _validate_one(label: str, m: dict) -> dict:
    pt = m.get("point")
    kind = m.get("kind") or "money"
    band = m.get("band")
    checks = []

    def add(name, ok, msg, hard=False):
        checks.append({"name": name, "ok": bool(ok), "msg": msg, "hard": hard})

    finite = pt is not None and isinstance(pt, (int, float)) and math.isfinite(pt)
    add("finite", finite, "point is finite" if finite else "point missing / non-finite", hard=True)

    if finite:
        lo, hi = BOUNDS.get(kind, (-1e18, 1e18))
        if kind == "pct" and "margin" in label.lower():
            lo, hi = 0.0, 100.0
        add("range", lo <= pt <= hi, f"{pt} in [{lo:g}, {hi:g}] ({kind})", hard=True)
        if kind == "money":
            add("sign", pt > 0, "money value positive" if pt > 0 else "money value not positive", hard=True)
        if band:
            add("band", band[0] <= pt <= band[1], f"point inside band [{band[0]:g}, {band[1]:g}]")
            width = (band[1] - band[0]) / abs(pt) if pt else 0.0
            add("band-width", (width <= 0.4 if kind == "money" else True),
                f"band width {width:.0%}")

    hard_fail = any((not c["ok"] and c["hard"]) for c in checks)
    soft_fail = any((not c["ok"] and not c["hard"]) for c in checks)
    verdict = "fail" if hard_fail else ("warn" if soft_fail else "pass")
    return {"verdict": verdict, "checks": checks}


def validate(metrics: list[dict]) -> dict:
    """metrics: list of {label, kind, point, band}. Returns {label: {verdict, checks}}."""
    return {m["label"]: _validate_one(m["label"], m) for m in metrics}


def summarize(results: dict) -> dict:
    v = [r["verdict"] for r in results.values()]
    return {"pass": v.count("pass"), "warn": v.count("warn"), "fail": v.count("fail"), "n": len(v)}
