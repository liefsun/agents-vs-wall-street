"""Corpus loader: index the frozen Markdown corpus by company / type / date.

The corpus lives at challenge/offline-data/<company>/{filings,call-transcripts,slides}.
Every document begins with a YAML-ish frontmatter block:

    ---
    company: "Analog Devices"
    ticker: "ADI"
    published_at: "2015-08-18"
    document_type: "FILING"
    period: "Q3 2015"
    ---

We keep this deliberately dependency-free (no PyYAML) — the frontmatter is a flat
key: "value" block, so a line parser is enough and avoids a dependency at event time.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "challenge", "offline-data")

# companies.json uses HD / ADI / LSE:HAS / DE; the corpus folders are these:
FOLDER = {
    "HD": "home-depot",
    "ADI": "analog-devices",
    "HAS": "hays",
    "DE": "deere",
}
DOC_TYPES = ("filings", "call-transcripts", "slides")

_FM_LINE = re.compile(r'^([a-z_]+):\s*(?:"(.*)"|(.*))\s*$')


@dataclass
class Doc:
    path: str
    ticker: str
    company: str
    published_at: str          # "YYYY-MM-DD"
    document_type: str         # FILING / TRANSCRIPT / SLIDE (from frontmatter)
    period: str                # e.g. "Q3 2015", "FY 2024"
    kind: str                  # folder: filings / call-transcripts / slides
    _body: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def body(self) -> str:
        if not self._body:
            self._body = read_body(self.path)
        return self._body


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Tolerates a missing block."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end]
    body = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_block.splitlines():
        m = _FM_LINE.match(line.strip())
        if m:
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else (m.group(3) or "")
            fm[key] = val.strip()
    return fm, body


def read_body(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        _, body = _split_frontmatter(fh.read())
    return body


def _read_head(path: str, n: int = 4000) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(n)


def load_docs(ticker: str, kinds: tuple[str, ...] = DOC_TYPES) -> list[Doc]:
    """All docs for a ticker, sorted by published_at ascending."""
    folder = FOLDER[ticker]
    out: list[Doc] = []
    for kind in kinds:
        d = os.path.join(CORPUS, folder, kind)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".md") or fn.upper() == "INDEX.MD":
                continue
            path = os.path.join(d, fn)
            fm, _ = _split_frontmatter(_read_head(path))
            out.append(Doc(
                path=path,
                ticker=fm.get("ticker", ticker),
                company=fm.get("company", ""),
                published_at=fm.get("published_at", fn[:10]),
                document_type=fm.get("document_type", ""),
                period=fm.get("period", ""),
                kind=kind,
            ))
    out.sort(key=lambda x: (x.published_at, x.name))
    return out


def earnings_releases(ticker: str) -> list[Doc]:
    """Quarterly / annual earnings press releases (the 8-K / results filings).

    These carry the reported figures + the outlook for the next period, so they
    are the backbone for both the actuals series and the historical guidance.
    """
    docs = load_docs(ticker, kinds=("filings",))
    pat = re.compile(r"-(q[1-4]|fy)-8k|results|earnings|trading|-8k", re.I)
    hits = [d for d in docs if pat.search(d.name)]
    return hits or docs
