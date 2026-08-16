"""The research agent's validation gate must reject before its passes mean anything.

These tests do not call OpenAI. They drive `read_document` with a stubbed driver so that
every rejection path is exercised deterministically, including the one that matters most:
an extraction whose supporting quote is not actually in the source document.
"""
from __future__ import annotations

import json
import re

import pytest

from agent import research
from agent.research import BRIEFS, candidate_documents, excerpt_for, read_document


class StubLLM:
    """Stands in for the OpenAI driver and returns a fixed payload."""

    available = True
    model = "stub"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, system: str, user: str, max_tokens: int = 500) -> str:
        self.calls += 1
        return json.dumps(self.payload)


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Every case needs its own cache directory.

    The request text is identical across cases, so a shared cache would serve the first
    case's answer to all the others and every gate would appear to pass.
    """
    monkeypatch.setattr(research, "CACHE", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="module")
def hd_net_sales():
    """A real document, a real sentence from it, and the figure that sentence states.

    The quote and the value have to be consistent: the gate now requires the reported
    number to appear in its own supporting quote, so a mismatched pair would be rejected
    for the wrong reason and mask whichever rejection a test is actually probing.
    """
    brief = BRIEFS[("HD", "Net sales")]
    docs = candidate_documents(brief)
    assert docs, "expected HD net-sales candidate documents in the frozen corpus"
    doc = docs[-1]
    match = re.search(r"[^\n]{0,80}[Nn]et sales[^\n]{0,80}?(\d[\d,]{3,})[^\n]{0,60}", doc.body())
    assert match, "expected a real net-sales sentence carrying a figure"
    quote = match.group(0).strip()
    value = float(match.group(1).replace(",", ""))
    assert brief.low <= value <= brief.high, f"{value} is outside the brief's own bounds"
    return brief, doc, quote, value


@pytest.fixture
def honest(hd_net_sales):
    """The payload a well-behaved agent would return for this document."""
    _, _, quote, value = hd_net_sales
    return {"value": value, "units_stated": "$ in millions", "period": "Q1 2026",
            "quote": quote, "confidence": "high", "notes": ""}


def _payload(honest_payload: dict, **overrides) -> dict:
    base = dict(honest_payload)
    base.update(overrides)
    return base


def test_honest_extraction_is_admitted(hd_net_sales, honest, isolated_cache):
    brief, doc, _, value = hd_net_sales
    result = read_document(doc, brief, StubLLM(honest))
    assert result.admitted, f"honest payload was rejected: {result.rejection}"
    assert result.rejection is None
    assert result.value == pytest.approx(value)


def test_hallucinated_quote_is_rejected(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    fabricated = "Net sales for the quarter were $99,999 million, an all-time record."
    result = read_document(doc, brief, StubLLM(_payload(honest, quote=fabricated)))
    assert not result.admitted
    assert "verbatim" in (result.rejection or "")


def test_implausible_value_is_rejected(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(honest, value=999_999_999)))
    assert not result.admitted
    assert "plausible range" in (result.rejection or "")


def test_missing_quote_is_rejected(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(honest, quote="")))
    assert not result.admitted
    assert "no supporting quote" in (result.rejection or "")


def test_low_confidence_is_rejected(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(honest, confidence="low")))
    assert not result.admitted
    assert "low confidence" in (result.rejection or "")


def test_agent_declining_is_rejected_not_guessed(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(honest, value=None, quote="",
                                                        notes="only GAAP stated")))
    assert not result.admitted
    assert result.value is None


def test_unparsable_answer_is_rejected(hd_net_sales, honest, isolated_cache):
    brief, doc, _, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(honest, value="not a number")))
    assert not result.admitted
    assert "not numeric" in (result.rejection or "")


def test_value_absent_from_its_own_quote_is_rejected(hd_net_sales, honest, isolated_cache):
    """A real sentence that does not contain the reported number must not pass.

    This is the ADI Q3 2020 failure in miniature: a genuine sentence about a merger's
    pro-forma revenue was being used to justify that quarter's revenue figure.
    """
    brief, doc, _, value = hd_net_sales
    other = round(value * 0.5, 1)   # in range, real quote, but not the quoted figure
    assert brief.low <= other <= brief.high
    result = read_document(doc, brief, StubLLM(_payload(honest, value=other)))
    assert not result.admitted
    assert "does not appear in its own supporting quote" in (result.rejection or "")


@pytest.mark.parametrize(
    "value, quote, expected",
    [
        (41400.0, "reported sales of $41.4 billion for the third quarter", True),
        (38198.0, "| Net sales | $ 38,198 | $ 39,704 | (3.8)% |", True),
        (1456.0, "| Revenue | $ 1,456,136 | $ 1,480,143 |", True),   # thousands table
        (2.4, "comparable sales increased 2.4%", True),
        (1456.0, "expected revenue of $8.2 billion on a pro forma basis", False),
        (99.9, "net sales were $41.4 billion", False),
    ],
)
def test_corroboration_handles_unit_scales(value, quote, expected):
    assert research.quote_corroborates(value, quote) is expected


def test_excerpt_is_focused_and_bounded(hd_net_sales):
    brief, doc, _, _ = hd_net_sales
    body = doc.body()
    text = excerpt_for(body, brief)
    assert len(text) <= research.MAX_EXCERPT_CHARS
    assert any(term.lower() in text.lower() for term in brief.terms)


def test_agent_yields_nothing_without_a_key_or_cached_answers(monkeypatch, tmp_path):
    """With neither credentials nor committed answers the agent contributes nothing.

    It must not fall back to guessing; the deterministic parsers carry the series instead.
    """
    monkeypatch.setattr(research.LLM, "available", property(lambda self: False))
    monkeypatch.setattr(research, "CACHE", str(tmp_path / "empty"))
    assert research.research("HD", "Net sales") == []
    assert research.available() is False


def test_committed_answers_replay_without_a_key(monkeypatch):
    """The reproducibility claim: cached readings work with no credentials and no network.

    Without this the architecture page's promise that a reviewer can reproduce the
    submitted numbers keyless would be false.
    """
    if not research.has_cached_answers():
        pytest.skip("no committed answers in this checkout")

    monkeypatch.setattr(research.LLM, "available", property(lambda self: False))
    assert research.available() is True

    from agent import history

    series = history.series_for("HD", "Net sales")
    assert series is not None and len(series.observations) > 0


def test_every_target_metric_has_a_brief():
    from agent.history import _SERIES_BUILDERS

    assert set(_SERIES_BUILDERS) == set(BRIEFS), "each target metric needs an analyst brief"
