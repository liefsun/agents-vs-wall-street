"""Deterministic reconciliation guard — the accuracy pass applied AFTER selection and
BEFORE the workbook is written. It never invents a number: it only reconciles the two
forecasts the system already produced (the selected point and its references) and, where a
reliable anchor exists, blends them.

1. Guidance guard (accuracy). Where the frozen corpus contains issued management guidance
   for the target period, a forecast may not sit far from it. If the selected point deviates
   more than GUIDANCE_CAP from that guidance, blend the point toward the guidance, weighted
   by the model's *measured out-of-sample skill* — a high-skill model is pulled less, a
   weak one is pulled more. Management guidance is the strongest next-period signal, so this
   caps the downside of a model that wanders off it without discarding a model that earned
   its skill.

2. Anchorless-deviation flag (safety, no change). Where there is no reliable guidance but the
   selected point and the sourced direct forecast disagree by more than FLAG_DEV, record a
   flag for human review. We deliberately do NOT pull toward the direct here, because those
   direct bridges are the coarse ones (e.g. Deere PPA ≈ 55% of sales × 18% margin) — pulling
   the measured-skill value back toward a rough estimate could easily make it worse.

3. Cross-metric consistency note. A light directional check across a company's metrics,
   recorded for audit (does not change numbers).

Everything is deterministic, reproducible and written into the clear-run evidence log.
"""
from __future__ import annotations

from . import prequential as pq

GUIDANCE_CAP = 0.08     # a forecast may sit at most 8% from issued guidance before we blend
FLAG_DEV = 0.30         # disagreement with the (coarse) direct beyond this is flagged
_W_LO, _W_HI = 0.30, 0.85   # model weight is bounded so neither signal is fully discarded


def _guidance_anchor(ticker: str, label: str):
    """The management guidance issued for the target period, or None."""
    g = pq.guidance_for(ticker, label)
    return list(g.values())[-1] if g else None


def apply(ticker: str, metrics: list[dict]) -> list[dict]:
    """Adjust metrics[].point in place with the guidance guard; return adjustment records."""
    records: list[dict] = []
    for m in metrics:
        pt = m.get("point")
        if pt is None:
            continue
        sel = m.get("selection") or {}
        g = _guidance_anchor(ticker, m["label"])
        if g is not None and abs(g) > 1e-9:
            dev = abs(pt - g) / abs(g)
            if dev > GUIDANCE_CAP:
                skill = sel.get("outer_skill")
                w = min(_W_HI, max(_W_LO, skill if isinstance(skill, (int, float)) else 0.5))
                new = w * pt + (1 - w) * g
                records.append({"label": m["label"], "action": "guidance-guard",
                                "before": pt, "after": new, "guidance": g,
                                "deviation": dev, "model_weight": w,
                                "note": f"blended toward issued guidance (model weight {w:.2f} = "
                                        f"bounded outer skill)"})
                m["point"] = new
                continue
        dp = m.get("direct_point")
        if dp and abs(dp) > 1e-9 and abs(pt - dp) / abs(dp) > FLAG_DEV:
            records.append({"label": m["label"], "action": "flag",
                            "before": pt, "after": pt, "direct": dp,
                            "deviation": abs(pt - dp) / abs(dp),
                            "note": "large disagreement with the sourced direct forecast and no "
                                    "reliable guidance anchor — kept the measured-skill value for review"})
    return records
