"""Feature control — stats-control on the PROVISIONED features (not just the final
number). Given a catalog entry, decide deterministically whether each methodology's
inputs can be provisioned AND whether the features are meaningful (enough periods,
non-degenerate variance, decent coverage, plausible range). This BOUNDS the provisioning
agent: it can never claim a methodology is feasible if the features don't validate.
"""
from __future__ import annotations

MIN_SERIES = 14
MIN_VAR = 1e-6
MIN_COVERAGE = 0.6


def check(cat: dict) -> dict:
    """Return per-methodology feasibility + the feature checks behind it."""
    m1_ok = cat["m1_point_available"]
    checks_m1 = [("M1 input produced", m1_ok,
                  cat.get("m1_basis") or "adapter guidance/series/bridge")]

    n = cat["series_periods"]
    var_ok = cat["yoy_var"] > MIN_VAR
    cov_ok = cat["coverage"] >= MIN_COVERAGE
    len_ok = n >= MIN_SERIES
    checks_m2 = [
        (f"series ≥ {MIN_SERIES}q", len_ok, f"{n} periods"),
        ("features non-degenerate", var_ok, f"YoY-growth variance {cat['yoy_var']}"),
        (f"coverage ≥ {int(MIN_COVERAGE*100)}%", cov_ok, f"{int(cat['coverage']*100)}%"),
    ]
    m2_ok = len_ok and var_ok and cov_ok

    return {"m1_feasible": bool(m1_ok), "m2_feasible": bool(m2_ok),
            "checks_m1": checks_m1, "checks_m2": checks_m2,
            "m2_reason": (None if m2_ok else
                          ("series too short" if not len_ok else
                           "features degenerate (near-constant)" if not var_ok else
                           "series coverage too low"))}
