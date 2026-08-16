"""Research agent — the LLM does the analyst's reading, not a regex.

For each target metric the agent works the way a human analyst does:

    1. retrieve   candidate documents for (company, metric) from the frozen corpus
    2. read       focused excerpts around the metric's own language
    3. extract    the value THIS document reports for ITS OWN period, with a verbatim
                  quote, the units it was stated in, and the agent's confidence
    4. defend     every extraction must survive a validation gate before it is admitted

The agent extracts *reported historical facts*, never a forecast. That boundary is what
makes it auditable: each admitted number carries the sentence it came from, and that
sentence must appear verbatim in the source document or the observation is rejected.

Determinism: every completion is temperature-0 and disk-cached under `agent/cache/research/`.
Once the cache is warm the final run performs no network calls at all, so the clear run is
reproducible offline and byte-stable.

If no OpenAI key is configured the agent is simply unavailable and callers fall back to the
deterministic parsers in `history.py` — the pipeline never silently loses a stage.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

from .corpus import Doc, earnings_releases
from .llm import LLM

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "research")

# Maximum characters of document text shown to the agent per document. Filings in this
# corpus run to thousands of lines and repeat their figures in later statement tables;
# excerpting around the metric's own language keeps the read focused on the headline.
MAX_EXCERPT_CHARS = 6000
WINDOW = 700
MAX_WINDOWS = 8


@dataclass(frozen=True, slots=True)
class MetricBrief:
    """What the analyst is asked to find, and what counts as a plausible answer."""

    ticker: str
    label: str
    kind: str                      # money | eps | pct
    units: str
    instruction: str               # the analyst brief: exact basis, what NOT to accept
    terms: tuple[str, ...]         # retrieval + excerpting anchors
    low: float                     # plausibility gate (order-of-magnitude sanity only)
    high: float


@dataclass(frozen=True, slots=True)
class Extraction:
    """One admitted or rejected reading of one document."""

    ticker: str
    label: str
    doc_name: str
    published_at: str
    doc_period: str
    value: float | None
    units_stated: str
    quote: str
    confidence: str
    notes: str
    admitted: bool
    rejection: str | None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "label": self.label, "doc": self.doc_name,
            "published_at": self.published_at, "doc_period": self.doc_period,
            "value": self.value, "units_stated": self.units_stated, "quote": self.quote,
            "confidence": self.confidence, "notes": self.notes,
            "admitted": self.admitted, "rejection": self.rejection,
        }


# ── the analyst briefs: WHAT to find, stated the way you would brief a junior analyst ──
BRIEFS: dict[tuple[str, str], MetricBrief] = {
    ("HD", "Net sales"): MetricBrief(
        "HD", "Net sales", "money", "USDm",
        "Home Depot's consolidated net sales for the quarter this document reports. "
        "Take the quarter's own figure, not the fiscal-year or six-month total, and not "
        "the prior-year comparative. Report in millions of US dollars.",
        ("net sales", "sales for the quarter", "sales increased", "sales of"),
        1_000.0, 100_000.0),
    ("HD", "Adjusted diluted EPS"): MetricBrief(
        "HD", "Adjusted diluted EPS", "eps", "USD / share",
        "Home Depot's ADJUSTED (non-GAAP) diluted earnings per share for the quarter this "
        "document reports. Do NOT substitute GAAP diluted EPS — if only GAAP EPS is stated, "
        "return null. Do not take the prior-year comparative or a full-year figure.",
        ("adjusted diluted earnings per share", "adjusted diluted eps", "diluted earnings per share"),
        0.1, 30.0),
    ("HD", "Comparable sales, total company"): MetricBrief(
        "HD", "Comparable sales, total company", "pct", "%",
        "Home Depot's TOTAL COMPANY comparable sales change for the quarter this document "
        "reports, in percentage points (a 1.4% increase is 1.4; a decline is negative). "
        "Do NOT use U.S. comparable sales or any segment/region figure.",
        ("comparable sales", "comp sales", "comparable sales for the"),
        -30.0, 30.0),
    ("ADI", "Revenue"): MetricBrief(
        "ADI", "Revenue", "money", "USDm",
        "Analog Devices' total revenue for the fiscal quarter this document reports, in "
        "millions of US dollars. Not the six-month or full-year figure, not the prior-year "
        "comparative, and not a segment or end-market revenue.",
        ("revenue", "revenue of", "net revenue"),
        200.0, 20_000.0),
    ("ADI", "Adjusted diluted EPS"): MetricBrief(
        "ADI", "Adjusted diluted EPS", "eps", "USD / share",
        "Analog Devices' ADJUSTED (non-GAAP) diluted earnings per share for the fiscal "
        "quarter this document reports. Do NOT substitute GAAP diluted EPS; return null if "
        "only GAAP is stated.",
        ("adjusted diluted earnings per share", "adjusted eps", "adjusted diluted eps"),
        0.05, 30.0),
    ("ADI", "Adjusted gross margin"): MetricBrief(
        "ADI", "Adjusted gross margin", "pct", "%",
        "Analog Devices' ADJUSTED (non-GAAP) gross margin for the fiscal quarter this "
        "document reports, as a percentage (e.g. 68.9). Not GAAP gross margin, not "
        "operating margin.",
        ("adjusted gross margin", "gross margin"),
        20.0, 95.0),
    ("DE", "Worldwide net sales and revenues"): MetricBrief(
        "DE", "Worldwide net sales and revenues", "money", "USDm",
        "Deere's WORLDWIDE net sales and revenues for the quarter this document reports, in "
        "millions of US dollars. This is the total including financial services — not "
        "equipment operations alone, not a segment, not the year-to-date total.",
        ("worldwide net sales and revenues", "net sales and revenues"),
        1_000.0, 100_000.0),
    ("DE", "Diluted EPS (GAAP)"): MetricBrief(
        "DE", "Diluted EPS (GAAP)", "eps", "USD / share",
        "Deere's GAAP diluted earnings per share for the quarter this document reports. "
        "Take the quarter's own figure, not the year-to-date or full-year figure.",
        ("per share", "diluted", "net income attributable"),
        0.1, 40.0),
    ("DE", "Production & Precision Ag operating profit"): MetricBrief(
        "DE", "Production & Precision Ag operating profit", "money", "USDm",
        "The OPERATING PROFIT of Deere's Production & Precision Agriculture segment for the "
        "quarter this document reports, in millions of US dollars. Not the segment's net "
        "sales, not another segment, not the consolidated total.",
        ("production & precision ag", "production and precision ag", "precision ag"),
        -2_000.0, 10_000.0),
    ("HAS", "Net fees"): MetricBrief(
        "HAS", "Net fees", "money", "GBPm",
        "Hays plc GROUP net fees for the reporting period this document covers (H1 or full "
        "year), in millions of pounds. Take the group headline figure, not a regional or "
        "divisional figure, and not a percentage change.",
        ("net fees", "group net fees"),
        100.0, 3_000.0),
    ("HAS", "Pre-exceptional operating profit"): MetricBrief(
        "HAS", "Pre-exceptional operating profit", "money", "GBPm",
        "Hays plc GROUP operating profit BEFORE exceptional items for the reporting period "
        "this document covers, in millions of pounds. In years without exceptional items the "
        "headline 'operating profit' is the same figure. Not a regional figure.",
        ("operating profit", "pre-exceptional operating profit", "before exceptional"),
        -200.0, 500.0),
    ("HAS", "Pre-exceptional basic EPS"): MetricBrief(
        "HAS", "Pre-exceptional basic EPS", "eps", "GBp",
        "Hays plc BASIC earnings per share BEFORE exceptional items for the reporting period "
        "this document covers, stated in PENCE (e.g. 4.7). Not diluted EPS, not a figure in "
        "pounds, not the dividend per share.",
        ("basic earnings per share", "earnings per share", "basic eps"),
        -20.0, 40.0),
}

_SYSTEM = (
    "You are a meticulous equity research analyst extracting REPORTED HISTORICAL FIGURES "
    "from company filings. You never estimate, never interpolate and never forecast. You "
    "only report a number that is explicitly stated in the text you are shown.\n"
    "Hard rules:\n"
    "1. Report ONLY the figure for the document's own reporting period. Filings restate "
    "prior-year comparatives and year-to-date totals next to the current figure — those are "
    "traps. If you cannot tell which period a number belongs to, return null.\n"
    "2. Copy the sentence or table row you took the number from into `quote`, character for "
    "character, exactly as it appears. Do not paraphrase, reformat or fix typos.\n"
    "3. Respect the requested basis exactly (adjusted vs GAAP, group vs segment, quarter vs "
    "year). If only the wrong basis is present, return null with a reason.\n"
    "4. Convert to the requested units and say in `units_stated` what the source actually "
    "said (e.g. '$ in billions', 'pence', '£m').\n"
    "Return JSON only."
)


def _cache_path(key: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".json")


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def excerpt_for(body: str, brief: MetricBrief) -> str:
    """Windows of text around the metric's own language, in document order.

    Whole filings do not fit in a prompt and burying the headline table under thousands
    of lines of financial statements is exactly how the earlier parsers picked up
    weighted-share counts instead of EPS.
    """
    low = body.lower()
    hits: list[int] = []
    for term in brief.terms:
        start = 0
        while len(hits) < MAX_WINDOWS * 4:
            found = low.find(term.lower(), start)
            if found == -1:
                break
            hits.append(found)
            start = found + len(term)
    if not hits:
        return body[:MAX_EXCERPT_CHARS]

    spans: list[tuple[int, int]] = []
    for hit in sorted(hits):
        lo, hi = max(0, hit - WINDOW // 2), min(len(body), hit + WINDOW)
        if spans and lo <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], hi))
        else:
            spans.append((lo, hi))
        if len(spans) >= MAX_WINDOWS:
            break

    separator = "\n…\n"
    chunks, total = [], 0
    for lo, hi in spans:
        budget = MAX_EXCERPT_CHARS - total - (len(separator) if chunks else 0)
        if budget <= 0:
            break
        piece = body[lo:hi][:budget]
        total += len(piece) + (len(separator) if chunks else 0)
        chunks.append(piece)
    return separator.join(chunks)[:MAX_EXCERPT_CHARS]


def _ask(doc: Doc, brief: MetricBrief, text: str, llm: LLM) -> dict | None:
    user = (
        f"Company: {brief.ticker}\n"
        f"Document: {doc.name}\n"
        f"Document's own reporting period (from its metadata): {doc.period or 'unstated'}\n"
        f"Published: {doc.published_at}\n\n"
        f"TARGET METRIC: {brief.label}\n"
        f"Report it in: {brief.units}\n"
        f"Analyst brief: {brief.instruction}\n\n"
        f"DOCUMENT EXCERPTS:\n{text}\n\n"
        'Reply exactly {"value": <number or null>, "units_stated": "", "period": "", '
        '"quote": "", "confidence": "high|medium|low", "notes": ""}'
    )
    cache_key = f"research-v1\n{llm.model}\n{_SYSTEM}\n{user}"
    path = _cache_path(cache_key)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    raw = llm.complete_json(_SYSTEM, user, max_tokens=500)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(parsed, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return parsed


def read_document(doc: Doc, brief: MetricBrief, llm: LLM) -> Extraction:
    """Run the agent on one document and put its answer through the validation gate."""
    body = doc.body()
    text = excerpt_for(body, brief)
    answer = _ask(doc, brief, text, llm)

    def reject(reason: str, value: float | None = None, quote: str = "", **kw) -> Extraction:
        return Extraction(
            ticker=brief.ticker, label=brief.label, doc_name=doc.name,
            published_at=doc.published_at, doc_period=doc.period, value=value,
            units_stated=kw.get("units_stated", ""), quote=quote,
            confidence=kw.get("confidence", ""), notes=kw.get("notes", ""),
            admitted=False, rejection=reason)

    if answer is None:
        return reject("agent returned no parsable answer")

    raw_value = answer.get("value")
    quote = str(answer.get("quote") or "")
    units_stated = str(answer.get("units_stated") or "")
    confidence = str(answer.get("confidence") or "")
    notes = str(answer.get("notes") or "")

    if raw_value is None:
        return reject("agent found no figure on the requested basis",
                      quote=quote, units_stated=units_stated, confidence=confidence, notes=notes)
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return reject(f"value {raw_value!r} is not numeric", quote=quote, notes=notes)

    # ── the anti-hallucination gate: the quote must really be in the document ──
    if not quote.strip():
        return reject("no supporting quote", value, quote, notes=notes)
    if _norm_ws(quote) not in _norm_ws(body):
        return reject("quote does not appear verbatim in the source document",
                      value, quote, units_stated=units_stated, confidence=confidence, notes=notes)

    if not (brief.low <= value <= brief.high):
        return reject(f"value {value} outside plausible range [{brief.low}, {brief.high}]",
                      value, quote, units_stated=units_stated, confidence=confidence, notes=notes)

    if confidence.lower() == "low":
        return reject("agent reported low confidence", value, quote,
                      units_stated=units_stated, confidence=confidence, notes=notes)

    return Extraction(
        ticker=brief.ticker, label=brief.label, doc_name=doc.name,
        published_at=doc.published_at, doc_period=doc.period, value=value,
        units_stated=units_stated, quote=quote.strip()[:240], confidence=confidence,
        notes=notes, admitted=True, rejection=None)


def candidate_documents(brief: MetricBrief) -> list[Doc]:
    """Earnings releases that actually mention the metric, oldest first."""
    docs = earnings_releases(brief.ticker)
    keep = []
    for doc in docs:
        low = doc.body().lower()
        if any(term.lower() in low for term in brief.terms):
            keep.append(doc)
    return keep


def research(ticker: str, label: str, llm: LLM | None = None) -> list[Extraction]:
    """Run the research agent over every candidate document for one metric."""
    brief = BRIEFS.get((ticker, label))
    if brief is None:
        return []
    llm = llm or LLM()
    if not llm.available:
        return []
    return [read_document(doc, brief, llm) for doc in candidate_documents(brief)]


def available() -> bool:
    return LLM().available
