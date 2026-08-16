"""Prequential backtest — pulled from liefsun/quant-projects garch_var/rolling_garch.py
(walk-forward VaR backtest) and adapted to the earnings-forecast metrics.

Prequential = predictive-sequential: walk forward one origin at a time, at each origin
fit only on data available then, forecast the next point, score against the realized
actual. Runs ALONGSIDE the direct output (backtesting is no longer deferred) and emits:
  · point error   — prequential MAE / RMSE / WAPE
  · band coverage — VaR-style breach test: a "breach" is a realized value outside the
                    ex-ante forecast band (built from past residuals only, so PIT-clean)
  · Kupiec POF    — likelihood-ratio test that the breach rate matches the expected rate
                    (chi²₁ p-value via math.erf — no scipy)

The quant-projects VaR logic (breach counting + Kupiec LR) is preserved; here the
"loss" is a forecast miss rather than a return exceeding VaR.
"""
from __future__ import annotations

import math

import numpy as np

from . import candidates, extract, history
from .backtest import _series

# z for a symmetric central band (P(|Z|<z) = conf)
_Z = {0.80: 1.2816, 0.90: 1.6449, 0.95: 1.9600}
MIN_TRAIN = 8
ORIGIN_WINDOW = 24          # trailing scoring window — dodge old-regime contamination (acquisitions)


def _kupiec(n: int, n_breach: int, p0: float):
    """Kupiec proportion-of-failures LR test. Returns chi²₁ p-value (or None)."""
    if not (0 < n_breach < n):
        return None
    pr = n_breach / n
    lr = -2 * (n_breach * math.log(p0) + (n - n_breach) * math.log(1 - p0)
               - n_breach * math.log(pr) - (n - n_breach) * math.log(1 - pr))
    return float(1 - math.erf(math.sqrt(max(lr, 0) / 2)))     # chi2.cdf(x,1) = erf(sqrt(x/2))


def _drift_for(kind: str, season: int):
    producer = candidates.drift_add if kind == "pct" else candidates.drift_mult

    def predict(values):
        return producer(values, season=season)

    return predict, producer.__name__


# adapter approach -> is it a guidance replay?
_GUIDANCE_APPROACHES = {"guidance", "guide_reversion", "stated"}


def run(axis, values, kind: str, approach: str | None = None,
        guidance_by_key: dict | None = None, conf: float = 0.80,
        model_fn=None, model_name: str | None = None,
        origin_window: int = ORIGIN_WINDOW, season: int = candidates.SEASON) -> dict:
    """Walk-forward prequential backtest that REPLAYS THE ACTUAL APPROACH.

    - guidance approaches: at each origin predict with the guidance issued for that
      period (only scored where historical guidance exists) — so the backtest reflects
      the method that ships, not a generic drift proxy.
    - otherwise: seasonal-drift on the series.
    Trailing ORIGIN_WINDOW avoids old-regime (mega-acquisition) contamination.
    """
    guidance_by_key = guidance_by_key or {}
    axis2, y, filled = _series(axis, values, season=season)
    if len(y) < MIN_TRAIN + season:
        return {"insufficient": True, "n": len(y),
                "reason": f"series too short ({len(y)} periods) — need ≥{MIN_TRAIN + season}"}
    drift, drift_name = _drift_for(kind, season)
    z = _Z.get(conf, 1.2816)
    use_guidance = (model_fn is None) and approach in _GUIDANCE_APPROACHES and bool(guidance_by_key)

    start = max(MIN_TRAIN, len(y) - origin_window)
    pairs, resid_hist, breaches = [], [], []
    for t in range(start, len(y)):
        if filled[t]:
            continue
        a, tkey = y[t], axis2[t]
        if model_fn is not None:                   # parameter-eval: an arbitrary candidate model
            p = model_fn(y[:t])
        elif use_guidance:
            p = guidance_by_key.get(tkey)          # score only where guidance was issued
            if p is None:
                continue
        else:
            p = drift(y[:t])
        if p is None or not np.isfinite(p):
            continue
        if len(resid_hist) >= 4:                   # ex-ante band from PIT residuals
            s = float(np.std(resid_hist)) or 1e-9
            breaches.append(abs(a - p) > z * s)
        resid_hist.append(a - p)
        pairs.append((a, p))

    if len(pairs) < 8:
        return {"insufficient": True, "n": len(y),
                "reason": f"too few scoreable origins ({len(pairs)}) — need ≥8"}
    a = np.array([x[0] for x in pairs], float)
    p = np.array([x[1] for x in pairs], float)
    err = a - p
    nb, N = int(sum(breaches)), len(breaches)
    expected = 1 - conf
    return {"insufficient": False, "n_origins": len(pairs), "kind": kind,
            "model": (model_name or ("guidance (issued t-1)" if use_guidance else drift_name)),
            "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "wape": float(np.sum(np.abs(err)) / (np.sum(np.abs(a)) or 1.0)),
            "conf": conf, "coverage_n": N, "n_breach": nb,
            "breach_rate": (nb / N) if N else None, "expected_breach": expected,
            "kupiec_pvalue": (_kupiec(N, nb, expected) if N else None)}


# ── target histories ─────────────────────────────────────────────────────────────
_ADI_MAP = {"Revenue": "revenue", "Adjusted gross margin": "adj_gross_margin",
            "Adjusted diluted EPS": "adj_eps"}

# specific reasons where a clean history doesn't exist (honest, per Methodology 1 §13)
_NO_SERIES_REASON = {
    ("HD", "Adjusted diluted EPS"): (
        "only seven exact adjusted-EPS observations exist in the frozen corpus; "
        "GAAP EPS is not substituted"
    ),
}


def series_for(ticker: str, label: str):
    """(axis, values) for a metric where we have a series, else (None, None)."""
    historical = history.series_for(ticker, label)
    return historical.axis_values() if historical else (None, None)


def history_for(ticker: str, label: str) -> history.HistoricalSeries | None:
    """Return the provenance-bearing history used by the backtest."""

    return history.series_for(ticker, label)


def guidance_for(ticker: str, label: str) -> dict:
    """{target_period_key: guidance the company issued for it} — lets the backtest
    REPLAY the guidance approach instead of a generic drift proxy."""
    if ticker == "ADI" and label in _ADI_MAP:
        internal = _ADI_MAP[label]
        out = {}
        for r in extract.build_panel("ADI"):
            g = r.guidance_next.get(internal)
            if g is not None:
                out[r.key + 1] = g
        return out
    return {}


def backtest_metric(ticker: str, label: str, kind: str) -> dict:
    historical = history_for(ticker, label)
    axis, values = historical.axis_values() if historical else (None, None)
    if not axis:
        return {"insufficient": True,
                "reason": _NO_SERIES_REASON.get((ticker, label), "no historical series for this metric yet")}
    from . import methodology
    approach = methodology.metric_plan(ticker, label).get("approach")
    return run(
        axis,
        values,
        kind,
        approach=approach,
        guidance_by_key=guidance_for(ticker, label),
        season=historical.season,
    )


def _kind_from_units(units: str) -> str:
    u = (units or "").strip().lower()
    if "share" in u or u == "gbp":          # "USD / share", or Hays EPS in pence "GBp"
        return "eps"
    if "%" in u:
        return "pct"
    return "money"


def headline_error(r: dict) -> str:
    """MAE-first headline; percentage metrics are expressed in points."""
    if r.get("kind") == "pct":
        return f"MAE {r['mae']:.2f}pp"
    return f"MAE {r['mae']:.3g}"


def analyze(r: dict) -> str:
    """Plain-language read of a backtest result — the 'analysis' the run log can't hold."""
    if r.get("insufficient"):
        return r.get("reason", "No historical series — prequential backtest skipped.")
    if r.get("kind") == "pct":
        e = r["mae"]
        grade = "strong" if e < 1.5 else ("moderate" if e < 4 else "weak")
    else:
        e = r["wape"]
        grade = "strong" if e < 0.10 else ("moderate" if e < 0.25 else "weak")
    out = [
        (
            f"Point accuracy: {headline_error(r)} over {r['n_origins']} walk-forward origins "
            f"({grade}; model {r['model']}; WAPE diagnostic {r['wape']:.0%})."
        )
    ]
    kp, br, exp = r.get("kupiec_pvalue"), r.get("breach_rate"), r.get("expected_breach")
    if r.get("coverage_n") and br is not None:
        if kp is None:
            cal = "too few breaches to test calibration"
        elif kp < 0.05:
            cal = ("band too NARROW — under-covers, widen the uncertainty" if br > exp
                   else "band too WIDE — over-covers, tighten the uncertainty")
        else:
            cal = "band well-calibrated"
        kps = f"{kp:.2f}" if kp is not None else "n/a"
        out.append(f"Band calibration: {br:.0%} breach vs {exp:.0%} expected, Kupiec p={kps} → {cal}.")
    return " ".join(out)


def run_all() -> list[dict]:
    """Backtest every target metric (where a series exists). Returns a list of rows."""
    from .forecast import METRIC_MAP, company_spec
    rows = []
    for t in ("HD", "ADI", "HAS", "DE"):
        spec = company_spec(t)
        for m in spec["metrics"]:
            lbl = m["label"]
            kind = METRIC_MAP.get(t, {}).get(lbl, (None, None))[1] or _kind_from_units(m["units"])
            r = backtest_metric(t, lbl, kind)
            rows.append({"ticker": t, "company": spec["company"], "period": spec["period"],
                         "label": lbl, "units": m["units"], "kind": kind,
                         "analysis": analyze(r), **r})
    return rows
