"""OpenAI driver — the LLM the agent uses to read / extract / explain.

Loads OPENAI_API_KEY from .env (python-dotenv). Every completion is disk-cached, so a
re-run with the same prompt is free and reproducible (Methodology 1 §13). If no key is
set, `available` is False and callers fall back gracefully — the NUMERIC pipeline never
depends on the LLM (Methodology 1: the LLM never sets the forecast numbers).
"""
from __future__ import annotations

import hashlib
import json
import os

from .corpus import ROOT

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "llm")


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass


_load_env()


class LLM:
    def __init__(self, model: str | None = None, use_cache: bool = True):
        # Default is gpt-4o so a fresh clone (no .env) hits the committed gpt-4o research
        # cache and reproduces the submitted numbers offline. Override with OPENAI_MODEL.
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.use_cache = use_cache
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.key)

    def status(self) -> dict:
        return {"available": self.available, "model": self.model,
                "key": (self.key[:6] + "…") if self.key else None}

    def _cache_path(self, k: str) -> str:
        os.makedirs(CACHE, exist_ok=True)
        return os.path.join(CACHE, hashlib.sha1(k.encode("utf-8")).hexdigest()[:16] + ".json")

    def complete_json(self, system: str, user: str, max_tokens: int = 500) -> str | None:
        """Return the raw JSON string from the model (or None if unavailable / error)."""
        if not self.available:
            return None
        cache_key = f"{self.model}\n{system}\n{user}"
        cp = self._cache_path(cache_key)
        if self.use_cache and os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as fh:
                    return json.load(fh).get("raw")
            except Exception:
                pass
        try:
            if self._client is None:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.key)
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                max_tokens=max_tokens, temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
        except Exception:
            return None
        if self.use_cache and raw:
            try:
                with open(cp, "w", encoding="utf-8") as fh:
                    json.dump({"raw": raw}, fh, ensure_ascii=False)
            except Exception:
                pass
        return raw
