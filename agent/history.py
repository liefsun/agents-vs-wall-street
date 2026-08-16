"""Point-in-time historical series built from the frozen challenge corpus.

Every admitted value is tied to the document that first reported the target
period.  Parsers are deliberately metric-specific: rejecting an ambiguous row is
safer than manufacturing backtest coverage from a nearby but different number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from . import corpus, extract
from .corpus import Doc


class Frequency(Enum):
    """Supported reporting frequencies and their seasonal lag."""

    QUARTERLY = ("quarterly", 4)
    SEMIANNUAL = ("semiannual", 2)

    def __init__(self, label: str, season: int) -> None:
        self.label = label
        self.season = season


@dataclass(frozen=True, slots=True)
class HistoricalObservation:
    key: int
    period: str
    value: float
    published_at: str
    source: str
    snippet: str


@dataclass(frozen=True, slots=True)
class HistoricalSeries:
    ticker: str
    label: str
    kind: str
    units: str
    frequency: Frequency
    observations: tuple[HistoricalObservation, ...]

    def __post_init__(self) -> None:
        keys = tuple(item.key for item in self.observations)
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("historical observations must have unique increasing keys")

    @property
    def season(self) -> int:
        return self.frequency.season

    def axis_values(self) -> tuple[list[int], list[float | None]]:
        if not self.observations:
            return [], []
        values = {item.key: item.value for item in self.observations}
        axis = list(range(self.observations[0].key, self.observations[-1].key + 1))
        return axis, [values.get(key) for key in axis]


@dataclass(frozen=True, slots=True)
class _Candidate:
    key: int
    period: str
    value: float
    published_at: str
    source: str
    snippet: str
    quality: int


_QUARTER_WITH_YEAR = re.compile(
    r"\bQ([1-4])\b(?:(?!\b\d{4}\b).){0,24}\b(\d{4})\b",
    re.IGNORECASE,
)
_HALF_WITH_YEAR = re.compile(r"\bH1\s*(?:FY\s*)?(\d{4})\b", re.IGNORECASE)
_FISCAL_YEAR = re.compile(r"\bFY\s*(\d{4})\b", re.IGNORECASE)


def quarterly_period_key(period: str) -> int | None:
    """Normalize Q1-Q4/FY metadata; reject half-year-only periods."""

    quarter = _QUARTER_WITH_YEAR.search(period or "")
    if quarter:
        q, year = int(quarter.group(1)), int(quarter.group(2))
        return year * 4 + q - 1
    if re.search(r"\bH[12]\b", period or "", re.IGNORECASE):
        return None
    fiscal_year = _FISCAL_YEAR.search(period or "")
    if fiscal_year:
        return int(fiscal_year.group(1)) * 4 + 3
    return None


def quarterly_doc_key(doc: Doc) -> int | None:
    """Resolve explicit Q/FY metadata, with a narrow qN-filename fallback."""

    key = quarterly_period_key(doc.period)
    if key is not None:
        return key
    filename_quarter = re.search(r"-q([1-4])-", doc.name, re.IGNORECASE)
    period_year = re.search(r"\b(\d{4})\b", doc.period or "")
    if filename_quarter and period_year:
        quarter = int(filename_quarter.group(1))
        year = int(period_year.group(1))
        return year * 4 + quarter - 1
    return None


def semiannual_period_key(period: str) -> int | None:
    """Normalize Hays H1/FY events onto an H1, FY alternating axis."""

    half = _HALF_WITH_YEAR.search(period or "")
    if half:
        return int(half.group(1)) * 2
    fiscal_year = _FISCAL_YEAR.search(period or "")
    if fiscal_year:
        return int(fiscal_year.group(1)) * 2 + 1
    return None


def _number(raw: str) -> float:
    token = raw.strip().replace(",", "").replace("$", "").replace("£", "")
    token = token.rstrip("mMpP ")
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    value = float(token)
    return -value if negative else value


def _first_number(text: str) -> tuple[float, str] | None:
    match = re.search(r"(?<![\w.])(?:[$£]\s*)?(\(?\d[\d,]*(?:\.\d+)?\)?)(?:\s*[mMpP])?", text)
    if not match:
        return None
    return _number(match.group(1)), match.group(0)


def _choose_first_report(candidates: list[_Candidate]) -> tuple[HistoricalObservation, ...]:
    by_key: dict[int, list[_Candidate]] = {}
    for candidate in candidates:
        by_key.setdefault(candidate.key, []).append(candidate)

    observations = []
    for key in sorted(by_key):
        rows = by_key[key]
        first_date = min(row.published_at for row in rows)
        same_day = [row for row in rows if row.published_at == first_date]
        chosen = max(same_day, key=lambda row: (row.quality, -len(row.source)))
        observations.append(
            HistoricalObservation(
                key=chosen.key,
                period=chosen.period,
                value=chosen.value,
                published_at=chosen.published_at,
                source=chosen.source,
                snippet=chosen.snippet,
            )
        )
    return tuple(observations)


def _candidate(
    doc: Doc,
    key: int,
    value: float,
    snippet: str,
    quality: int = 0,
) -> _Candidate:
    return _Candidate(
        key=key,
        period=doc.period,
        value=float(value),
        published_at=doc.published_at,
        source=doc.name,
        snippet=snippet.strip()[:240],
        quality=quality,
    )


def _adi_history(label: str, metric: str, kind: str, units: str) -> HistoricalSeries:
    observations = []
    for row in extract.build_panel("ADI"):
        value = row.actuals.get(metric)
        if value is None:
            continue
        observations.append(
            HistoricalObservation(
                key=row.key,
                period=row.period,
                value=float(value),
                published_at=row.published_at,
                source=row.doc,
                snippet=row.evidence.get(f"actual.{metric}", ""),
            )
        )
    return HistoricalSeries(
        ticker="ADI",
        label=label,
        kind=kind,
        units=units,
        frequency=Frequency.QUARTERLY,
        observations=tuple(observations),
    )


def _hd_match(doc: Doc, metric: str) -> _Candidate | None:
    key = quarterly_doc_key(doc)
    if key is None:
        return None
    body = doc.body()
    if metric == "net_sales":
        match = re.search(
            r"Sales for the (?:first|second|third|fourth) quarter[^.]{0,80}?were\s*\$\s*([\d.]+)\s*(billion|million)",
            body,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"reported sales of\s*\$\s*([\d.]+)\s*(billion|million)",
                body,
                re.IGNORECASE,
            )
        if not match:
            return None
        value = _number(match.group(1)) * (1000.0 if match.group(2).lower().startswith("b") else 1.0)
    elif metric == "comp":
        match = re.search(
            r"Comparable sales for the [^.]*?(increased|decreased)\s*([\d.]+)\s*%",
            body,
            re.IGNORECASE,
        )
        if not match:
            return None
        value = _number(match.group(2)) * (-1.0 if match.group(1).lower() == "decreased" else 1.0)
    else:
        match = re.search(
            r"Adjusted diluted earnings per share for the (?:first|second|third|fourth) quarter[^.$\n]*?(?:were|was|of)\s*\$\s*([\d.]+)",
            body,
            re.IGNORECASE,
        )
        if not match:
            return None
        value = _number(match.group(1))
    return _candidate(doc, key, value, match.group(0), quality=100)


def _hd_history(label: str, metric: str, kind: str, units: str) -> HistoricalSeries:
    candidates = [
        candidate
        for doc in corpus.earnings_releases("HD")
        if (candidate := _hd_match(doc, metric)) is not None
    ]
    return HistoricalSeries(
        ticker="HD",
        label=label,
        kind=kind,
        units=units,
        frequency=Frequency.QUARTERLY,
        observations=_choose_first_report(candidates),
    )


def _de_match(doc: Doc, metric: str) -> _Candidate | None:
    key = quarterly_doc_key(doc)
    if key is None:
        return None
    body = doc.body()
    if metric == "net_sales_rev":
        match = re.search(
            r"Worldwide net sales and revenues[^.]{0,90}?to\s*\$\s*([\d.,]+)\s*billion",
            body,
            re.IGNORECASE,
        )
        if not match:
            return None
        value = _number(match.group(1)) * 1000.0
    elif metric == "eps_gaap":
        match = re.search(
            r"for the (?:first|second|third|fourth) quarter[^.]{0,100}?or\s*\$\s*([\d.]+)\s*per share",
            body,
            re.IGNORECASE,
        )
        if not match:
            return None
        value = _number(match.group(1))
        if not 0.0 <= value < 40.0:
            return None
    else:
        match = None
        for heading in re.finditer(
            r"Production\s*(?:&|and|&amp;)\s*Precision Ag(?:riculture)?",
            body,
            re.IGNORECASE,
        ):
            window = body[heading.start() : heading.start() + 800]
            if not re.search(
                r"\b(?:First|Second|Third|Fourth) Quarter\b",
                window,
                re.IGNORECASE,
            ):
                continue
            for line in window.splitlines():
                operating_profit = re.match(
                    r"^\s*\|?\s*Operating profit\b(?P<values>.*)$",
                    line,
                    re.IGNORECASE,
                )
                if not operating_profit:
                    continue
                number = _first_number(operating_profit.group("values"))
                if number is None:
                    continue
                match = operating_profit
                value = number[0]
                break
            if match:
                break
        if not match:
            return None
    return _candidate(doc, key, value, match.group(0), quality=100)


def _de_history(label: str, metric: str, kind: str, units: str) -> HistoricalSeries:
    candidates = [
        candidate
        for doc in corpus.earnings_releases("DE")
        if (candidate := _de_match(doc, metric)) is not None
    ]
    return HistoricalSeries(
        ticker="DE",
        label=label,
        kind=kind,
        units=units,
        frequency=Frequency.QUARTERLY,
        observations=_choose_first_report(candidates),
    )


_HAYS_SPECS = {
    "net_fees": {
        "aliases": ("net fees",),
        "bounds": (100.0, 3000.0),
    },
    "pre_exceptional_op": {
        "aliases": (
            "operating profit (before exceptional items)",
            "pre-exceptional operating profit",
            "operating profit from continuing operations",
            "operating profit",
        ),
        "bounds": (-100.0, 500.0),
    },
    "pre_exceptional_eps": {
        "aliases": (
            "basic earnings per share (before exceptional items)",
            "pre-exceptional basic earnings per share",
            "basic earnings per share",
        ),
        "bounds": (-20.0, 30.0),
    },
}


def _normalise_hays_label(cell: str) -> str:
    label = re.sub(r"\{?\(\d+\)\}?", "", cell)
    label = re.sub(r"\s+", " ", label.replace("‡", "")).strip().lower()
    return label.rstrip(":")


def _hays_doc_candidate(doc: Doc, metric: str) -> _Candidate | None:
    key = semiannual_period_key(doc.period)
    if key is None:
        return None
    spec = _HAYS_SPECS[metric]
    matches: list[tuple[int, _Candidate]] = []
    for line_number, line in enumerate(doc.body().splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = _normalise_hays_label(cells[0])
        try:
            alias_index = spec["aliases"].index(label)
        except ValueError:
            continue
        numeric_cells = [number for cell in cells[1:] if (number := _first_number(cell))]
        if not numeric_cells:
            continue
        value = numeric_cells[0][0]
        if (
            len(numeric_cells) > 1
            and value.is_integer()
            and 0.0 <= value <= 10.0
        ):
            value = numeric_cells[1][0]
        lower, upper = spec["bounds"]
        if not lower <= value <= upper:
            continue
        explicit = alias_index < len(spec["aliases"]) - 1
        quality = (200 if explicit else 100) + max(0, 200 - min(line_number, 200))
        if "-8k-2__" not in doc.name:
            quality += 40
        matches.append((alias_index, _candidate(doc, key, value, line, quality=quality)))
    if not matches:
        return None
    best_alias = min(alias_index for alias_index, _ in matches)
    preferred = [row for alias_index, row in matches if alias_index == best_alias]
    return max(preferred, key=lambda row: (row.value, row.quality))


def _hays_history(label: str, metric: str, kind: str, units: str) -> HistoricalSeries:
    candidates = [
        candidate
        for doc in corpus.load_docs("HAS", kinds=("filings",))
        if (candidate := _hays_doc_candidate(doc, metric)) is not None
    ]
    return HistoricalSeries(
        ticker="HAS",
        label=label,
        kind=kind,
        units=units,
        frequency=Frequency.SEMIANNUAL,
        observations=_choose_first_report(candidates),
    )


_SERIES_BUILDERS = {
    ("ADI", "Revenue"): lambda: _adi_history("Revenue", "revenue", "money", "USDm"),
    ("ADI", "Adjusted gross margin"): lambda: _adi_history(
        "Adjusted gross margin", "adj_gross_margin", "pct", "%"
    ),
    ("ADI", "Adjusted diluted EPS"): lambda: _adi_history(
        "Adjusted diluted EPS", "adj_eps", "eps", "USD / share"
    ),
    ("HD", "Net sales"): lambda: _hd_history("Net sales", "net_sales", "money", "USDm"),
    ("HD", "Comparable sales, total company"): lambda: _hd_history(
        "Comparable sales, total company", "comp", "pct", "%"
    ),
    ("HD", "Adjusted diluted EPS"): lambda: _hd_history(
        "Adjusted diluted EPS", "adj_eps", "eps", "USD / share"
    ),
    ("DE", "Worldwide net sales and revenues"): lambda: _de_history(
        "Worldwide net sales and revenues", "net_sales_rev", "money", "USDm"
    ),
    ("DE", "Diluted EPS (GAAP)"): lambda: _de_history(
        "Diluted EPS (GAAP)", "eps_gaap", "eps", "USD / share"
    ),
    ("DE", "Production & Precision Ag operating profit"): lambda: _de_history(
        "Production & Precision Ag operating profit", "ppa_op", "money", "USDm"
    ),
    ("HAS", "Net fees"): lambda: _hays_history("Net fees", "net_fees", "money", "GBPm"),
    ("HAS", "Pre-exceptional operating profit"): lambda: _hays_history(
        "Pre-exceptional operating profit", "pre_exceptional_op", "money", "GBPm"
    ),
    ("HAS", "Pre-exceptional basic EPS"): lambda: _hays_history(
        "Pre-exceptional basic EPS", "pre_exceptional_eps", "eps", "GBp"
    ),
}


_SEMIANNUAL_TICKERS = frozenset({"HAS"})

# A researched and a parsed observation for the same period should agree closely. A wide
# gap means one of them is reading a different row. On disagreement the AGENT value wins
# (it carries a verbatim quote checked to contain the number; the parser is an unverified
# pattern match), and the gap is recorded in the returned disagreements list for audit —
# see cross_check(). The parser only fills periods the agent never returned.
CROSS_CHECK_TOLERANCE = 0.02


def _frequency_for(ticker: str) -> Frequency:
    return Frequency.SEMIANNUAL if ticker in _SEMIANNUAL_TICKERS else Frequency.QUARTERLY


def _researched_candidates(brief, llm) -> tuple[list[_Candidate], list]:
    """Run the research agent over the corpus and keep what survives its gate."""

    from . import research

    frequency = _frequency_for(brief.ticker)
    admitted, attempts = [], []
    for doc in research.candidate_documents(brief):
        result = research.read_document(doc, brief, llm)
        attempts.append(result)
        if not result.admitted or result.value is None:
            continue
        key = (
            semiannual_period_key(doc.period)
            if frequency is Frequency.SEMIANNUAL
            else quarterly_doc_key(doc)
        )
        if key is None:
            continue
        admitted.append(_candidate(doc, key, result.value, result.quote, quality=2))
    return admitted, attempts


def cross_check(
    researched: HistoricalSeries, parsed: HistoricalSeries | None
) -> tuple[HistoricalSeries, list[dict]]:
    """Merge the agent's readings with the parser's, and record where they disagree.

    The agent wins a disagreement. Its value carries a sentence that was checked to exist
    in the source and to contain the number itself; the parser's value is an unverified
    pattern match. Deferring to the parser here would have shipped ADI's Q3 2020 revenue as
    8,200 — a pro-forma figure lifted from a merger announcement — instead of the 1,456
    stated in that quarter's income statement.

    The parser is still useful: it fills periods the agent never returned, so coverage is
    the union of the two rather than whichever one happened to find more.
    """

    if parsed is None:
        return researched, []

    agent_by_key = {item.key: item for item in researched.observations}
    disagreements = []
    for item in parsed.observations:
        other = agent_by_key.get(item.key)
        if other is None:
            agent_by_key[item.key] = item        # parser fills a gap the agent left
            continue
        scale = max(abs(item.value), abs(other.value), 1e-9)
        gap = abs(item.value - other.value) / scale
        if gap > CROSS_CHECK_TOLERANCE:
            disagreements.append({
                "ticker": researched.ticker, "label": researched.label, "period": other.period,
                "agent_value": other.value, "parser_value": item.value,
                "relative_gap": gap, "agent_source": other.source, "agent_quote": other.snippet,
                "resolution": "kept the agent's value — it is corroborated by a quote",
            })

    merged = tuple(agent_by_key[key] for key in sorted(agent_by_key))
    return (
        HistoricalSeries(
            ticker=researched.ticker, label=researched.label, kind=researched.kind,
            units=researched.units, frequency=researched.frequency,
            observations=merged,
        ),
        disagreements,
    )


def researched_series_for(
    ticker: str, label: str, llm=None
) -> tuple[HistoricalSeries | None, list]:
    """Build one history using the research agent. Returns (series, per-document attempts)."""

    from . import research

    brief = research.BRIEFS.get((ticker, label))
    if brief is None:
        return None, []
    llm = llm or research.LLM()
    # A live key is not required: committed answers replay offline, which is what lets a
    # reviewer reproduce the submitted numbers without credentials.
    if not (llm.available or research.has_cached_answers()):
        return None, []
    candidates, attempts = _researched_candidates(brief, llm)
    if not candidates:
        return None, attempts
    return (
        HistoricalSeries(
            ticker=ticker, label=label, kind=brief.kind, units=brief.units,
            frequency=_frequency_for(ticker),
            observations=_choose_first_report(candidates),
        ),
        attempts,
    )


def series_for(ticker: str, label: str) -> HistoricalSeries | None:
    """Return one audited history, or ``None`` for an unknown target metric.

    The research agent is the primary reader: its observations carry the sentence they came
    from, checked to exist in the source and to contain the reported number. The parser
    fills periods the agent did not return, and is the whole series when the agent is
    unavailable. Coverage is therefore the union of the two, and a disagreement is resolved
    in favour of the reading that can show its evidence.
    """

    builder = _SERIES_BUILDERS.get((ticker, label))
    parsed = builder() if builder else None

    researched, _ = researched_series_for(ticker, label)
    if researched is None:
        return parsed

    merged, _disagreements = cross_check(researched, parsed)
    return merged
