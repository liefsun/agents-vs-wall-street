"""Agent pipeline for Agents vs Wall Street.

Same skeleton as the lab pipeline: extract -> candidate models -> causal prequential
paired gate -> prior-origin capped ensemble -> fuse (with guidance anchor) -> point + band.
Built during the event; the only new hard part vs the lab is Stage-1 extraction
(unstructured text corpus -> period-indexed numeric panel), which is why the
extractor is a deterministic table parser with an LLM fallback + disk cache.
"""

from .backtest import BacktestConfig, DEFAULT_BACKTEST_CONFIG

__all__ = ["BacktestConfig", "DEFAULT_BACKTEST_CONFIG"]
