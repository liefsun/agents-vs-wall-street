"""LLM driver — qualitative signals from calls/slides (Methodology 1 §6).

The LLM reads the latest call transcript / slides and codes qualitative business
signals on a −2..+2 scale (demand, pricing, inventory, management confidence, guidance
direction) with a one-line reason each. It NEVER sets a numeric forecast — signals are
informational (they would feed the deferred regime/scenario layer). Returns None when
no OpenAI key is set, so the numeric pipeline is unaffected.
"""
from __future__ import annotations

import json

from . import corpus
from .llm import LLM

DIMS = ["demand", "pricing", "inventory", "management_confidence", "guidance_direction"]


def _latest_call(ticker: str):
    docs = corpus.load_docs(ticker, kinds=("call-transcripts", "slides"))
    return docs[-1] if docs else None


def qualitative_signals(ticker: str, llm: LLM | None = None) -> dict | None:
    llm = llm or LLM()
    if not llm.available:
        return None
    d = _latest_call(ticker)
    if not d:
        return None
    body = d.body()[:6000]
    system = ("You read an earnings-call / slides excerpt and extract qualitative BUSINESS "
              "signals only. You must NOT produce any financial forecast or number. JSON only.")
    user = (f"Company {ticker}. Rate each dimension on an integer −2..+2 "
            f"(−2 materially deteriorating, 0 stable/mixed, +2 materially improving): "
            f"{', '.join(DIMS)}. Give a one-line reason for each. "
            f'Reply exactly {{"signals":[{{"dim":"","score":0,"reason":""}}],"summary":"<=20 words"}}.\n\n'
            f"TEXT:\n{body}")
    raw = llm.complete_json(system, user, max_tokens=600)
    if not raw:
        return None
    try:
        o = json.loads(raw)
        return {"ticker": ticker, "doc": d.name,
                "signals": o.get("signals", []), "summary": o.get("summary", "")}
    except Exception:
        return None
