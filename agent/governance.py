"""Governance layer — phases, plug types, and a hot-swappable model-node registry.

Mirrors the lab's design (pipeline/phases.py + node_resolver): the pipeline is a
layered graph. Some layers are FIXED methodology (change via code only); one layer
— the candidate forecasters — is HOT-SWAPPABLE so we can do research fast: drop a
JSON node into agent/nodes/models/ and it becomes a new competitor in the
rolling-origin backtest, no code change.

Neural-network framing (what the /graph view draws):
    corpus sources ─▶ extractors ─▶ period panel (features)
                                        │
                    ┌───────────────────┼───────────────────┐   ← candidate layer
                 model₁  model₂  …  modelₙ  guidance             (parallel nodes)
                    └───────────────────┼───────────────────┘
                          rolling-origin backtest (gate: beat seasonal-naive)
                                        │  inverse-error weights (learned)
                                  capped ensemble  ─▶  point + band  ─▶  workbook

Plug types (governance):
    hot  — pure JSON, loaded from disk on read; safe to add/edit during research
    code — JSON declaration bound to a code producer / registry (needs a code edit)
    no   — fixed; methodology or governance, change via code only
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from . import candidates
from .corpus import ROOT

NODES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes", "models")

# ── the 5 layers: single source of truth for the graph + governance ──
# Input = (company code, required output).  Ingestion → Methodology → Model →
# Backtesting → Output.  Methodology is its own FIXED layer: it decides HOW the
# method runs; the Model layer plugs in (hot-swap); Backtesting executes.
PHASES = [
    {"id": "P1", "title": "Data ingestion", "plug": "code",
     "note": "frozen corpus → extract → period panel (actuals + issued guidance)"},
    {"id": "P2", "title": "Methodology", "plug": "no",
     "note": "loss · gate · point-in-time · backtest window · ensemble · guardrail — decides HOW the method runs"},
    {"id": "P3", "title": "Model", "plug": "hot",
     "note": "parallel forecaster nodes compete — hot-swap JSON or code producers"},
    {"id": "P4", "title": "Backtesting", "plug": "no",
     "note": "rolling-origin executes the methodology → gate + learned ensemble weights + point + band"},
    {"id": "P5", "title": "Output", "plug": "no",
     "note": "emit the required workbooks (Summary sheet); one command, all four companies"},
]
PHASE_PLUG = {p["id"]: p["plug"] for p in PHASES}


# ── code producers: the built-in candidate functions (series -> next point) ──
CODE_PRODUCERS = {
    "seasonal_naive": candidates.seasonal_naive,
    "naive_last": candidates.naive_last,
    "drift_mult": candidates.drift_mult,
    "drift_add": candidates.drift_add,
    "trend_mult": candidates.trend_mult,
    "ar_lag": candidates.ar_lag,
    "ets_hw": candidates.ets_hw,
}

# built-in code nodes (declared, but bound to CODE_PRODUCERS)
_BUILTIN = [
    {"id": "seasonal_naive", "label": "Seasonal naive · same qtr last year", "plug": "no",
     "producer": "seasonal_naive", "note": "mandatory baseline every model must beat"},
    {"id": "naive_last", "label": "Naive · last quarter", "plug": "code", "producer": "naive_last"},
    {"id": "drift_mult", "label": "Seasonal drift · median YoY growth", "plug": "code", "producer": "drift_mult"},
    {"id": "drift_add", "label": "Seasonal drift · median YoY change", "plug": "code", "producer": "drift_add"},
    {"id": "trend_mult", "label": "Seasonal + growth trend", "plug": "code", "producer": "trend_mult"},
    {"id": "ar_lag", "label": "Lagged OLS / AR", "plug": "code", "producer": "ar_lag"},
    {"id": "ets_hw", "label": "ETS / Holt-Winters", "plug": "code", "producer": "ets_hw"},
]

BASELINE = "seasonal_naive"


# ── JSON spec interpreter: pure-config models (the hot-swap research lever) ──
def _interp(spec: dict, y: list[float]):
    """Run a declarative model spec on series y -> next point (or None)."""
    t = spec.get("type")
    if t == "seasonal_lag":
        lag = int(spec.get("lag", 4))
        return float(y[-lag]) if len(y) >= lag else None
    if t == "linear_lags":
        lags = spec.get("lags", {"1": 1.0})
        b = float(spec.get("intercept", 0.0))
        acc, ok = b, True
        for k, w in lags.items():
            k = int(k)
            if len(y) < k:
                ok = False
                break
            acc += float(w) * y[-k]
        return float(acc) if ok else None
    if t == "drift":
        lag = int(spec.get("lag", 4))
        look = int(spec.get("lookback", 8))
        mode = spec.get("mode", "mult")
        if len(y) < lag * 2:
            return None
        if mode == "mult":
            g = [y[i] / y[i - lag] for i in range(lag, len(y)) if y[i - lag] > 0][-look:]
            return y[-lag] * float(np.median(g)) if g else None
        d = [y[i] - y[i - lag] for i in range(lag, len(y))][-look:]
        return y[-lag] + float(np.median(d)) if d else None
    if t == "ewma":
        alpha = float(spec.get("alpha", 0.5))
        if not y:
            return None
        s = y[0]
        for v in y[1:]:
            s = alpha * v + (1 - alpha) * s
        return float(s)
    return None


@dataclass
class ModelNode:
    id: str
    label: str
    phase: str = "P3"
    plug: str = "code"
    kind: str = "candidate"
    producer: str | None = None          # code path
    spec: dict | None = None             # json path
    applies_to: list[str] = field(default_factory=lambda: ["money", "eps", "pct"])
    enabled: bool = True
    note: str = ""
    source: str = "code"                 # code | json

    def predict(self, y: list[float]):
        if self.producer:
            fn = CODE_PRODUCERS.get(self.producer)
            return fn(y) if fn else None
        if self.spec:
            return _interp(self.spec, y)
        return None

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "phase": self.phase, "plug": self.plug,
                "kind": self.kind, "producer": self.producer, "spec": self.spec,
                "applies_to": self.applies_to, "enabled": self.enabled, "note": self.note,
                "source": self.source}


def load_models() -> list[ModelNode]:
    """Built-in code nodes + hot-swap JSON nodes from agent/nodes/models/*.json."""
    out = [ModelNode(id=d["id"], label=d["label"], plug=d.get("plug", "code"),
                     producer=d.get("producer"), note=d.get("note", ""), source="code")
           for d in _BUILTIN]
    if os.path.isdir(NODES_DIR):
        for fn in sorted(os.listdir(NODES_DIR)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(NODES_DIR, fn), "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                out.append(ModelNode(
                    id=d["id"], label=d.get("label", d["id"]), plug=d.get("plug", "hot"),
                    producer=d.get("producer"), spec=d.get("spec"),
                    applies_to=d.get("applies_to", ["money", "eps", "pct"]),
                    enabled=d.get("enabled", True), note=d.get("note", ""), source="json"))
            except Exception as exc:
                out.append(ModelNode(id=f"BROKEN:{fn}", label=f"invalid JSON node ({exc})",
                                     plug="hot", enabled=False, source="json"))
    return out


def active_models(kind: str) -> list[ModelNode]:
    return [m for m in load_models() if m.enabled and (not m.applies_to or kind in m.applies_to)]


# ── node validation (agent judges a node BEFORE it goes live; no data fetch) ──
_SAMPLE = [float(v) for v in range(100, 100 + 24)]     # smooth ramp, 24 quarters


def validate_node(node: dict) -> dict:
    """Schema + runnability check for a candidate model node. 4-state verdict like the lab."""
    msgs, warns = [], []
    schema_ok = isinstance(node, dict) and bool(node.get("id"))
    if not schema_ok:
        return {"verdict": "invalid", "schema_ok": False,
                "messages": ["node needs an 'id'"], "warnings": []}
    has_producer = node.get("producer") in CODE_PRODUCERS
    has_spec = isinstance(node.get("spec"), dict)
    if not (has_producer or has_spec):
        msgs.append("node has neither a known 'producer' nor a 'spec'")
        return {"verdict": "invalid", "schema_ok": True, "messages": msgs, "warnings": warns}
    if node.get("producer") and not has_producer:
        return {"verdict": "invalid", "schema_ok": True,
                "messages": [f"unknown producer '{node.get('producer')}'"], "warnings": warns}
    # runnability: does it produce a finite number on a sample ramp?
    try:
        m = ModelNode(id=node["id"], label=node.get("label", node["id"]),
                      producer=node.get("producer"), spec=node.get("spec"))
        p = m.predict(_SAMPLE)
    except Exception as exc:
        return {"verdict": "invalid", "schema_ok": True,
                "messages": [f"raised {type(exc).__name__}: {exc}"], "warnings": warns}
    if p is None:
        warns.append("returned None on the sample ramp (may need a longer series to fire)")
        return {"verdict": "declarable", "schema_ok": True, "sample_pred": None,
                "messages": ["schema OK; runs but did not fire on 24-pt sample"], "warnings": warns}
    if not np.isfinite(p):
        return {"verdict": "invalid", "schema_ok": True,
                "messages": ["produced a non-finite value"], "warnings": warns}
    plug = node.get("plug", "hot")
    return {"verdict": "publishable", "schema_ok": True, "sample_pred": float(p),
            "plug": plug, "messages": [f"OK — sample prediction {p:.2f}"], "warnings": warns}
