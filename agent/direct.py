"""Auditable direct forecast layer used as the guarded pipeline's fallback.

For each target metric we produce the point directly from the adapter's approach:
  guidance anchor (calibrated) · seasonal + trend on the actual series · accounting
  bridge (EPS = after-tax ÷ shares; operating profit = base × margin/conversion).

Every number carries a `basis` string and source excerpts. The selection layer may
replace a point only when nested outer evidence passes its production gates.
"""
from __future__ import annotations

import re

from . import corpus, methodology


# ── small extraction helpers ──────────────────────────────────────────────────────
def _num(s: str) -> float:
    return float(s.replace(",", "").replace("$", "").replace("£", "").strip())


def _bn_to_m(v: float, unit: str) -> float:
    return v * 1000.0 if unit and unit.lower().startswith("b") else v


def _find(body: str, pat: str, flags=re.IGNORECASE):
    m = re.search(pat, body, flags)
    return m if m else None


def _releases(ticker: str):
    return corpus.earnings_releases(ticker)


def _by_period(ticker: str) -> dict:
    """period string -> latest release Doc for that period."""
    out = {}
    for d in _releases(ticker):
        out.setdefault(d.period, d)
        out[d.period] = d          # keep last (primary)
    return out


def _pt(point, kind, lo=None, hi=None, basis="", src=None):
    band = (lo, hi) if lo is not None and hi is not None else None
    return {"point": point, "band": band, "kind": kind, "basis": basis, "sources": src or []}


# ── ADI: guidance-anchored (methodology: Q3 guide is a strong anchor) ──────────────
def _adi() -> dict:
    from . import extract
    panel = extract.build_panel("ADI")
    last = panel[-1] if panel else None
    g = last.guidance_next if last else {}
    ev = last.evidence if last else {}
    out = {}
    # Revenue: guidance midpoint (position from momentum ~ sit at midpoint)
    if "revenue" in g:
        r = g["revenue"]
        out["Revenue"] = _pt(round(r, 0), "money", round(r * 0.97), round(r * 1.03),
                             "Q3 guidance midpoint (methodology: strong anchor)",
                             [ev.get("guide_next.revenue", "ADI Q2 8-K outlook")])
    if "adj_eps" in g:
        e = g["adj_eps"]
        out["Adjusted diluted EPS"] = _pt(round(e, 2), "eps", round(e - 0.15, 2), round(e + 0.15, 2),
                                          "Q3 guidance midpoint ±$0.15", [ev.get("guide_next.adj_eps", "ADI Q2 8-K outlook")])
    # Adjusted gross margin: series trend (last actual + small drift toward higher revenue)
    gms = [r.actuals.get("adj_gross_margin") for r in panel if r.actuals.get("adj_gross_margin") is not None]
    if gms:
        last_gm = gms[-1]
        trend = (gms[-1] - gms[-4]) / 3 if len(gms) >= 4 else 0.0
        gm = last_gm + max(-0.5, min(1.0, trend))
        out["Adjusted gross margin"] = _pt(round(gm, 2), "pct", round(gm - 1, 2), round(gm + 1, 2),
                                           f"last adj GM {last_gm:.1f}% + recent trend (rev rising to guide)",
                                           ["ADI Q2 8-K adjusted gross margin table"])
    return out


# ── HD: seasonal anchor × guidance calibration; comp = reversion to guide ──────────
def _hd_series():
    """(period -> {net_sales, comp, adj_eps}) from HD earnings releases."""
    rows = {}
    for d in _releases("HD"):
        b = d.body()
        r = {}
        m = _find(b, r"Net sales\s*\|\s*\$\s*\|\s*([\d,]+)")
        if not m:
            m = _find(b, r"reported sales of \$\s*([\d.]+)\s*(billion|million)")
            if m:
                r["net_sales"] = _bn_to_m(_num(m.group(1)), m.group(2))
        else:
            r["net_sales"] = _num(m.group(1))
        m = _find(b, r"Comparable sales for the [^.]*?(increased|decreased)\s*([\d.]+)\s*%")
        if m:
            r["comp"] = (1 if m.group(1).lower() == "increased" else -1) * _num(m.group(2))
        m = _find(b, r"Adjusted diluted earnings per share[^.$\n]*?(?:were|of)\s*\$\s*([\d.]+)")
        if m:
            r["adj_eps"] = _num(m.group(1))
        if r:
            rows[d.period] = {"row": r, "doc": d.name, "pub": d.published_at}
    return rows


def _hd_guidance():
    g = {}
    for d in reversed(_releases("HD")):          # newest first
        b = d.body()
        m = _find(b, r"[Tt]otal sales growth of approximately\s*([\d.]+)%?\s*to\s*([\d.]+)\s*%")
        if m and "sales_growth" not in g:
            g["sales_growth"] = (_num(m.group(1)) + _num(m.group(2))) / 2
            g["sales_growth_src"] = f"{d.name}: total sales growth {m.group(1)}–{m.group(2)}%"
        m = _find(b, r"[Cc]omparable sales growth of approximately\s*(flat|[\d.]+%?)\s*to\s*([\d.]+)\s*%")
        if m and "comp" not in g:
            lo = 0.0 if m.group(1).lower().startswith("flat") else _num(m.group(1).replace("%", ""))
            g["comp"] = (lo + _num(m.group(2))) / 2
            g["comp_src"] = f"{d.name}: comparable sales {m.group(1)} to {m.group(2)}%"
        if "sales_growth" in g and "comp" in g:
            break
    return g


def _hd() -> dict:
    S = _hd_series(); G = _hd_guidance()
    out = {}
    py = S.get("Q2 2025", {}).get("row", {})     # prior-year same quarter (seasonal anchor)
    q1 = S.get("Q1 2026", {}).get("row", {})     # latest quarter (trend)
    # Net sales: PY Q2 × (1 + total-sales-growth guide), nudged by Q1 run-rate
    if "net_sales" in py and "sales_growth" in G:
        g = G["sales_growth"] / 100
        pt = py["net_sales"] * (1 + g)
        out["Net sales"] = _pt(round(pt, 0), "money", round(pt * 0.985), round(pt * 1.015),
                               f"PY Q2 {py['net_sales']:.0f} × (1+{G['sales_growth']:.1f}% FY sales-growth guide)",
                               [G.get("sales_growth_src", ""), "HD FY2025 Q2 8-K net sales"])
    # Comparable sales: AR(1) from latest quarter toward FY comp-guide midpoint
    if "comp" in q1 and "comp" in G:
        phi = 0.4
        pt = phi * q1["comp"] + (1 - phi) * G["comp"]
        out["Comparable sales, total company"] = _pt(round(pt, 2), "pct", round(pt - 0.7, 2), round(pt + 0.7, 2),
                                                     f"AR(1): 0.4·Q1({q1['comp']:.1f}%) + 0.6·FY-guide-mid({G['comp']:.1f}%)",
                                                     [G.get("comp_src", ""), "HD Q1 FY2026 comparable sales"])
    # Adjusted EPS: PY Q2 × (1 + recent YoY trend)
    if "adj_eps" in py and "adj_eps" in q1 and "Q1 2025" in S:
        q1py = S["Q1 2025"]["row"].get("adj_eps")
        yoy = (q1["adj_eps"] / q1py - 1) if q1py else 0.0
        pt = py["adj_eps"] * (1 + yoy)
        out["Adjusted diluted EPS"] = _pt(round(pt, 2), "eps", round(pt - 0.12, 2), round(pt + 0.12, 2),
                                          f"PY Q2 {py['adj_eps']:.2f} × (1+{yoy*100:.1f}% latest-YoY)",
                                          ["HD FY2025 Q2 adj EPS", "HD Q1 FY2026 vs FY2025 adj EPS"])
    return out


# ── HAS: FY ended → reconstruction; net fees growth, OP stated, EPS bridge ─────────
def _has() -> dict:
    out = {}
    # Q4/FY26 trading update carries the reported YoY + the OP range/consensus
    upd = None
    for d in reversed(_releases("HAS")):
        if "2026-07" in d.published_at or "2026-08" in d.published_at:
            upd = d; break
    b = upd.body() if upd else ""
    # Net fees: latest FY25 actual × (1 + reported actual-basis YoY)
    fy25 = None
    for d in _releases("HAS"):
        if d.period and "2025" in d.period:
            m = _find(d.body(), r"[Nn]et fees[^.\n]*?£\s*([\d,]+(?:\.\d+)?)\s*(?:m|million)")
            if m:
                fy25 = _num(m.group(1))
    yoy = None
    m = _find(b, r"net fees\s*(?:decreased|down)[^.\n]*?(\d+)\s*%")
    if m:
        yoy = -_num(m.group(1))
    if fy25 is not None and yoy is not None:
        pt = fy25 * (1 + yoy / 100)
        out["Net fees"] = _pt(round(pt, 0), "money", round(pt * 0.97), round(pt * 1.03),
                              f"FY2025 net fees £{fy25:.0f}m × (1+{yoy:.0f}% reported YoY)",
                              ["Hays FY2025 net fees", f"{upd.name if upd else ''}: net fees YoY"])
    # Pre-exceptional operating profit: stated "top of £37–46m" + consensus
    lo = hi = cons = None
    m = _find(b, r"£\s*([\d.]+)\s*[–\-]\s*([\d.]+)\s*m")
    if m:
        lo, hi = _num(m.group(1)), _num(m.group(2))
    m = _find(b, r"consensus[^.\n]*?£\s*([\d.]+)\s*m")
    if m:
        cons = _num(m.group(1))
    if hi is not None:
        pt = (hi + (cons if cons else hi)) / 2 if cons else hi - 0.5
        out["Pre-exceptional operating profit"] = _pt(round(pt, 1), "money", round(lo, 1), round(hi, 1),
                                                      f"stated top of £{lo:.0f}–{hi:.0f}m; consensus £{cons}m → ~£{pt:.1f}m",
                                                      [f"{upd.name if upd else ''}: OP range + consensus"])
        # EPS bridge: pre-exc EPS ≈ OP × historical (EPS/OP) ratio (pence) — needs a ratio anchor
        out["Pre-exceptional basic EPS"] = _pt(round(pt * 0.045, 2), "eps", round(pt * 0.035, 2), round(pt * 0.055, 2),
                                               "bridge: operating profit × approx after-tax/share ratio (pence) — coarse, refine with shares/tax",
                                               ["Hays operating profit → EPS bridge (approx)"])
    return out


# ── DE: FY NI guide → Q3 EPS; segment %Δ → net sales & PPA OP ──────────────────────
def _de() -> dict:
    out = {}
    rel = _releases("DE")
    q2 = next((d for d in reversed(rel) if d.period == "Q2 2026"), None)
    b = q2.body() if q2 else ""
    # FY net income guide midpoint
    ni_mid = None
    h1_ni = None
    m = _find(b, r"net income[^.\n]*?fiscal 2026[^.\n]*?\$\s*([\d.]+)\s*billion\s*to\s*\$\s*([\d.]+)\s*billion")
    if not m:
        m = _find(b, r"forecasted to be in a range of\s*\$\s*([\d.]+)\s*billion\s*to\s*\$\s*([\d.]+)\s*billion")
    if m:
        ni_mid = (_num(m.group(1)) + _num(m.group(2))) / 2 * 1000    # $m
    m = _find(b, r"first six months[^.\n]*?net income[^.\n]*?\$\s*([\d.]+)\s*billion")
    if m:
        h1_ni = _num(m.group(1)) * 1000
    # PY Q3 net sales & shares from prior Q3 release
    q3py = next((d for d in reversed(rel) if d.period == "Q3 2025"), None)
    py_rev = None
    if q3py:
        m = _find(q3py.body(), r"[Nn]et sales and revenues[^.\n]*?to\s*\$\s*([\d.]+)\s*billion")
        if m:
            py_rev = _num(m.group(1)) * 1000
    # EPS (GAAP): (FY NI - H1 NI) × Q3-share ÷ diluted shares
    if ni_mid and h1_ni:
        h2 = ni_mid - h1_ni
        ni_q3 = h2 * 0.57                     # Q3 seasonally the larger of H2
        sh = 271.0                            # diluted shares (~m) — refine from filing
        eps = ni_q3 / sh
        out["Diluted EPS (GAAP)"] = _pt(round(eps, 2), "eps", round(eps * 0.85, 2), round(eps * 1.15, 2),
                                        f"FY NI mid ${ni_mid/1000:.2f}bn − H1 ${h1_ni/1000:.2f}bn → Q3 share 0.57 ÷ {sh:.0f}m sh",
                                        ["DE Q2 8-K FY net income guidance", "DE Q2 8-K six-month net income"])
    # Worldwide net sales & revenues: PY Q3 × segment-blended FY %Δ (approx flat/slightly down)
    if py_rev:
        blend = -0.03                          # revenue-weighted blend of segment guides (PPA −7.5%, SmallAg/C&F up)
        pt = py_rev * (1 + blend)
        out["Worldwide net sales and revenues"] = _pt(round(pt, 0), "money", round(pt * 0.95), round(pt * 1.05),
                                                     f"PY Q3 {py_rev:.0f} × (1+{blend*100:.0f}% segment-blended FY guide)",
                                                     ["DE FY2025 Q3 net sales & revenues", "DE Q2 8-K segment outlook"])
        # PPA operating profit: coarse — PPA is ~55% of sales at ~18% margin (downcycle)
        ppa_sales = pt * 0.55
        out["Production & Precision Ag operating profit"] = _pt(round(ppa_sales * 0.18, 0), "money",
                                                               round(ppa_sales * 0.14, 0), round(ppa_sales * 0.22, 0),
                                                               "PPA sales (≈55% of net sales, −7.5% FY guide) × ~18% segment margin — coarse",
                                                               ["DE Q2 8-K segment outlook (Production & Precision Ag)"])
    return out


def _de_series():
    """(period -> {net_sales_rev, eps_gaap}) from Deere quarterly releases (for backtesting)."""
    rows = {}
    for d in _releases("DE"):
        if not d.period or d.period.startswith("FY"):        # quarterly only (skip annual)
            continue
        b = d.body()
        r = {}
        m = _find(b, r"[Ww]orldwide net sales and revenues[^.]{0,70}?to\s*\$\s*([\d.,]+)\s*billion")
        if m:
            r["net_sales_rev"] = _num(m.group(1)) * 1000
        # quarterly diluted EPS: "... for the <ordinal> quarter ... or $X.XX per share"
        m = _find(b, r"for the [a-z]+ quarter[^.]{0,90}?or\s*\$\s*([\d.]+)\s*per share")
        if m and _num(m.group(1)) < 40:
            r["eps_gaap"] = _num(m.group(1))
        if r:
            rows[d.period] = r
    return rows


_ADAPTERS = {"ADI": _adi, "HD": _hd, "HAS": _has, "DE": _de}


def forecast(ticker: str) -> dict:
    """Methodology-1 direct forecast for one company. Returns the metric points keyed by
    the challenge label, plus which target labels are still missing."""
    a = methodology.adapter(ticker)
    produced = _ADAPTERS[ticker]() if ticker in _ADAPTERS else {}
    labels = list(a.get("metrics", {}).keys())
    return {"ticker": ticker, "company": a.get("name", ticker), "period": a.get("period", ""),
            "metrics": produced, "labels": labels,
            "missing": [l for l in labels if l not in produced]}
