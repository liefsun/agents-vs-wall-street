"""Local demo app — the presentation surface, in the spirit of the lab's Node Studio.

  /                overview: 4 companies x 3 metrics, fused point + band
  /c/<ticker>      detail: per-metric candidate leaderboard (backtest error + weight +
                   prediction), guidance anchor, actual-series sparkline, evidence trail
  /run             write the 4 workbooks to submission/ and report checker-shape status

Run:  uv run --with-requirements agent/requirements.txt python -m agent.app
"""
from __future__ import annotations

import html
import os
import time

from flask import Flask, Response, redirect

import json as _json

from .forecast import forecast_company, METRIC_MAP, company_spec
from .corpus import FOLDER, ROOT
from . import workbook, governance, output, methodology, direct

app = Flask(__name__)
TICKERS = ["HD", "ADI", "HAS", "DE"]

_CSS = """
*{box-sizing:border-box} body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
margin:0;background:#0f1216;color:#e6e9ef} a{color:#6aa0ff;text-decoration:none}
.wrap{max-width:1080px;margin:0 auto;padding:26px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;margin:26px 0 10px;color:#cdd3dd}
.sub{color:#8b93a1;font-size:13px;margin-bottom:18px}
.card{background:#161b22;border:1px solid #232b36;border-radius:10px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mrow{display:flex;justify-content:space-between;align-items:baseline;padding:7px 0;border-bottom:1px solid #1e252f}
.mrow:last-child{border:0} .pt{font-size:18px;font-weight:600;color:#fff}
.band{color:#8b93a1;font-size:12px} .u{color:#6b7280;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px} th,td{text-align:right;padding:5px 8px}
th:first-child,td:first-child{text-align:left} thead th{color:#8b93a1;border-bottom:1px solid #2a333f;font-weight:500}
tr.elig td{color:#e6e9ef} tr.out td{color:#5c6470}
.w{display:inline-block;height:8px;background:#3b82f6;border-radius:2px;vertical-align:middle}
.badge{font-size:11px;padding:1px 7px;border-radius:20px;background:#1f2937;color:#9ca3af;margin-left:6px}
.guide{background:#134e2a;color:#6ee7a8} .lab{background:#3a2a12;color:#f0b768}
.ev{color:#7b8494;font-size:12px;margin:3px 0;font-family:ui-monospace,monospace}
.phase{display:inline-block;font-size:12px;color:#9ca3af;background:#1a212b;border:1px solid #263040;
border-radius:20px;padding:3px 11px;margin:2px 4px 2px 0}
.pending{opacity:.5}
.gnode{cursor:pointer} .gnode rect{transition:.1s} .gnode:hover rect{filter:brightness(1.25)}
.gnode text{fill:#e6e9ef;font:11px -apple-system,Segoe UI,sans-serif;pointer-events:none}
.leg{font-size:12px;color:#9ca3af;margin:8px 0} .sw{display:inline-block;width:11px;height:11px;
border-radius:3px;vertical-align:middle;margin:0 4px 0 12px}
#ov{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:9}
#panel{background:#161b22;border:1px solid #2a333f;border-radius:12px;max-width:560px;width:92vw;padding:20px;max-height:88vh;overflow:auto}
#panel h3{margin:0 0 4px} pre{background:#0d1117;border:1px solid #222b36;border-radius:8px;padding:10px;
overflow:auto;font:12px ui-monospace,monospace;color:#c9d3df}
.kv{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1e252f;font-size:13px}
.x{float:right;cursor:pointer;color:#8b93a1}
.gnode.done rect{stroke:#2f6b43}
.gnode.run rect{stroke:#3fb950 !important;stroke-width:2.6;filter:drop-shadow(0 0 6px #3fb95088)}
#runlog{background:#0d1117;border:1px solid #263040;border-radius:8px;padding:10px;height:180px;
overflow:auto;font:12px ui-monospace,monospace;color:#c9d3df;white-space:pre-wrap;margin-top:8px}
#runlog .n{color:#6ee7a8} #runlog .d{color:#8b93a1}
button{background:#1f6feb;color:#fff;border:0;border-radius:7px;padding:7px 14px;font:600 13px sans-serif;cursor:pointer}
button:disabled{opacity:.5;cursor:default} button.g{background:#238636}
"""


def _fmt(v, kind):
    if v is None:
        return "—"
    if kind == "eps":
        return f"{v:,.2f}"
    if kind == "pct":
        return f"{v:,.2f}"
    return f"{v:,.0f}"


def _sparkline(axis, values, w=260, h=44):
    pts = [(a, v) for a, v in zip(axis, values) if v is not None][-24:]
    if len(pts) < 2:
        return ""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys); rng = (hi - lo) or 1
    x0, x1 = min(xs), max(xs); xr = (x1 - x0) or 1
    coords = [(8 + (x - x0) / xr * (w - 16), h - 6 - (y - lo) / rng * (h - 12)) for x, y in zip(xs, ys)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    cx, cy = coords[-1]
    return (f'<svg width="{w}" height="{h}">'
            f'<path d="{d}" fill="none" stroke="#6aa0ff" stroke-width="1.6"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#6ee7a8"/></svg>')


def _page(title, body):
    return (f"<!doctype html><meta charset=utf-8><title>{title}</title>"
            f"<style>{_CSS}</style><div class=wrap>{body}</div>")


@app.get("/")
def index():
    manifest = output.run_pipeline(write=False)
    rows = ""
    for c in manifest["companies"]:
        cells = ""
        for m in c["metrics"]:
            bd = m["band"]
            band = f"{_fmt(bd[0], m['kind'])}–{_fmt(bd[1], m['kind'])}" if bd else ""
            val = _fmt(m["point"], m["kind"]) if m["point"] is not None else "—"
            basis = f" <span class=u title=\"{html.escape(m.get('basis') or '')}\">ⓘ</span>" if m.get("basis") else ""
            cells += (f"<div class=mrow><span>{html.escape(m['label'])} "
                      f"<span class=u>{html.escape(m['units'])}</span></span>"
                      f"<span><span class=pt>{val}</span> <span class=band>{band}</span>{basis}</span></div>")
        head = (f"<b>{html.escape(c['company'])}</b> "
                f"<span class=badge>{html.escape(c['period'])}</span>")
        rows += (f"<div class=card><div style='display:flex;justify-content:space-between'>"
                 f"<div>{head}</div><a href='/graph?t={c['ticker']}'>graph →</a></div>{cells}</div>")
    body = (f"<h1>Agents vs Wall Street — forecasting agent</h1>"
            f"<div class=sub><b>{methodology.METHODOLOGY_1['name']}</b> · direct output "
            f"(backtesting deferred). {manifest['n_filled']}/{manifest['n_total']} numbers produced.</div>"
            f"<div class=card><a href='/graph'>▶ one pipeline · four companies · output layer (graph)</a>"
            f" &nbsp;·&nbsp; <a href='/output'>output layer</a>"
            f" &nbsp;·&nbsp; <a href='/backtest'>backtest results</a>"
            f" &nbsp;·&nbsp; <a href='/run'>write the 4 workbooks</a></div>"
            f"<h2>Four companies · twelve metrics</h2>{rows}")
    return Response(_page("Forecasting agent", body), mimetype="text/html")


@app.get("/c/<ticker>")
def company(ticker):
    ticker = ticker.upper()
    if ticker not in FOLDER:
        return redirect("/")
    if ticker not in METRIC_MAP:
        return Response(_page(ticker, f"<h1>{ticker}</h1><div class=sub>Extractor not wired "
                                      f"yet for this company (ADI is the reference implementation).</div>"
                                      f"<a href='/'>← back</a>"), mimetype="text/html")
    fc = forecast_company(ticker)
    blocks = ""
    for m in fc["metrics"]:
        res = m.result
        if m.point is None:
            blocks += f"<div class=card><b>{html.escape(m.label)}</b><div class=u>insufficient data</div></div>"
            continue
        bd = m.band
        band = f"{_fmt(bd[0], m.kind)} – {_fmt(bd[1], m.kind)}" if bd else "—"
        anchor = f"<span class='badge guide'>guidance {_fmt(m.guidance_anchor, m.kind)}</span>" if m.guidance_anchor is not None else ""
        lb = ""
        for row in res["leaderboard"]:
            cls = "elig" if row["eligible"] else "out"
            err = f"{row['error']:.4f}" if row["error"] is not None else "—"
            pred = _fmt(row["final_pred"], m.kind) if row["final_pred"] is not None else "—"
            wpx = int(row["weight"] * 90)
            tag = " <span class='badge guide'>guidance</span>" if row["model"] == "guidance" else ""
            lb += (f"<tr class={cls}><td>{html.escape(row['label'])}{tag}</td>"
                   f"<td>{err}</td><td>{pred}</td>"
                   f"<td><span class=w style='width:{wpx}px'></span> {row['weight']:.2f}</td>"
                   f"<td class=u>{row['origins']}</td></tr>")
        ev = "".join(f"<div class=ev>{html.escape(str(e))}</div>" for e in m.evidence[:3])
        spark = _sparkline(m.series["axis"], m.series["values"])
        blocks += (f"<div class=card>"
                   f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
                   f"<div><b>{html.escape(m.label)}</b> <span class=u>{html.escape(m.units)}</span> {anchor}</div>"
                   f"<div><span class=pt>{_fmt(m.point, m.kind)}</span> "
                   f"<span class=band>band {band}</span></div></div>"
                   f"<div style='margin:8px 0'>{spark} <span class=u>backtest: baseline WAPE/MAE "
                   f"{res['baseline_error']:.3f} · {res['n_origins']} origins"
                   f"{' · FALLBACK' if res['fallback'] else ''}</span></div>"
                   f"<table><thead><tr><th>candidate</th><th>bt error</th><th>pred</th>"
                   f"<th>weight</th><th>n</th></tr></thead><tbody>{lb}</tbody></table>"
                   f"<div style='margin-top:8px'>{ev}</div></div>")
    body = (f"<h1>{html.escape(fc['company'])} <span class=badge>{html.escape(fc['period'])}</span></h1>"
            f"<div class=sub>{fc['panel_rows']} periods extracted · fused point = capped inverse-error "
            f"ensemble of candidates that beat seasonal-naive in the trailing backtest window</div>"
            f"<a href='/'>← overview</a>{blocks}")
    return Response(_page(fc["company"], body), mimetype="text/html")


@app.get("/output")
def output_page():
    from flask import request
    write = request.args.get("write") == "1"
    spec = output.output_spec()
    manifest = output.run_pipeline(write=write)
    files = ""
    for c in manifest["companies"]:
        ready = c["wired"] and all(m["point"] is not None for m in c["metrics"])
        rows = ""
        for m in c["metrics"]:
            val = _fmt(m["point"], m["kind"]) if m["point"] is not None else "—"
            bd = m.get("band")
            band = f" <span class=band>[{_fmt(bd[0], m['kind'])}–{_fmt(bd[1], m['kind'])}]</span>" if bd else ""
            rows += (f"<div class=mrow><span>{html.escape(m['label'])} <span class=u>{html.escape(m['units'])}</span></span>"
                     f"<span><span class=pt>{val}</span>{band}</span></div>")
        status = ("<span class='badge guide'>ready</span>" if ready
                  else "<span class=badge>pending</span>")
        wrote = f"<span class=u>· wrote {os.path.basename(c['written'])}</span>" if c.get("written") else ""
        files += (f"<div class=card><div style='display:flex;justify-content:space-between'>"
                  f"<div><b>{html.escape(c['file'])}</b> <span class=u>{html.escape(c['company'])} · "
                  f"{html.escape(c['period'])}</span> {status} {wrote}</div></div>{rows}</div>")
    contract = "".join(f"<li>{html.escape(x)}</li>" for x in spec["contract"])
    hdr = (f"<div class=card><b>Output layer — what the pipeline emits</b>"
           f"<div class=mrow><span>deliverable</span><span>{html.escape(spec['deliverable'])}</span></div>"
           f"<div class=mrow><span>numbers</span><span>{manifest['n_filled']}/{spec['n_numbers']} produced</span></div>"
           f"<div class=mrow><span>final command</span><span class=u>python -m agent.run</span></div>"
           f"<div class=mrow><span>checker</span><span class=u>{html.escape(spec['checker'])}</span></div>"
           f"<div class=mrow><span>upload</span><span class=u>{html.escape(spec['upload'])}</span></div>"
           f"<div style='margin-top:8px'><b class=u>Contract (Summary sheet)</b><ul class=u style='margin:6px 0'>{contract}</ul></div></div>")
    action = (f"<div class=card><a href='/output?write=1'>▶ run pipeline for all four & write workbooks to submission/</a>"
              + (f" <span class=u>· wrote {sum(1 for c in manifest['companies'] if c.get('written'))} files</span>" if write else "")
              + "</div>")
    body = (f"<h1>Output layer</h1><div class=sub>The four companies through one pipeline → "
            f"{spec['n_numbers']} numbers in {len(spec['files'])} workbooks.</div>"
            f"{hdr}{action}{files}<a href='/graph'>← pipeline graph</a> · <a href='/'>overview</a>")
    return Response(_page("Output", body), mimetype="text/html")


@app.get("/backtest")
def backtest_page():
    from . import prequential as _pq
    from . import param_eval as _pe
    rows = _pq.run_all()
    pe_map = {(x["ticker"], x["label"]): x for x in _pe.compare_all()}
    # write outputs/backtest.json (Methodology 1 §11 auditability)
    try:
        outdir = os.path.join(ROOT, "outputs")
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "backtest.json"), "w", encoding="utf-8") as fh:
            _json.dump(rows, fh, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

    def _pct(x):
        return f"{x:.0%}" if x is not None else "—"

    n_tested = sum(1 for r in rows if not r.get("insufficient"))
    n_miscal = sum(1 for r in rows if not r.get("insufficient")
                   and r.get("kupiec_pvalue") is not None and r["kupiec_pvalue"] < 0.05)
    cards = ""
    for t in ("HD", "ADI", "HAS", "DE"):
        crows = [r for r in rows if r["ticker"] == t]
        body = ""
        for r in crows:
            if r.get("insufficient"):
                body += (f"<div style='padding:6px 0;border-bottom:1px solid #1e252f'>"
                         f"<div style='display:flex;justify-content:space-between'>"
                         f"<span>{html.escape(r['label'])} <span class=u>{html.escape(r['units'])}</span></span>"
                         f"<span class=u>skipped</span></div>"
                         f"<div class=ev>{html.escape(r.get('reason', 'no series'))}</div></div>")
                continue
            kp = r.get("kupiec_pvalue")
            if kp is None:
                badge = "<span class=badge>— </span>"
            elif kp < 0.05:
                badge = "<span class='badge lab'>miscalibrated</span>"
            else:
                badge = "<span class='badge guide'>calibrated</span>"
            kps = f"{kp:.2f}" if kp is not None else "n/a"
            body += (f"<div style='padding:7px 0;border-bottom:1px solid #1e252f'>"
                     f"<div style='display:flex;justify-content:space-between'>"
                     f"<span><b>{html.escape(r['label'])}</b> <span class=u>{html.escape(r['units'])}</span></span>"
                     f"<span>{badge}</span></div>"
                     f"<div class=u style='margin:3px 0'>n={r['n_origins']} · {_pq.headline_error(r)} · "
                     f"RMSE {r['rmse']:.3g} · breach {_pct(r['breach_rate'])}/exp {_pct(r['expected_breach'])} · "
                     f"Kupiec p={kps}</div>"
                     f"<div class=ev>{html.escape(r['analysis'])}</div>")
            pe = pe_map.get((r["ticker"], r["label"]))
            if pe and not pe.get("insufficient"):
                rank = " › ".join(x["model"] for x in pe["rows"][:4])
                sens = pe.get("sensitivity") or {}
                beats = "beats seasonal-naive ✓" if pe["beats_baseline"] else "≤ baseline"
                robust = "robust across windows" if sens.get("robust") else "window-sensitive"
                body += (f"<div class=ev style='color:#8fa8c8'>▸ param eval: best <b>{html.escape(pe['best'])}</b> "
                         f"· {beats} · {robust} · ranking: {html.escape(rank)}</div>")
            body += "</div>"
        cards += (f"<div class=card><b>{html.escape(crows[0]['company'])}</b> "
                  f"<span class=badge>{html.escape(crows[0]['period'])}</span>{body}</div>")
    body = (f"<h1>Prequential backtest — results & analysis</h1>"
            f"<div class=sub>Walk-forward one-step-ahead (pulled from quant-projects garch_var). "
            f"Point error (WAPE/RMSE) + VaR-style band coverage + Kupiec POF test. "
            f"<b>{n_tested}/12 metrics tested · {n_miscal} band(s) miscalibrated.</b> "
            f"Written to <code>outputs/backtest.json</code>.</div>"
            f"{cards}<a href='/graph'>← pipeline graph</a> · <a href='/'>overview</a>")
    return Response(_page("Backtest", body), mimetype="text/html")


@app.get("/run")
def run():
    manifest = output.run_pipeline(write=True)
    lines = ""
    for c in manifest["companies"]:
        if not c["wired"]:
            lines += f"<div class=mrow><span>{c['ticker']}</span><span class=u>skipped — extractor pending</span></div>"
            continue
        vals = ", ".join(f"{m['label']}={_fmt(m['point'], m['kind'])}"
                         for m in c["metrics"] if m["point"] is not None)
        lines += f"<div class=mrow><span>{os.path.basename(c['written'])}</span><span class=u>{html.escape(vals)}</span></div>"
    body = (f"<h1>Write workbooks</h1><div class=sub>{manifest['n_filled']}/{manifest['n_total']} numbers · "
            f"submission/*.xlsx — validate with <code>npm run check:submission</code></div>"
            f"<div class=card>{lines}</div><a href='/output'>output detail →</a> · <a href='/'>overview</a>")
    return Response(_page("Run", body), mimetype="text/html")


_PLUG_COLOR = {"hot": "#f0b768", "code": "#6aa0ff", "no": "#8b93a1"}
_PHASE_Y = {"IN": (40, 92), "P1": (112, 232), "P2": (252, 312),
            "P3": (332, 452), "P4": (472, 552), "P5": (572, 640)}


def _rect(x, y, w, h, nid, fill, stroke, lines, dash=False, ring=None):
    """One clickable graph node."""
    tx = x + w / 2
    txt = ""
    n = len(lines)
    for i, ln in enumerate(lines):
        ty = y + h / 2 + (i - (n - 1) / 2) * 13 + 4
        weight = "600" if i == 0 else "400"
        txt += f'<text x="{tx:.0f}" y="{ty:.0f}" text-anchor="middle" font-weight="{weight}">{html.escape(ln)}</text>'
    d = ' stroke-dasharray="4 3"' if dash else ""
    r = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" '
         f'stroke="{stroke}" stroke-width="1.4"{d}/>')
    rr = f'<rect x="{x-2}" y="{y-2}" width="{w+4}" height="{h+4}" rx="8" fill="none" stroke="{ring}" stroke-width="1.6"/>' if ring else ""
    return f'<g class=gnode id="n_{nid}" onclick="show(\'{nid}\')">{rr}{r}{txt}</g>'


def _methodology_html():
    """Full description of the active methodology (Methodology 1) for the node modal."""
    M = methodology.METHODOLOGY_1

    def ul(items):
        return "<ul class=u style='margin:4px 0 8px;padding-left:18px'>" + "".join(
            f"<li>{html.escape(str(x))}</li>" for x in items) + "</ul>"

    h = (f"<div class=u style='margin:0 0 8px'>{html.escape(M['goal'])}</div>"
         "<b class=u>Approach</b>" + ul(M["approach"]) +
         "<b class=u>Core principles (the agent must obey)</b>" + ul(M["principles"]) +
         "<b class=u>Flow</b><div class=u style='margin:4px 0 8px'>" +
         " → ".join(html.escape(s) for s in M["flow"]) + "</div>" +
         "<b class=u>Data priority</b>" + ul(M["data"]["priority"]) +
         "<b class=u>Baseline — current form (backtesting deferred)</b>"
         f"<div class=u style='margin:4px 0'>{html.escape(M['baseline']['formula'])}</div>"
         f"<div class=u style='margin:0 0 8px'>allowed: {', '.join(M['baseline']['allowed'])}; "
         f"forbidden: {html.escape(M['baseline']['forbidden'])}</div>"
         "<b class=u>Per-company adapters (drive the models)</b>")
    for t, a in M["adapters"].items():
        h += f"<div class=kv><span><b>{t}</b> · {html.escape(a['name'])} · {a['period']}</span></div>"
        for lbl, mp in a["metrics"].items():
            h += (f"<div class=kv><span>{html.escape(lbl)}</span>"
                  f"<span class=u>{mp['approach']} · {html.escape(mp['note'])}</span></div>")
        h += f"<div class=u style='margin:2px 0 8px'>guidance: {html.escape(a['guidance'])}</div>"
    h += ("<b class=u>Output rules</b>" + ul(M["output"]["rules"]) +
          "<b class=u>Deferred (not in the current form)</b>"
          f"<div class=u style='margin:4px 0'>{', '.join(M['deferred'])}</div>"
          f"<div class=u style='margin:8px 0 0'><i>{html.escape(M['current_form'])}</i></div>")
    return h


def _graph_svg(fc, mf):
    """Focus view for one metric, layered as the user's mental model:
    Input(company, required output) -> Data ingestion -> Methodology -> Model
    -> Backtesting -> Output. Returns (svg, nodes_js)."""
    W, H = 1060, 664
    lb = {r["model"]: r for r in mf.result.get("leaderboard", [])} if mf and mf.point is not None else {}
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:1060px">']
    nodes = {}

    def cx(x, w): return x + w / 2

    def band(y0, y1, ident, title, plug):
        col = _PLUG_COLOR.get(plug, "#6b7480")
        tag = {"hot": "HOT-SWAP", "code": "CODE", "no": "FIXED", "in": "GIVEN"}.get(plug, "")
        parts.append(f'<rect x="6" y="{y0-4}" width="{W-12}" height="{y1-y0+8}" rx="9" fill="#12171e" stroke="#1c242e"/>')
        parts.append(f'<text x="18" y="{y0+12}" fill="#6b7480" style="font:600 11px sans-serif">{ident} · {html.escape(title)}</text>')
        parts.append(f'<text x="18" y="{y0+27}" fill="{col}" style="font:10px sans-serif">{tag}</text>')

    # INPUT
    iy = _PHASE_Y["IN"]
    band(iy[0], iy[1], "IN", "Input · (company code, required output)", "in")
    metric_lab = mf.label if mf else ""
    parts.append(_rect(380, 50, 300, 34, "input", "#101a26", "#3b5b7e",
                       [f"{fc['ticker']} · {metric_lab}", f"required: {mf.units if mf else ''} · {fc['period']}"]))
    nodes["input"] = {"t": "Input — what the pipeline is asked to do", "plug": "given",
                      "sub": "company code + required output",
                      "body": f"Forecast <b>{html.escape(metric_lab)}</b> for {fc['company']} ({fc['ticker']}), "
                              f"reported in {mf.units if mf else ''} for {fc['period']}. "
                              f"The required-output contract comes from companies.json."}
    inb = (530, 84)

    # bands P1..P5 (titles/plugs from governance.PHASES)
    P = {p["id"]: p for p in governance.PHASES}
    for pid in ("P1", "P2", "P3", "P4", "P5"):
        y0, y1 = _PHASE_Y[pid]
        band(y0, y1, pid, P[pid]["title"], P[pid]["plug"])

    # P1 Data ingestion: sources -> extract
    for (nid, label), x in zip([("src_filings", "Filings"), ("src_transcripts", "Transcripts"),
                                ("src_slides", "Slides")], [300, 520, 740]):
        parts.append(_rect(x, 122, 140, 28, nid, "#1a2531", "#33506e", [label]))
        parts.append(f'<path d="M{x+70},150 C{x+70},168 520,168 520,182" fill="none" stroke="#2b3745" stroke-width="0.8"/>')
        nodes[nid] = {"t": label, "plug": "code", "sub": "P1 · Data ingestion",
                      "body": f"Frozen corpus document type. {fc['company']}: {fc['panel_rows']} extracted periods."}
    parts.append(_rect(400, 182, 240, 40, "extract", "#2a2312", "#7a5a1e",
                       ["Extract → period panel", f"{fc['ticker']} · actuals + issued guidance"]))
    parts.append(f'<path d="M{inb[0]},{inb[1]} C{inb[0]},104 520,104 520,182" fill="none" stroke="#2b3745" stroke-width="1.2"/>')
    nodes["extract"] = {"t": "Extractor → period panel", "plug": "hot", "sub": "P1 · Data ingestion (hot-swap)",
                        "body": f"Text→panel for {fc['company']}: per-metric prose+table regex, LLM fallback seam. "
                                f"Panel: {fc['panel_rows']} periods (actuals + issued guidance)."}

    # P2 Methodology (control plane) — Methodology 1
    parts.append(_rect(360, 262, 340, 40, "methodology", "#1a1f27", "#4a5568",
                       ["Methodology 1 · click to read", "filing baseline + guidance — decides HOW"]))
    parts.append(f'<line x1="520" y1="222" x2="530" y2="262" stroke="#3a4658" stroke-width="1.4"/>')
    mthb = (530, 302)
    nodes["methodology"] = {"t": methodology.METHODOLOGY_1["name"], "plug": "no",
                            "sub": "P2 · FIXED / constitutional — the agent reads this and obeys it",
                            "body": _methodology_html()}

    # P3 Model (candidates)
    models = governance.active_models(mf.kind) if (mf and mf.kind) else governance.active_models("money")
    ids = [m.id for m in models] + ["guidance"]
    mnode = {m.id: m for m in models}
    n = len(ids)
    mw = (W - 40 - (n - 1) * 10) / n
    p3c = {}
    for i, mid in enumerate(ids):
        x = 20 + i * (mw + 10)
        row = lb.get(mid, {})
        plug = row.get("plug", "hot" if mid == "guidance" else (mnode[mid].plug if mid in mnode else "code"))
        col = _PLUG_COLOR.get(plug, "#6aa0ff")
        elig = row.get("eligible")
        w = row.get("weight", 0.0)
        lab = "guidance" if mid == "guidance" else (mnode[mid].label if mid in mnode else mid)
        short = (lab[:16] + "…") if len(lab) > 17 else lab
        parts.append(_rect(x, 366, mw, 52, mid, col + "22", col, [short, f"w {w:.2f}"], ring=("#3fb950" if elig else None)))
        p3c[mid] = (cx(x, mw), 418)
        parts.append(f'<path d="M{mthb[0]},{mthb[1]} C{mthb[0]},334 {cx(x,mw)},334 {cx(x,mw)},366" fill="none" stroke="#22303e" stroke-width="0.7"/>')
        err = row.get("error")
        nodes[mid] = {"t": lab, "plug": plug,
                      "sub": f"P3 · Model ({'JSON hot-swap' if plug == 'hot' and mid != 'guidance' else 'guidance' if mid == 'guidance' else 'code'})",
                      "body": (f"backtest error: {err:.4f}<br>ensemble weight: {w:.2f}<br>"
                               f"eligible (beat seasonal-naive): {'yes' if elig else 'no'}<br>"
                               f"next-period prediction: {row.get('final_pred')}" if row else "not scored"),
                      "spec": (mnode[mid].spec if mid in mnode and mnode[mid].spec else None),
                      "producer": (mnode[mid].producer if mid in mnode else None)}

    # P4 Backtesting
    parts.append(_rect(300, 488, 230, 40, "backtest", "#1b222c", "#3a4658",
                       ["Rolling-origin backtest", "gate vs seasonal-naive · PIT"]))
    parts.append(_rect(600, 488, 170, 40, "ensemble", "#1b222c", "#3a4658",
                       ["Capped ensemble", "learned weights"]))
    btc = (415, 488); eno = (685, 528)
    for mid, (mx, my) in p3c.items():
        row = lb.get(mid, {})
        wt = row.get("weight", 0.0)
        col = "#f0b768" if row.get("eligible") else "#2b3745"
        parts.append(f'<path d="M{mx},{my} C{mx},458 {btc[0]},458 {btc[0]},488" fill="none" stroke="{col}" stroke-width="{0.6+wt*7:.1f}" opacity="0.75"/>')
    parts.append(f'<line x1="530" y1="508" x2="600" y2="508" stroke="#4a5a6e" stroke-width="2.4"/>')
    nodes["backtest"] = {"t": "Rolling-origin backtest · gate", "plug": "no", "sub": "P4 · Backtesting (executes methodology)",
                         "body": "Executes the methodology: at each trailing origin fit on data-up-to-then, predict "
                                 "next, score; drop anything that can't beat seasonal-naive."}
    nodes["ensemble"] = {"t": "Capped inverse-error ensemble", "plug": "no", "sub": "P4 · Backtesting",
                         "body": "Survivors weighted by 1/error, capped, renormalised = the learned weights."}

    # P5 Output
    parts.append(_rect(320, 584, 170, 40, "guardrail", "#16241b", "#2f6b43", ["Guardrail band", "point ± ens-error"]))
    parts.append(_rect(560, 584, 170, 40, "emit", "#16241b", "#2f6b43", [fc["output_file"], "Summary sheet"]))
    parts.append(f'<path d="M{eno[0]},{eno[1]} C{eno[0]},558 405,558 405,584" fill="none" stroke="#3a6b47" stroke-width="2"/>')
    parts.append(f'<line x1="490" y1="604" x2="560" y2="604" stroke="#3a6b47" stroke-width="2"/>')
    nodes["guardrail"] = {"t": "Guardrail band", "plug": "no", "sub": "P5 · Output",
                          "body": f"Point {_fmt(mf.point, mf.kind) if mf and mf.point is not None else '—'} "
                                  f"± ensemble error → band. Consensus-clamp seam (corpus-only for now)."}
    nodes["emit"] = {"t": "Workbook writer", "plug": "no", "sub": "P5 · Output",
                     "body": f"Writes submission/{fc['output_file']} — fills the Summary-sheet cell for this metric."}
    parts.append("</svg>")
    return "".join(parts), nodes


def _pipeline_svg(manifest, spec):
    """Unified view: the four companies flow through ONE pipeline into the output layer."""
    W, H = 1060, 600
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:1060px">']
    nodes = {}
    xs = [120, 360, 600, 840]
    cos = manifest["companies"]

    # band labels
    for (lab, y, tag, col) in [("INPUT · four companies", 34, "company code + required output", "#6b7480"),
                               ("SHARED PIPELINE", 152, "ingestion → methodology → model → backtesting", "#6aa0ff"),
                               ("P5 · OUTPUT LAYER", 428, "4 workbooks · 12 numbers", "#3fb950")]:
        parts.append(f'<text x="18" y="{y}" fill="{col}" style="font:600 11px sans-serif">{lab}</text>')
        if tag:
            parts.append(f'<text x="200" y="{y}" fill="#5c6470" style="font:10px sans-serif">{tag}</text>')

    # input: 4 company nodes
    incx = []
    for c, x in zip(cos, xs):
        wired = c["wired"]
        col = "#6aa0ff" if wired else "#8b93a1"
        badge = "" if wired else " ·pending"
        parts.append(_rect(x, 46, 170, 46, f"co_{c['ticker']}", col + "1e", col,
                           [f"{c['ticker']} · {c['company'][:16]}", f"{c['period']}{badge}"]))
        incx.append(x + 85)
        vals = "".join(f"{m['label']}: {(_fmt(m['point'], m['kind']) if m['point'] is not None else '—')} {m['units']}<br>"
                       for m in c["metrics"])
        nodes[f"co_{c['ticker']}"] = {"t": f"{c['company']} — input", "plug": "code" if wired else "no",
                                      "sub": f"target {c['period']}", "body": (vals or "extractor pending")}

    # shared core: ingestion → methodology → model → backtesting
    ex = (430, 172, 158, 40)
    parts.append(_rect(*ex, "u_extract", "#2a2312", "#7a5a1e", ["Extract → panel", "per company (ingestion)"]))
    mth = (380, 226, 300, 34)
    parts.append(_rect(*mth, "u_method", "#1a1f27", "#4a5568",
                       ["Methodology 1 · click to read", "filing baseline + guidance — decides HOW"]))
    nModels = len(governance.active_models("money"))
    cd = (380, 288, 300, 40)
    parts.append(_rect(*cd, "u_candidates", "#241a2b", "#7a5a1e",
                       [f"Model layer · {nModels} nodes", "hot-swap registry + guidance"]))
    bt = (350, 352, 170, 38); en = (560, 352, 150, 38)
    parts.append(_rect(*bt, "u_backtest", "#1b222c", "#3a4658", ["Backtesting gate", "vs seasonal-naive · PIT"]))
    parts.append(_rect(*en, "u_ensemble", "#1b222c", "#3a4658", ["Capped ensemble", "learned weights"]))
    ex_cx = ex[0] + ex[2] / 2; mth_cx = mth[0] + mth[2] / 2; cd_cx = cd[0] + cd[2] / 2
    for cx0 in incx:                                   # companies fan-in to the one pipeline
        parts.append(f'<path d="M{cx0},92 C{cx0},120 {ex_cx},120 {ex_cx},{ex[1]}" fill="none" stroke="#2b3745" stroke-width="1"/>')
    parts.append(f'<line x1="{ex_cx}" y1="{ex[1]+ex[3]}" x2="{mth_cx}" y2="{mth[1]}" stroke="#5a4620" stroke-width="1.4"/>')
    parts.append(f'<line x1="{mth_cx}" y1="{mth[1]+mth[3]}" x2="{cd_cx}" y2="{cd[1]}" stroke="#3a4658" stroke-width="1.4"/>')
    parts.append(f'<path d="M{cd_cx},{cd[1]+cd[3]} C{cd_cx},344 {bt[0]+bt[2]/2},344 {bt[0]+bt[2]/2},{bt[1]}" fill="none" stroke="#3a4658" stroke-width="1.6"/>')
    parts.append(f'<line x1="{bt[0]+bt[2]}" y1="{bt[1]+bt[3]/2}" x2="{en[0]}" y2="{en[1]+en[3]/2}" stroke="#4a5a6e" stroke-width="2"/>')
    nodes["u_extract"] = {"t": "Extract → period panel", "plug": "hot", "sub": "P1 · Data ingestion (hot-swap)",
                          "body": "Text→panel per company: actuals series + issued guidance. Same extractor shape, one per company."}
    nodes["u_method"] = {"t": methodology.METHODOLOGY_1["name"], "plug": "no",
                         "sub": "P2 · FIXED / constitutional — the agent reads this and obeys it",
                         "body": _methodology_html()}
    nodes["u_candidates"] = {"t": f"Model layer · {nModels} nodes", "plug": "hot", "sub": "P3 · hot-swap registry",
                             "body": "Parallel forecasters compete: seasonal/drift/trend/AR/ETS + guidance + JSON hot-swap nodes. Open a company+metric to see the learned weights."}
    nodes["u_backtest"] = {"t": "Rolling-origin backtest · gate", "plug": "no", "sub": "P4 · Backtesting", "body": "PIT gate: drop anything that can't beat seasonal-naive."}
    nodes["u_ensemble"] = {"t": "Capped inverse-error ensemble", "plug": "no", "sub": "P4 · Backtesting", "body": "Survivors weighted by 1/error (cap 0.60) → point + band."}

    # output layer: 4 workbook nodes + an OUTPUT spec node
    en_cx, en_cy = en[0] + en[2] / 2, en[1] + en[3]
    for c, x in zip(cos, xs):
        ready = c["wired"] and all(m["point"] is not None for m in c["metrics"])
        col = "#3fb950" if ready else "#8b93a1"
        summ = "  ".join(_fmt(m["point"], m["kind"]) for m in c["metrics"] if m["point"] is not None) or "pending"
        parts.append(_rect(x, 448, 170, 46, f"out_{c['ticker']}", "#16241b", col,
                           [c["file"], summ], ring=("#3fb950" if ready else None)))
        ocx = x + 85
        parts.append(f'<path d="M{en_cx},{en_cy} C{en_cx},420 {ocx},420 {ocx},448" fill="none" stroke="#3a6b47" stroke-width="1.3"/>')
        mrows = "".join(f"<div class=kv><span>{html.escape(m['label'])} <span class=u>{m['units']}</span></span>"
                        f"<span>{(_fmt(m['point'], m['kind']) if m['point'] is not None else '—')}</span></div>"
                        for m in c["metrics"])
        nodes[f"out_{c['ticker']}"] = {"t": f"{c['file']}", "plug": "no", "sub": "P5 · output workbook",
                                       "body": f"Summary sheet for {c['company']} · {c['period']}.<br>{mrows}"}
    # the OUTPUT spec node (what this whole layer emits)
    parts.append(_rect(378, 520, 304, 40, "output_spec", "#12271a", "#2f6b43",
                       [f"OUTPUT · {spec['n_numbers']} numbers → {len(spec['files'])} .xlsx", "click: what we emit"]))
    contract = "".join(f"<div class=kv><span>{html.escape(x)}</span></div>" for x in spec["contract"])
    filerows = "".join(f"<div class=kv><span>{f['file']}</span><span class=u>{', '.join(m['label'] for m in f['metrics'])}</span></div>"
                       for f in spec["files"])
    nodes["output_spec"] = {"t": "Output layer — the deliverable", "plug": "no", "sub": "P5 · FIXED / constitutional",
                            "body": (f"<b>{spec['deliverable']}</b> — {spec['n_numbers']} numbers.<br><br>"
                                     f"<b>Files</b>{filerows}<br><b>Contract</b>{contract}<br>"
                                     f"<div class=kv><span>final command</span><span class=u>python -m agent.run</span></div>"
                                     f"<div class=kv><span>checker</span><span class=u>{spec['checker']}</span></div>"
                                     f"<div class=kv><span>upload</span><span class=u>manual</span></div>")}
    parts.append("</svg>")
    return "".join(parts), nodes


# adapter approach -> which methodology-owned model-approach node handles it
_APPROACH_NODE = {
    "guidance": "app_guidance", "guide_reversion": "app_guidance", "stated": "app_guidance",
    "seasonal": "app_seasonal", "series_trend": "app_seasonal", "series_growth": "app_seasonal",
    "seasonal_segment": "app_seasonal",
    "bridge": "app_bridge", "fy_ni_bridge": "app_bridge", "segment_margin": "app_bridge",
}
_APPROACH_META = {
    "app_guidance": ("Guidance anchor", "management's published numbers",
                     "Anchor to management guidance: midpoint, stated range, or reversion toward the guide. "
                     "Methodology 1 §5 guidance calibration. Metrics: ADI Rev/EPS, HD comp, HAS OP."),
    "app_seasonal": ("Seasonal + trend", "historical anchor + recent growth",
                     "Same-quarter seasonal anchor + recent-trend adjustment on the extracted actual series. "
                     "Methodology 1 §5 seasonal anchor + recent-trend. Metrics: HD net sales/EPS, ADI GM, HAS net fees, DE net sales."),
    "app_bridge": ("Accounting bridge", "EPS / OP via financial identities",
                   "Derive via accounting identities: EPS = after-tax profit ÷ shares; operating profit = base × margin/conversion; "
                   "segment sales × margin. Methodology 1 §4/§9. Metrics: DE EPS & PPA OP, HAS EPS."),
}


def _approach_html(aid):
    A = methodology.MODEL_APPROACHES[aid]
    formulas = "<pre>" + "\n".join(html.escape(f) for f in A["formulas"]) + "</pre>"
    metrics = ("<ul class=u style='margin:4px 0;padding-left:18px'>"
               + "".join(f"<li>{html.escape(m)}</li>" for m in A["metrics"]) + "</ul>")
    return (f"<div class=u style='margin-bottom:6px'>{html.escape(A['desc'])}</div>"
            f"<b class=u>Formulas</b>{formulas}<b class=u>Metrics it handles</b>{metrics}")


def _combined_svg(manifest, spec):
    """One combined network graph (current form): four companies → ingestion →
    Methodology 1 → the model approaches Methodology 1 OWNS → stats control →
    output. The deferred candidate/backtest/ensemble nodes are removed."""
    W, H = 1060, 700
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:1060px">']
    nodes = {}
    xs = [120, 360, 600, 840]
    cos = manifest["companies"]

    def band(lab, y, tag, col):
        parts.append(f'<text x="18" y="{y}" fill="{col}" style="font:600 11px sans-serif">{lab}</text>')
        if tag:
            parts.append(f'<text x="210" y="{y}" fill="#5c6470" style="font:10px sans-serif">{tag}</text>')

    band("INPUT · four companies", 30, "company code + required output", "#6b7480")
    band("P1 · DATA INGESTION", 122, "corpus → extract → panel", "#6aa0ff")
    band("P2 · METHODOLOGY 1", 258, "fixed — decides HOW and owns the model approaches", "#8b93a1")
    band("P3 · MODEL APPROACHES", 350, "owned by Methodology 1 (backtesting deferred)", "#f0b768")
    band("P4 · CONTROL · BACKTEST · PARAM-EVAL", 458, "validate + walk-forward backtest + model grid — run alongside", "#8b93a1")
    band("P5 · OUTPUT LAYER", 530, "4 workbooks · 12 numbers", "#3fb950")

    # INPUT — four companies
    incx = []
    for c, x in zip(cos, xs):
        parts.append(_rect(x, 42, 170, 44, f"co_{c['ticker']}", "#6aa0ff1e", "#6aa0ff",
                           [f"{c['ticker']} · {c['company'][:16]}", c["period"]]))
        incx.append(x + 85)
        vals = "".join(f"{m['label']}: {(_fmt(m['point'], m['kind']) if m['point'] is not None else '—')} {m['units']}<br>"
                       for m in c["metrics"])
        nodes[f"co_{c['ticker']}"] = {"t": f"{c['company']} — input", "plug": "code",
                                      "sub": f"required output · {c['period']}", "body": vals}

    # P1 ingestion — sources → extract
    for (nid, label), x in zip([("src_filings", "Filings"), ("src_transcripts", "Transcripts"),
                                ("src_slides", "Slides")], [300, 520, 740]):
        parts.append(_rect(x, 132, 140, 28, nid, "#1a2531", "#33506e", [label]))
        parts.append(f'<path d="M{x+70},160 C{x+70},178 520,178 520,190" fill="none" stroke="#2b3745" stroke-width="0.8"/>')
        nodes[nid] = {"t": label, "plug": "code", "sub": "P1 · Data ingestion",
                      "body": "Frozen corpus document type (priority: filings > release > slides > call > Q&A)."}
    ex = (430, 190, 200, 42)
    parts.append(_rect(*ex, "u_extract", "#2a2312", "#7a5a1e",
                       ["Extract → period panel", "per company · actuals + guidance"]))
    excx = ex[0] + ex[2] / 2
    for cx0 in incx:
        parts.append(f'<path d="M{cx0},86 C{cx0},112 {excx},112 {excx},{ex[1]}" fill="none" stroke="#2b3745" stroke-width="1"/>')
    nodes["u_extract"] = {"t": "Extractor → period panel", "plug": "hot", "sub": "P1 · Data ingestion (hot-swap)",
                          "body": "Text→panel per company: historical actuals series + issued guidance, event-deduped."}

    # P2 Methodology 1
    mth = (380, 268, 300, 40)
    parts.append(_rect(*mth, "methodology", "#1a1f27", "#4a5568",
                       ["Methodology 1 · click to read", "filing baseline + guidance — owns ↓ approaches"]))
    parts.append(f'<line x1="{excx}" y1="{ex[1]+ex[3]}" x2="{mth[0]+mth[2]/2}" y2="{mth[1]}" stroke="#5a4620" stroke-width="1.4"/>')
    mthcx = mth[0] + mth[2] / 2
    nodes["methodology"] = {"t": methodology.METHODOLOGY_1["name"], "plug": "no",
                            "sub": "P2 · FIXED / constitutional — the agent reads this and obeys it",
                            "body": _methodology_html()}

    # LLM driver (optional, OpenAI) — qualitative signals from calls/slides (§6)
    from .llm import LLM
    _llm = LLM()
    ldc = "#6aa0ff" if _llm.available else "#5c6470"
    parts.append(_rect(700, 190, 214, 42, "llm_driver",
                       (ldc + "1e") if _llm.available else "#171c24", ldc,
                       ["LLM driver · signals (§6)",
                        ("OpenAI: " + _llm.model) if _llm.available else "set OPENAI_API_KEY in .env"],
                       dash=not _llm.available))
    parts.append('<path d="M810,160 C810,176 805,176 805,190" fill="none" stroke="#2b3745" stroke-width="0.8"/>')
    parts.append('<path d="M700,222 C640,248 690,262 680,278" fill="none" stroke="#3a4658" '
                 'stroke-width="0.8" stroke-dasharray="3 3"/>')
    nodes["llm_driver"] = {
        "t": "LLM driver — qualitative signals (§6)",
        "plug": "code" if _llm.available else "no",
        "sub": "OpenAI · reads calls/slides · never sets the numbers",
        "body": (f"<b>OpenAI driver active</b> (model {_llm.model}, disk-cached). Reads the latest call/slides "
                 "and codes demand / pricing / inventory / management-confidence / guidance-direction on a "
                 "−2..+2 scale with reasons. Informational only — feeds the deferred regime/scenario layer; "
                 "it never sets a forecast number (Methodology 1 §6)."
                 if _llm.available else
                 "<b>No OpenAI key.</b> Set <code>OPENAI_API_KEY</code> in the <code>.env</code> file to enable. "
                 "The numeric pipeline runs fine without it — the LLM only reads / extracts / explains, it never "
                 "sets the forecast numbers (Methodology 1).")}

    # P3 model approaches — OWNED by Methodology 1 (dashed container = belonging)
    parts.append('<rect x="150" y="356" width="760" height="88" rx="11" fill="#1d160c" '
                 'stroke="#7a5a1e" stroke-dasharray="5 4" opacity="0.85"/>')
    parts.append('<text x="164" y="372" fill="#f0b768" style="font:10px sans-serif">▸ owned by Methodology 1</text>')
    app_xy = {"app_guidance": (200, 384, 200, 46), "app_seasonal": (430, 384, 200, 46),
              "app_bridge": (660, 384, 200, 46)}
    for aid, (x, y, w, h) in app_xy.items():
        t, sub, _ = _APPROACH_META[aid]
        parts.append(_rect(x, y, w, h, aid, "#2a2013", "#c78a34", [t, sub]))
        parts.append(f'<path d="M{mthcx},{mth[1]+mth[3]} C{mthcx},350 {x+w/2},350 {x+w/2},{y}" '
                     f'fill="none" stroke="#5a4620" stroke-width="1" stroke-dasharray="3 3"/>')
        nodes[aid] = {"t": f"{t} — model approach", "plug": "hot",
                      "sub": "P3 · owned by Methodology 1 · formulas ↓", "body": _approach_html(aid)}

    # P4 · stats control + prequential backtest (run alongside the output)
    parts.append('<line x1="530" y1="444" x2="530" y2="458" stroke="#3a4658" stroke-width="1.4"/>')
    for cxn in (234, 530, 826):
        parts.append(f'<path d="M530,458 C530,464 {cxn},462 {cxn},470" fill="none" stroke="#3a4658" stroke-width="1"/>')
    parts.append(_rect(100, 470, 268, 38, "stats_control", "#1b222c", "#3a4658",
                       ["Stats control · validate", "finite · range · sign · band"]))
    parts.append(_rect(396, 470, 268, 38, "prequential", "#1b222c", "#3a4658",
                       ["Prequential backtest", "walk-forward · coverage · Kupiec"]))
    parts.append(_rect(692, 470, 268, 38, "param_eval", "#1b222c", "#3a4658",
                       ["Parameter eval", "model grid · rank · robustness"]))
    from . import stats_control as _sc
    summ_sc = {"pass": 0, "warn": 0, "fail": 0, "n": 0}
    for c in cos:                                     # per company so duplicate labels (EPS) aren't merged
        r = _sc.summarize(_sc.validate(c["metrics"]))
        for k in summ_sc:
            summ_sc[k] += r[k]
    checkdoc = "".join(f"<div class=kv><span>{html.escape(x)}</span></div>" for x in _sc.CHECKS_DOC)
    nodes["stats_control"] = {"t": "Stats control — validate", "plug": "no",
                              "sub": "P4 · runs after the model approaches, before output",
                              "body": (f"Deterministic control gate on every produced number "
                                       f"(Methodology 1 §11 units + consistency; §13 never hide failures).<br>"
                                       f"<div class=kv><span>latest run</span><span>"
                                       f"{summ_sc['pass']} pass · {summ_sc['warn']} warn · {summ_sc['fail']} fail "
                                       f"/ {summ_sc['n']}</span></div><br><b class=u>Checks</b>{checkdoc}")}
    nodes["prequential"] = {"t": "Prequential backtest", "plug": "no",
                            "sub": "P4 · walk-forward, runs alongside the output",
                            "body": ("Predictive-sequential backtest (pulled from quant-projects garch_var, "
                                     "walk-forward VaR method). At each historical origin, fit on data-up-to-then, "
                                     "forecast next, score the realized actual.<br><br>"
                                     "<b class=u>Emits</b><div class=kv><span>point error</span>"
                                     "<span class=u>prequential MAE / RMSE / WAPE</span></div>"
                                     "<div class=kv><span>band coverage</span>"
                                     "<span class=u>VaR-style breach rate vs expected</span></div>"
                                     "<div class=kv><span>Kupiec POF</span>"
                                     "<span class=u>LR test that breach rate is calibrated (χ²₁)</span></div><br>"
                                     "<span class=u>Runs where a historical series exists (ADI full panel, HD releases).</span>"
                                     "<br><br><a href='/backtest'>▸ open full backtest results &amp; analysis</a>")}
    nodes["param_eval"] = {"t": "Parameter eval — model grid", "plug": "no",
                           "sub": "P4 · pulled from quant-projects (compare_models + sensitivity)",
                           "body": ("For each metric, evaluate a GRID of candidate models "
                                    "(seasonal-naive · naive · drift · trend · AR · ETS · guidance) by prequential "
                                    "out-of-sample error, rank them, pick the best and check it beats the "
                                    "Seasonal-Naive baseline — the <b>compare_models</b> analog. Then a "
                                    "<b>sensitivity</b> grid over the backtest window flags whether the winner is "
                                    "robust or fragile.<br><br>"
                                    "<span class=u>Findings drive model choice: e.g. ADI EPS → guidance wins "
                                    "(validates the methodology); ADI gross margin → AR beats the drift the pipeline "
                                    "currently uses.</span><br><br>"
                                    "<a href='/backtest'>▸ see the per-metric model ranking</a>")}

    # P5 output — four workbooks + OUTPUT spec
    for c, x in zip(cos, xs):
        ready = c["wired"] and all(m["point"] is not None for m in c["metrics"])
        col = "#3fb950" if ready else "#8b93a1"
        summ = "  ".join(_fmt(m["point"], m["kind"]) for m in c["metrics"] if m["point"] is not None) or "pending"
        parts.append(_rect(x, 542, 170, 46, f"out_{c['ticker']}", "#16241b", col, [c["file"], summ],
                           ring=("#3fb950" if ready else None)))
        parts.append(f'<path d="M530,508 C530,526 {x+85},526 {x+85},542" fill="none" stroke="#3a6b47" stroke-width="1.2"/>')
        mrows = "".join(f"<div class=kv><span>{html.escape(m['label'])} <span class=u>{m['units']}</span></span>"
                        f"<span>{(_fmt(m['point'], m['kind']) if m['point'] is not None else '—')}</span></div>"
                        for m in c["metrics"])
        nodes[f"out_{c['ticker']}"] = {"t": c["file"], "plug": "no", "sub": "P5 · output workbook",
                                       "body": f"Summary sheet for {c['company']} · {c['period']}.<br>{mrows}"}
    parts.append(_rect(378, 618, 304, 38, "output_spec", "#12271a", "#2f6b43",
                       [f"OUTPUT · {spec['n_numbers']} numbers → {len(spec['files'])} .xlsx", "click: what we emit"]))
    for x in xs:
        parts.append(f'<line x1="{x+85}" y1="588" x2="530" y2="618" stroke="#284d33" stroke-width="0.7"/>')
    filerows = "".join(f"<div class=kv><span>{f['file']}</span><span class=u>{', '.join(m['label'] for m in f['metrics'])}</span></div>"
                       for f in spec["files"])
    contract = "".join(f"<div class=kv><span>{html.escape(x)}</span></div>" for x in spec["contract"])
    nodes["output_spec"] = {"t": "Output layer — the deliverable", "plug": "no", "sub": "P5 · FIXED",
                            "body": (f"<b>{spec['deliverable']}</b> — {spec['n_numbers']} numbers.<br><br>"
                                     f"<b>Files</b>{filerows}<br><b>Contract</b>{contract}")}
    parts.append("</svg>")
    return "".join(parts), nodes


def _modal_js(nodes):
    return ("<div id=ov onclick=\"if(event.target.id=='ov')hide()\"><div id=panel></div></div>"
            f"<script>var N={_json.dumps(nodes)};"
            "function show(id){var n=N[id];if(!n)return;var h='<span class=x onclick=hide()>close ✕</span>';"
            "h+='<h3>'+n.t+'</h3><div class=u>'+n.sub+'</div>';"
            "h+='<div class=kv><span>plug</span><span>'+n.plug+'</span></div>';"
            "if(n.body)h+='<div style=\"margin:10px 0\">'+n.body+'</div>';"
            "if(n.producer)h+='<div class=kv><span>code producer</span><span>'+n.producer+'</span></div>';"
            "if(n.spec)h+='<pre>'+JSON.stringify(n.spec,null,2)+'</pre>';"
            "document.getElementById('panel').innerHTML=h;document.getElementById('ov').style.display='flex';}"
            "function hide(){document.getElementById('ov').style.display='none';}</script>")


@app.get("/graph")
def graph():
    from flask import request
    if not request.args.get("t"):
        manifest = output.run_pipeline(write=False)
        spec = output.output_spec()
        svg, nodes = _combined_svg(manifest, spec)
        focus = "".join(f"<a class=phase href='/graph?t={t}'>{t} detail →</a>" for t in TICKERS)
        legend = ("<div class=leg>Node plug: <span class=sw style='background:#f0b768'></span>hot-swap"
                  "<span class=sw style='background:#6aa0ff'></span>code"
                  "<span class=sw style='background:#8b93a1'></span>fixed / pending"
                  "<span class=sw style='background:#3fb950'></span>ready output</div>")
        run_card = ("<div class=card><button id=runbtn onclick='runPipe()'>▶ Run pipeline</button> "
                    "<span class=u>runs all four companies through the pipeline — nodes light up as the agent runs them</span>"
                    "<div id=runlog>click ▶ Run to watch the agent step through the nodes…</div></div>")
        run_js = ("<script>function runPipe(){var b=document.getElementById('runbtn');b.disabled=true;b.textContent='running…';"
                  "var L=document.getElementById('runlog');L.textContent='';"
                  "document.querySelectorAll('.gnode').forEach(function(g){g.classList.remove('run','done');});"
                  "var es=new EventSource('/api/run');var prev=null;"
                  "es.onmessage=function(e){var d=JSON.parse(e.data);"
                  "if(d.node){var id='n_'+d.node;if(prev&&prev!=id){var p=document.getElementById(prev);"
                  "if(p){p.classList.remove('run');p.classList.add('done');}}"
                  "var el=document.getElementById(id);if(el)el.classList.add('run');prev=id;}"
                  "if(d.log){var s=document.createElement('div');if(d.cls)s.className=d.cls;s.textContent=d.log;"
                  "L.appendChild(s);L.scrollTop=L.scrollHeight;}"
                  "if(d.done){es.close();b.disabled=false;b.textContent='▶ Run again';b.classList.add('g');"
                  "var el=document.getElementById('n_'+d.node);if(el)el.classList.add('run');}};"
                  "es.onerror=function(){es.close();b.disabled=false;b.textContent='▶ Run pipeline';};}</script>")
        body = (f"<h1>One pipeline · four companies · one output layer</h1>"
                f"<div class=sub>All four companies flow through the same governed pipeline; the "
                f"<b>output layer</b> emits the {spec['n_numbers']} numbers as {len(spec['files'])} workbooks. "
                f"Click a node to inspect it; click ▶ Run to watch the agent execute them.</div>"
                f"{run_card}"
                f"{legend}<div class=card style='padding:10px'>{svg}</div>"
                f"<div class=card><b>{manifest['n_filled']}/{manifest['n_total']} numbers produced</b> "
                f"· {manifest['wired']}/4 companies wired · <a href='/output'>output detail</a>"
                f" · <a href='/backtest'>▸ prequential backtest results &amp; analysis</a></div>"
                f"<div>Drill into learned weights: {focus}</div>"
                f"<a href='/'>← overview</a>{_modal_js(nodes)}{run_js}")
        return Response(_page("Pipeline", body), mimetype="text/html")
    ticker = request.args.get("t", "ADI").upper()
    if ticker not in FOLDER:
        ticker = "ADI"
    fc = forecast_company(ticker)
    labels = [m.label for m in fc["metrics"]]
    sel = request.args.get("m") or labels[0]
    mf = next((m for m in fc["metrics"] if m.label == sel), fc["metrics"][0])
    svg, nodes = _graph_svg(fc, mf)

    # company selector: all four; selected highlighted; unwired marked pending
    tsel = ""
    for t in TICKERS:
        on = t == ticker
        pend = "" if t in METRIC_MAP else " ·pending"
        style = "background:#22303e;color:#e6e9ef" if on else ("opacity:.55" if pend else "")
        tsel += f"<a class=phase href='/graph?t={t}' style=\"{style}\">{t}{pend}</a>"
    # metric selector: this company's required metrics (companies.json); selected highlighted
    msel = "".join(f"<a class=phase href='/graph?t={ticker}&m={html.escape(l)}' "
                   f"style=\"{'background:#22303e;color:#e6e9ef' if l == sel else ''}\">{html.escape(l)}</a>"
                   for l in labels)
    legend = ("<div class=leg>Node plug: <span class=sw style='background:#f0b768'></span>hot-swap (JSON)"
              "<span class=sw style='background:#6aa0ff'></span>code"
              "<span class=sw style='background:#8b93a1'></span>fixed/governance"
              "<span class=sw style='background:#3fb950'></span>eligible (edge thickness = learned weight)</div>")
    form = ("<div class=card><b>Hot-swap a candidate model</b>"
            "<div class=u>Paste a JSON node. Validate runs the agent's pre-live check; Save writes it to "
            "agent/nodes/models/ and it competes on the next run — no code change.</div>"
            "<textarea id=nodejson rows=7 style='width:100%;background:#0d1117;color:#c9d3df;border:1px solid #263040;"
            "border-radius:8px;padding:10px;font:12px ui-monospace,monospace'>"
            '{\n  "id": "my_model",\n  "label": "My research model",\n  "plug": "hot",\n'
            '  "applies_to": ["money","eps"],\n  "spec": { "type": "ewma", "alpha": 0.4 }\n}</textarea>'
            "<div style='margin-top:8px'><button onclick='v/**/al()' id=vb>Validate</button> "
            "<button onclick='sv()'>Validate + Save</button> <span id=vres class=u></span></div></div>")

    js = ("<div id=ov onclick=\"if(event.target.id=='ov')hide()\"><div id=panel></div></div>"
          f"<script>var N={_json.dumps(nodes)};"
          "function show(id){var n=N[id];if(!n)return;var h='<span class=x onclick=hide()>close ✕</span>';"
          "h+='<h3>'+n.t+'</h3><div class=u>'+n.sub+'</div>';"
          "h+='<div class=kv><span>plug</span><span>'+n.plug+'</span></div>';"
          "if(n.body)h+='<div style=\"margin:10px 0\">'+n.body+'</div>';"
          "if(n.producer)h+='<div class=kv><span>code producer</span><span>'+n.producer+'</span></div>';"
          "if(n.spec)h+='<pre>'+JSON.stringify(n.spec,null,2)+'</pre>';"
          "document.getElementById('panel').innerHTML=h;document.getElementById('ov').style.display='flex';}"
          "function hide(){document.getElementById('ov').style.display='none';}"
          "function val(){fetch('/api/validate',{method:'POST',headers:{'Content-Type':'application/json'},"
          "body:document.getElementById('nodejson').value}).then(r=>r.json()).then(j=>{"
          "document.getElementById('vres').textContent=j.verdict+' — '+(j.messages||[]).join('; ');});}"
          "document.getElementById('vb').onclick=val;"
          "function sv(){fetch('/api/addnode',{method:'POST',headers:{'Content-Type':'application/json'},"
          "body:document.getElementById('nodejson').value}).then(r=>r.json()).then(j=>{"
          "document.getElementById('vres').textContent=j.saved?('saved '+j.file+' — reload'):('not saved: '+j.verdict);"
          "if(j.saved)setTimeout(()=>location.reload(),700);});}</script>")

    body = (f"<h1>Governed forecasting graph <span class=badge>{html.escape(fc['company'])}</span></h1>"
            f"<div class=sub>Layered like a network: corpus → extract → parallel candidate nodes → "
            f"backtest gate (learns weights) → ensemble → workbook. "
            f"Fixed methodology vs hot-swappable research layer.</div>"
            f"<div>Company: {tsel}</div><div style='margin-top:6px'>Metric: {msel}</div>"
            f"{legend}<div class=card style='padding:10px'>{svg}</div>{form}"
            f"<a href='/'>← overview</a> · <a href='/c/{ticker}'>metric detail →</a>{js}")
    return Response(_page("Graph", body), mimetype="text/html")


@app.get("/api/run")
def api_run():
    """Run the whole pipeline and stream node-by-node events (SSE) so the graph can
    light up the nodes the agent is running, with a live thinking log."""
    def sse(d):
        return f"data: {_json.dumps(d)}\n\n"

    def gen():
        yield sse({"node": "methodology", "cls": "n",
                   "log": "▸ Reading Methodology 1 — filing baseline + guidance calibration (the agent obeys this)"})
        time.sleep(0.5)
        done = 0
        for t in output.TICKERS:
            a = methodology.adapter(t)
            sp = company_spec(t)
            yield sse({"node": f"co_{t}", "cls": "n",
                       "log": f"● {t} · {a.get('name', t)} — input: (company code, required output · {sp['period']})"})
            time.sleep(0.3)
            yield sse({"node": "u_extract", "log": f"   P1 · ingest → extract period panel  ({t})"})
            time.sleep(0.3)
            # optional LLM driver — qualitative signals (reads calls/slides; never sets numbers)
            from .llm import LLM as _LLM
            _llm = _LLM()
            if _llm.available:
                from . import signals as _signals
                s = _signals.qualitative_signals(t, _llm)
                msg = s["summary"] if s else "(no signal)"
                yield sse({"node": "llm_driver", "cls": "n", "log": f"   LLM driver · calls/slides → {msg}"})
            else:
                yield sse({"node": "llm_driver", "cls": "d",
                           "log": "   LLM driver · no key (set OPENAI_API_KEY in .env) — numeric pipeline unaffected"})
            time.sleep(0.25)
            d = direct.forecast(t)
            metrics = []
            for m in sp["metrics"]:
                lbl = m["label"]
                mm = d["metrics"].get(lbl)
                metrics.append({"label": lbl, "units": m["units"], "band": mm["band"] if mm else None,
                                "point": mm["point"] if mm else None, "kind": mm["kind"] if mm else None})
                approach = a.get("metrics", {}).get(lbl, {}).get("approach", "")
                anode = _APPROACH_NODE.get(approach, "app_seasonal")
                aname = _APPROACH_META.get(anode, ("", ""))[0]
                val = mm["point"] if mm else "—"
                basis = (mm["basis"][:50] if mm else "")
                yield sse({"node": anode, "cls": "d",
                           "log": f"   P3 · {aname} → {lbl} = {val}  [{basis}]"})
                if mm and mm["point"] is not None:
                    done += 1
                time.sleep(0.22)
            # P4 · stats control validation (after approaches, before output)
            from . import stats_control as _sc
            res = _sc.validate(metrics)
            sm = _sc.summarize(res)
            yield sse({"node": "stats_control", "cls": "n",
                       "log": f"   P4 · stats control → {sm['pass']} pass · {sm['warn']} warn · {sm['fail']} fail"})
            for lbl, r in res.items():
                if r["verdict"] != "pass":
                    bad = ", ".join(c["name"] for c in r["checks"] if not c["ok"])
                    yield sse({"cls": "d", "log": f"        {'✗' if r['verdict']=='fail' else '⚠'} {lbl}: {r['verdict']} ({bad})"})
            time.sleep(0.25)
            # P4 · prequential backtest (walk-forward, runs alongside the output)
            from . import prequential as _pq
            ran = 0
            for mm in metrics:
                r = _pq.backtest_metric(t, mm["label"], mm["kind"] or "money")
                if r.get("insufficient"):
                    continue
                ran += 1
                kp = f"{r['kupiec_pvalue']:.2f}" if r.get("kupiec_pvalue") is not None else "n/a"
                br = r["breach_rate"] if r["breach_rate"] is not None else 0.0
                flag = " ⚠miscalibrated" if (r.get("kupiec_pvalue") is not None and r["kupiec_pvalue"] < 0.05) else ""
                yield sse({"node": "prequential", "cls": "d",
                           "log": f"   P4 · backtest {mm['label']}: n={r['n_origins']} {_pq.headline_error(r)} "
                                  f"breach={br:.0%}/exp{r['expected_breach']:.0%} Kupiec p={kp}{flag}"})
                time.sleep(0.16)
            if not ran:
                yield sse({"node": "prequential", "cls": "d",
                           "log": f"   P4 · backtest ({t}) skipped — no historical series yet"})
            time.sleep(0.2)
            # P4 · parameter eval (model grid: compare candidates, pick best, robustness)
            from . import param_eval as _pe
            for mm in metrics:
                c = _pe.compare(t, mm["label"], mm["kind"] or "money")
                if c.get("insufficient"):
                    continue
                sens = c.get("sensitivity") or {}
                tag = ("beats baseline" if c["beats_baseline"] else "≤ baseline") + \
                      (", robust" if sens.get("robust") else ", window-sensitive")
                yield sse({"node": "param_eval", "cls": "d",
                           "log": f"   P4 · param-eval {mm['label']}: best={c['best']} ({tag})"})
                time.sleep(0.14)
            time.sleep(0.15)
            path = workbook.write_direct(sp["outputFile"], sp["period"], metrics)
            yield sse({"node": f"out_{t}", "cls": "n", "log": f"   P5 · output → wrote {os.path.basename(path)}"})
            time.sleep(0.3)
        yield sse({"node": "output_spec", "cls": "n", "done": True,
                   "log": f"✓ done — {done}/12 numbers → 4 workbooks in submission/  (npm run check:submission)"})

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/validate")
def api_validate():
    from flask import request
    try:
        node = request.get_json(force=True)
    except Exception as exc:
        return {"verdict": "invalid", "messages": [f"bad JSON: {exc}"]}
    return governance.validate_node(node)


@app.post("/api/addnode")
def api_addnode():
    from flask import request
    try:
        node = request.get_json(force=True)
    except Exception as exc:
        return {"saved": False, "verdict": "invalid", "messages": [f"bad JSON: {exc}"]}
    v = governance.validate_node(node)
    if v.get("verdict") not in ("publishable", "declarable"):
        return {"saved": False, **v}
    os.makedirs(governance.NODES_DIR, exist_ok=True)
    safe = "".join(c for c in str(node.get("id", "node")) if c.isalnum() or c in "_-")[:40] or "node"
    fn = f"{safe}.json"
    with open(os.path.join(governance.NODES_DIR, fn), "w", encoding="utf-8") as fh:
        _json.dump(node, fh, ensure_ascii=False, indent=2)
    return {"saved": True, "file": fn, **v}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8010"))
    app.run(host="127.0.0.1", port=port, debug=False)
