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

from . import candidates, extract
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


def _drift_for(kind: str):
    return candidates.drift_add if kind == "pct" else candidates.drift_mult


# adapter approach -> is it a guidance replay?
_GUIDANCE_APPROACHES = {"guidance", "guide_reversion", "stated"}


def run(axis, values, kind: str, approach: str | None = None,
        guidance_by_key: dict | None = None, conf: float = 0.80,
        model_fn=None, model_name: str | None = None) -> dict:
    """Walk-forward prequential backtest that REPLAYS THE ACTUAL APPROACH.

    - guidance approaches: at each origin predict with the guidance issued for that
      period (only scored where historical guidance exists) — so the backtest reflects
      the method that ships, not a generic drift proxy.
    - otherwise: seasonal-drift on the series.
    Trailing ORIGIN_WINDOW avoids old-regime (mega-acquisition) contamination.
    """
    guidance_by_key = guidance_by_key or {}
    axis2, y, filled = _series(axis, values)
    if len(y) < MIN_TRAIN + 4:
        return {"insufficient": True, "n": len(y),
                "reason": f"series too short ({len(y)} periods) — need ≥{MIN_TRAIN + 4}"}
    drift = _drift_for(kind)
    z = _Z.get(conf, 1.2816)
    use_guidance = (model_fn is None) and approach in _GUIDANCE_APPROACHES and bool(guidance_by_key)

    start = max(MIN_TRAIN, len(y) - ORIGIN_WINDOW)
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
            "model": (model_name or ("guidance (issued t-1)" if use_guidance else drift.__name__)),
            "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "wape": float(np.sum(np.abs(err)) / (np.sum(np.abs(a)) or 1.0)),
            "conf": conf, "coverage_n": N, "n_breach": nb,
            "breach_rate": (nb / N) if N else None, "expected_breach": expected,
            "kupiec_pvalue": (_kupiec(N, nb, expected) if N else None)}


# ── which metrics have a usable historical series (ADI full panel + HD releases) ──
_ADI_MAP = {"Revenue": "revenue", "Adjusted gross margin": "adj_gross_margin",
            "Adjusted diluted EPS": "adj_eps"}
_HD_MAP = {"Net sales": "net_sales", "Comparable sales, total company": "comp",
           "Adjusted diluted EPS": "adj_eps"}
_DE_MAP = {"Worldwide net sales and revenues": "net_sales_rev", "Diluted EPS (GAAP)": "eps_gaap"}

# specific reasons where a clean history doesn't exist (honest, per Methodology 1 §13)
_NO_SERIES_REASON = {
    ("HD", "Adjusted diluted EPS"): "HD reports adjusted EPS only since ~2024 (≈8 quarters) — too few for walk-forward",
    ("HD", "Comparable sales, total company"): "comparable-sales history too sparse in parseable form",
    ("DE", "Production & Precision Ag operating profit"): "segment operating profit lives in segment tables — not extracted yet",
    ("HAS", "Net fees"): "Hays reports annually/interim (mixed frequency) — quarterly series not built",
    ("HAS", "Pre-exceptional operating profit"): "Hays annual/interim — series not built",
    ("HAS", "Pre-exceptional basic EPS"): "Hays annual/interim — series not built",
}


def _series_from_periods(period_val: dict):
    kv = sorted((extract.period_key(k), v) for k, v in period_val.items()
                if extract.period_key(k) is not None and v is not None)
    if len(kv) < 4:
        return None, None
    lo, hi = kv[0][0], kv[-1][0]
    d = dict(kv)
    axis = list(range(lo, hi + 1))
    return axis, [d.get(k) for k in axis]


def series_for(ticker: str, label: str):
    """(axis, values) for a metric where we have a series, else (None, None)."""
    if ticker == "ADI" and label in _ADI_MAP:
        panel = extract.build_panel("ADI")
        return extract.metric_series(panel, _ADI_MAP[label])
    if ticker == "HD" and label in _HD_MAP:
        from .direct import _hd_series
        S = _hd_series()
        key = _HD_MAP[label]
        pv = {per: info["row"].get(key) for per, info in S.items()}
        return _series_from_periods(pv)
    if ticker == "DE" and label in _DE_MAP:
        from .direct import _de_series
        S = _de_series()
        key = _DE_MAP[label]
        return _series_from_periods({per: r.get(key) for per, r in S.items()})
    return None, None


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
    axis, values = series_for(ticker, label)
    if not axis:
        return {"insufficient": True,
                "reason": _NO_SERIES_REASON.get((ticker, label), "no historical series for this metric yet")}
    from . import methodology
    approach = methodology.metric_plan(ticker, label).get("approach")
    return run(axis, values, kind, approach=approach, guidance_by_key=guidance_for(ticker, label))


def _kind_from_units(units: str) -> str:
    u = (units or "").strip().lower()
    if "share" in u or u == "gbp":          # "USD / share", or Hays EPS in pence "GBp"
        return "eps"
    if "%" in u:
        return "pct"
    return "money"


def headline_error(r: dict) -> str:
    """Kind-appropriate point-error headline: pct → MAE in points, else WAPE."""
    if r.get("kind") == "pct":
        return f"MAE {r['mae']:.2f}pp"
    return f"WAPE {r['wape']:.0%}"


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
    out = [f"Point accuracy: {headline_error(r)} over {r['n_origins']} walk-forward origins "
           f"({grade}; model {r['model']})."]
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
    from .forecast import company_spec, METRIC_MAP
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

