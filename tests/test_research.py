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
    brief = BRIEFS[("HD", "Net sales")]
    docs = candidate_documents(brief)
    assert docs, "expected HD net-sales candidate documents in the frozen corpus"
    doc = docs[-1]
    match = re.search(r"[^.\n]{20,180}net sales[^.\n]{0,180}\.", doc.body(), re.IGNORECASE)
    assert match, "expected a real net-sales sentence to quote"
    return brief, doc, match.group(0).strip()


def _payload(**overrides) -> dict:
    base = {"value": 45000.0, "units_stated": "$ in millions", "period": "Q2 2025",
            "quote": "", "confidence": "high", "notes": ""}
    base.update(overrides)
    return base


def test_honest_extraction_is_admitted(hd_net_sales, isolated_cache):
    brief, doc, real_quote = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(quote=real_quote)))
    assert result.admitted
    assert result.rejection is None
    assert result.value == pytest.approx(45000.0)


def test_hallucinated_quote_is_rejected(hd_net_sales, isolated_cache):
    brief, doc, _ = hd_net_sales
    fabricated = "Net sales for the quarter were $99,999 million, an all-time record."
    result = read_document(doc, brief, StubLLM(_payload(quote=fabricated)))
    assert not result.admitted
    assert "verbatim" in (result.rejection or "")


def test_implausible_value_is_rejected(hd_net_sales, isolated_cache):
    brief, doc, real_quote = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(value=999_999_999, quote=real_quote)))
    assert not result.admitted
    assert "plausible range" in (result.rejection or "")


def test_missing_quote_is_rejected(hd_net_sales, isolated_cache):
    brief, doc, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(quote="")))
    assert not result.admitted
    assert "no supporting quote" in (result.rejection or "")


def test_low_confidence_is_rejected(hd_net_sales, isolated_cache):
    brief, doc, real_quote = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(quote=real_quote, confidence="low")))
    assert not result.admitted
    assert "low confidence" in (result.rejection or "")


def test_agent_declining_is_rejected_not_guessed(hd_net_sales, isolated_cache):
    brief, doc, _ = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(value=None, notes="only GAAP stated")))
    assert not result.admitted
    assert result.value is None


def test_unparsable_answer_is_rejected(hd_net_sales, isolated_cache):
    brief, doc, real_quote = hd_net_sales
    result = read_document(doc, brief, StubLLM(_payload(value="not a number", quote=real_quote)))
    assert not result.admitted
    assert "not numeric" in (result.rejection or "")


def test_excerpt_is_focused_and_bounded(hd_net_sales):
    brief, doc, _ = hd_net_sales
    body = doc.body()
    text = excerpt_for(body, brief)
    assert len(text) <= research.MAX_EXCERPT_CHARS
    assert any(term.lower() in text.lower() for term in brief.terms)


def test_agent_is_skipped_when_no_key(monkeypatch):
    """With no OpenAI key the agent yields nothing rather than inventing a series."""
    monkeypatch.setattr(research.LLM, "available", property(lambda self: False))
    assert research.research("HD", "Net sales") == []


def test_every_target_metric_has_a_brief():
    from agent.history import _SERIES_BUILDERS

    assert set(_SERIES_BUILDERS) == set(BRIEFS), "each target metric needs an analyst brief"
