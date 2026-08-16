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

from flask import Flask, Response, redirect

import json as _json

from .forecast import forecast_company, METRIC_MAP
from .corpus import FOLDER
from . import workbook, governance

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
    rows = ""
    for t in TICKERS:
        mapped = t in METRIC_MAP
        try:
            fc = forecast_company(t) if mapped else None
        except Exception as exc:
            fc = None
            mapped = False
            note = f"<span class=u>error: {html.escape(str(exc))}</span>"
        cells = ""
        if fc:
            for m in fc["metrics"]:
                bd = m.band
                band = f"{_fmt(bd[0], m.kind)}–{_fmt(bd[1], m.kind)}" if bd else ""
                cells += (f"<div class=mrow><span>{html.escape(m.label)} "
                          f"<span class=u>{html.escape(m.units)}</span></span>"
                          f"<span><span class=pt>{_fmt(m.point, m.kind)}</span> "
                          f"<span class=band>{band}</span></span></div>")
            head = (f"<b>{html.escape(fc['company'])}</b> "
                    f"<span class=badge>{html.escape(fc['period'])}</span> "
                    f"<span class=u>· {fc['panel_rows']} periods</span>")
        else:
            head = f"<b>{t}</b> <span class=badge>extractor pending</span>"
            cells = "<div class=u>corpus loads; ADI-shape extractor not yet wired for this company</div>"
        rows += (f"<div class=card><div style='display:flex;justify-content:space-between'>"
                 f"<div>{head}</div><a href='/c/{t}'>detail →</a></div>{cells}</div>")
    phases = "".join(f"<span class=phase>{p}</span>" for p in
                     ["1 · extract text→panel", "2 · candidate models", "3 · causal prequential backtest",
                      "4 · paired baseline gate", "5 · prior-origin weights", "6 · fuse + band", "7 · write xlsx"])
    body = (f"<h1>Agents vs Wall Street — forecasting agent</h1>"
            f"<div class=sub>Guidance competes as a backtestable candidate. A baseline-only warm-up "
            f"feeds causal paired evaluation; each origin's ensemble uses errors from earlier origins only.</div>"
            f"<div>{phases}</div><h2>Four companies · twelve metrics</h2>{rows}"
            f"<div class=card><a href='/run'>▶ write the 4 workbooks to submission/</a></div>")
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
        ensemble_error = res.get("ens_error")
        paired_baseline_error = res.get("ensemble_baseline_error")
        skill = res.get("ensemble_skill")
        if ensemble_error is not None and paired_baseline_error is not None and skill is not None:
            backtest_summary = (
                f"causal ensemble MAE {ensemble_error:.3f} vs paired baseline "
                f"{paired_baseline_error:.3f} · skill {skill:.1%} · "
                f"{res.get('n_ensemble_origins', 0)} adaptive origins"
            )
        else:
            backtest_summary = "baseline-only warm-up; insufficient adaptive origins"
        blocks += (f"<div class=card>"
                   f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
                   f"<div><b>{html.escape(m.label)}</b> <span class=u>{html.escape(m.units)}</span> {anchor}</div>"
                   f"<div><span class=pt>{_fmt(m.point, m.kind)}</span> "
                   f"<span class=band>band {band}</span></div></div>"
                   f"<div style='margin:8px 0'>{spark} <span class=u>backtest: {backtest_summary}"
                   f"{' · FALLBACK' if res['fallback'] else ''}</span></div>"
                   f"<table><thead><tr><th>candidate</th><th>paired MAE</th><th>pred</th>"
                   f"<th>weight</th><th>n</th></tr></thead><tbody>{lb}</tbody></table>"
                   f"<div style='margin-top:8px'>{ev}</div></div>")
    body = (f"<h1>{html.escape(fc['company'])} <span class=badge>{html.escape(fc['period'])}</span></h1>"
            f"<div class=sub>{fc['panel_rows']} periods extracted · causal prequential ensemble: "
            f"baseline-only warm-up, paired seasonal-naive gate, prior-origin inverse-MAE weights</div>"
            f"<a href='/'>← overview</a>{blocks}")
    return Response(_page(fc["company"], body), mimetype="text/html")


@app.get("/run")
def run():
    lines = ""
    for t in TICKERS:
        if t not in METRIC_MAP:
            lines += f"<div class=mrow><span>{t}</span><span class=u>skipped — extractor pending</span></div>"
            continue
        try:
            fc = forecast_company(t)
            path = workbook.write_workbook(fc)
            vals = ", ".join(f"{m.label}={_fmt(m.point, m.kind)}" for m in fc["metrics"] if m.point is not None)
            lines += f"<div class=mrow><span>{os.path.basename(path)}</span><span class=u>{html.escape(vals)}</span></div>"
        except Exception as exc:
            lines += f"<div class=mrow><span>{t}</span><span class=u>error: {html.escape(str(exc))}</span></div>"
    body = (f"<h1>Write workbooks</h1><div class=sub>submission/*.xlsx — validate with "
            f"<code>npm run check:submission</code></div><div class=card>{lines}</div>"
            f"<a href='/'>← overview</a>")
    return Response(_page("Run", body), mimetype="text/html")


_PLUG_COLOR = {"hot": "#f0b768", "code": "#6aa0ff", "no": "#8b93a1"}
_PHASE_Y = {"P1": (44, 112), "P2": (142, 210), "P3": (242, 362),
            "P4": (398, 476), "P5": (516, 592)}


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
    return f'<g class=gnode onclick="show(\'{nid}\')">{rr}{r}{txt}</g>'


def _graph_svg(fc, mf):
    """Layered NN-style graph for one metric. Returns (svg, nodes_js)."""
    W, H = 1060, 620
    lb = {r["model"]: r for r in mf.result.get("leaderboard", [])} if mf and mf.point is not None else {}
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:1060px">']
    nodes = {}

    # phase bands
    for p in governance.PHASES:
        y0, y1 = _PHASE_Y[p["id"]]
        parts.append(f'<rect x="6" y="{y0-4}" width="{W-12}" height="{y1-y0+8}" rx="9" '
                     f'fill="#12171e" stroke="#1c242e"/>')
        plug = p["plug"]
        col = _PLUG_COLOR[plug]
        tag = {"hot": "HOT-SWAP", "code": "CODE", "no": "FIXED"}[plug]
        parts.append(f'<text x="18" y="{y0+12}" fill="#6b7480" font="600 11px sans-serif" '
                     f'style="font:600 11px sans-serif">{p["id"]} · {html.escape(p["title"])}</text>')
        parts.append(f'<text x="18" y="{y0+27}" fill="{col}" style="font:10px sans-serif">{tag}</text>')

    def cx(x, w): return x + w / 2

    # P1 sources
    src = [("src_filings", "Filings"), ("src_transcripts", "Transcripts"), ("src_slides", "Slides")]
    sx = [300, 520, 740]
    p1c = []
    for (nid, label), x in zip(src, sx):
        parts.append(_rect(x, 60, 140, 34, nid, "#1a2531", "#33506e", [label]))
        p1c.append((cx(x, 140), 94))
        nodes[nid] = {"t": label, "plug": "code", "sub": "P1 · Ingest",
                      "body": f"Frozen corpus document type. {fc['company']} has {fc['panel_rows']} extracted periods."}
    # P2 extractor
    ex_x, ex_w = 400, 240
    parts.append(_rect(ex_x, 158, ex_w, 40, "extract", "#2a2312", "#7a5a1e",
                       ["Extract → period panel", f"{fc['ticker']} · actuals + issued guidance"]))
    exc = (cx(ex_x, ex_w), 198); ext = (cx(ex_x, ex_w), 158)
    nodes["extract"] = {"t": "Extractor → period panel", "plug": "hot", "sub": "P2 · Extract (hot-swap)",
                        "body": f"Text→panel for {fc['company']}. Per-metric prose+table regex, LLM fallback seam. "
                                f"Panel: {fc['panel_rows']} periods."}
    for c in p1c:
        parts.append(f'<path d="M{c[0]},{c[1]} C{c[0]},130 {ext[0]},130 {ext[0]},{ext[1]}" fill="none" stroke="#2b3745" stroke-width="1"/>')

    # P3 candidate layer (+ guidance)
    models = governance.active_models(mf.kind) if (mf and mf.kind) else governance.active_models("money")
    ids = [m.id for m in models] + ["guidance"]
    mnode = {m.id: m for m in models}
    n = len(ids)
    gap, mw = 10, 0
    mw = (W - 40 - (n - 1) * gap) / n
    p3c = {}
    for i, mid in enumerate(ids):
        x = 20 + i * (mw + gap)
        row = lb.get(mid, {})
        plug = row.get("plug", "hot" if mid == "guidance" else mnode.get(mid).plug if mid in mnode else "code")
        col = _PLUG_COLOR.get(plug, "#6aa0ff")
        elig = row.get("eligible")
        w = row.get("weight", 0.0)
        lab = "guidance" if mid == "guidance" else mnode[mid].label if mid in mnode else mid
        short = (lab[:16] + "…") if len(lab) > 17 else lab
        ring = "#3fb950" if elig else None
        fill = col + "22"
        parts.append(_rect(x, 278, mw, 50, mid, fill, col, [short, f"w {w:.2f}"], ring=ring))
        p3c[mid] = (cx(x, mw), 328, cx(x, mw), 278)
        # edge extractor -> model
        parts.append(f'<path d="M{exc[0]},{exc[1]} C{exc[0]},240 {p3c[mid][2]},240 {p3c[mid][2]},278" fill="none" stroke="#22303e" stroke-width="0.8"/>')
        err = row.get("error")
        nodes[mid] = {"t": lab, "plug": plug,
                      "sub": f"P3 · candidate ({'JSON hot-swap' if plug=='hot' and mid!='guidance' else 'guidance' if mid=='guidance' else 'code'})",
                      "body": (f"paired MAE: {err:.4f}<br>ensemble weight: {w:.2f}<br>"
                               f"eligible (beat seasonal-naive): {'yes' if elig else 'no'}<br>"
                               f"next-period prediction: {row.get('final_pred')}" if row else "not scored"),
                      "spec": (mnode[mid].spec if mid in mnode and mnode[mid].spec else None),
                      "producer": (mnode[mid].producer if mid in mnode else None)}

    # P4 backtest + ensemble
    bt_x, bt_w = 300, 230
    parts.append(_rect(bt_x, 414, bt_w, 44, "backtest", "#1b222c", "#3a4658",
                       ["Causal prequential backtest", "paired gate vs seasonal-naive · PIT"]))
    en_x, en_w = 600, 170
    parts.append(_rect(en_x, 414, en_w, 44, "ensemble", "#1b222c", "#3a4658",
                       ["Capped ensemble", "prior-origin inverse-MAE weights"]))
    btc = (cx(bt_x, bt_w), 414); bto = (cx(bt_x, bt_w), 458)
    enc = (cx(en_x, en_w), 414); eno = (cx(en_x, en_w), 458)
    nodes["backtest"] = {"t": "Causal prequential backtest · paired gate", "plug": "no", "sub": "P4 · FIXED methodology",
                         "body": "At each origin, predict from information available then. Weights use only "
                                 "earlier completed origins; candidates must beat seasonal-naive on paired rows."}
    nodes["ensemble"] = {"t": "Capped causal ensemble", "plug": "no", "sub": "P4 · FIXED",
                         "body": "Six-origin baseline-only warm-up; qualifying candidates use inverse paired "
                                 "MAE, capped at 0.60, with a 0.20 seasonal-naive floor."}
    # weighted edges model -> backtest
    for mid, (mxb, myb, _, _) in p3c.items():
        row = lb.get(mid, {})
        w = row.get("weight", 0.0)
        col = "#f0b768" if row.get("eligible") else "#2b3745"
        sw = 0.6 + w * 7
        parts.append(f'<path d="M{mxb},{myb} C{mxb},390 {btc[0]},390 {btc[0]},{btc[1]}" fill="none" stroke="{col}" stroke-width="{sw:.1f}" opacity="0.75"/>')
    parts.append(f'<path d="M{bto[0]},{bto[1]} C{bto[0]},485 {enc[0]},485 {enc[0]},{enc[1]}" fill="none" stroke="#4a5a6e" stroke-width="2.4"/>')

    # P5 govern + emit
    gd_x, gd_w = 320, 170
    parts.append(_rect(gd_x, 532, gd_w, 40, "guardrail", "#16241b", "#2f6b43", ["Diagnostic MAE band", "point ± causal MAE"]))
    wb_x, wb_w = 560, 170
    parts.append(_rect(wb_x, 532, wb_w, 40, "emit", "#16241b", "#2f6b43", ["Workbook (xlsx)", "Summary sheet"]))
    gdc = (cx(gd_x, gd_w), 532)
    parts.append(f'<path d="M{eno[0]},{eno[1]} C{eno[0]},505 {gdc[0]},505 {gdc[0]},532" fill="none" stroke="#3a6b47" stroke-width="2"/>')
    parts.append(f'<path d="M{cx(gd_x,gd_w)},572 C{cx(gd_x,gd_w)},595 {cx(wb_x,wb_w)},595 {cx(wb_x,wb_w)},572" fill="none" stroke="#3a6b47" stroke-width="1.6" stroke-dasharray="0"/>')
    parts.append(f'<line x1="{gd_x+gd_w}" y1="552" x2="{wb_x}" y2="552" stroke="#3a6b47" stroke-width="2"/>')
    nodes["guardrail"] = {"t": "Diagnostic MAE band", "plug": "no", "sub": "P5 · FIXED",
                          "body": f"Point {_fmt(mf.point, mf.kind) if mf and mf.point is not None else '—'} "
                                  f"± realized causal ensemble MAE. This is diagnostic, not a calibrated interval."}
    nodes["emit"] = {"t": "Workbook writer", "plug": "no", "sub": "P5 · FIXED",
                     "body": f"Writes submission/{fc['output_file']} — fills the Summary sheet, leaves structure intact."}
    parts.append("</svg>")
    return "".join(parts), nodes


@app.get("/graph")
def graph():
    from flask import request
    ticker = (request.args.get("t") or "ADI").upper()
    if ticker not in METRIC_MAP:
        ticker = "ADI"
    fc = forecast_company(ticker)
    labels = [m.label for m in fc["metrics"]]
    sel = request.args.get("m") or labels[0]
    mf = next((m for m in fc["metrics"] if m.label == sel), fc["metrics"][0])
    svg, nodes = _graph_svg(fc, mf)

    tsel = "".join(f"<a class=phase href='/graph?t={t}'>{t}</a>" for t in TICKERS if t in METRIC_MAP)
    msel = "".join(f"<a class=phase href='/graph?t={ticker}&m={html.escape(l)}' "
                   f"style=\"{'background:#22303e;color:#e6e9ef' if l==sel else ''}\">{html.escape(l)}</a>"
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
            f"causal paired backtest gate → prior-origin weights → ensemble → workbook. "
            f"Fixed methodology vs hot-swappable research layer.</div>"
            f"<div>Company: {tsel}</div><div style='margin-top:6px'>Metric: {msel}</div>"
            f"{legend}<div class=card style='padding:10px'>{svg}</div>{form}"
            f"<a href='/'>← overview</a> · <a href='/c/{ticker}'>metric detail →</a>{js}")
    return Response(_page("Graph", body), mimetype="text/html")


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
