"""Guarded bridge from nested evaluation to the submitted forecast pipeline."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import direct
from .corpus import ROOT
from .parameter_evaluation import (
    build_available_series,
    evaluate_nested_portfolio,
    forecast_recommendations,
    render_markdown_report,
)

DIRECT_MODE = "direct"
GUARDED_NESTED_MODE = "guarded_nested"
VALID_MODES = {DIRECT_MODE, GUARDED_NESTED_MODE}
MIN_OUTER_ORIGINS = 3
MIN_OUTER_SKILL = 0.0


@lru_cache(maxsize=1)
def nested_bundle() -> dict:
    """Compute one immutable-by-convention evaluation bundle per process."""

    series = tuple(build_available_series())
    report = evaluate_nested_portfolio(series)
    recommendations = forecast_recommendations(report, series)
    return {
        "series": series,
        "report": report,
        "recommendations": recommendations,
    }


def selection_decision(evidence: dict | None, recommendation: dict | None) -> dict:
    """Return an auditable production decision for one metric."""

    reasons = []
    if evidence is None:
        reasons.append("no nested outer evidence")
    else:
        if evidence.get("origins", 0) < MIN_OUTER_ORIGINS:
            reasons.append(f"fewer than {MIN_OUTER_ORIGINS} outer origins")
        if (evidence.get("skill") or 0.0) <= MIN_OUTER_SKILL:
            reasons.append("outer skill is not positive")

    if recommendation is None or recommendation.get("point") is None:
        reasons.append("no deployment forecast")
    elif recommendation.get("fallback"):
        reasons.append("deployment forecast fell back to seasonal naive")
    elif (recommendation.get("ensemble_skill") or 0.0) <= 0.0:
        reasons.append("deployment ensemble skill is not positive")

    return {
        "use_nested": not reasons,
        "reasons": reasons,
        "outer_origins": evidence.get("origins", 0) if evidence else 0,
        "outer_mae": evidence.get("mae") if evidence else None,
        "baseline_mae": evidence.get("baseline_mae") if evidence else None,
        "relative_mae": evidence.get("relative_mae") if evidence else None,
        "outer_skill": evidence.get("skill") if evidence else None,
    }


def forecast(ticker: str, mode: str = GUARDED_NESTED_MODE) -> dict:
    """Forecast one company, overriding direct points only when gates pass."""

    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    direct_result = direct.forecast(ticker)
    metrics = {label: dict(metric) for label, metric in direct_result["metrics"].items()}
    result = {**direct_result, "metrics": metrics, "selection_mode": mode}
    if mode == DIRECT_MODE:
        for metric in metrics.values():
            metric["selection"] = {"source": "direct", "use_nested": False}
        return result

    bundle = nested_bundle()
    report = bundle["report"]
    evidence_by_metric = {
        (row["ticker"], row["label"]): row
        for row in report["outer_summary"]["metrics"]
    }
    recommendation_by_metric = {
        (row["ticker"], row["label"]): row
        for row in bundle["recommendations"]
    }

    for label, metric in metrics.items():
        evidence = evidence_by_metric.get((ticker, label))
        recommendation = recommendation_by_metric.get((ticker, label))
        decision = selection_decision(evidence, recommendation)
        metric["direct_point"] = metric.get("point")
        metric["selection"] = {
            "source": "nested" if decision["use_nested"] else "direct",
            **decision,
            "config_id": recommendation.get("config_id") if recommendation else None,
        }
        if not decision["use_nested"]:
            continue

        direct_point = metric["direct_point"]
        metric["point"] = recommendation["point"]
        metric["band"] = recommendation["band"]
        metric["basis"] = (
            f"nested causal ensemble ({recommendation['config_id']} config); "
            f"outer skill {decision['outer_skill']:.1%} across "
            f"{decision['outer_origins']} unseen origins; direct cross-check {direct_point}"
        )
        metric["sources"] = [
            *metric.get("sources", []),
            "Nested causal prequential evaluation; paired seasonal-naive baseline",
        ]

    result["nested_summary"] = {
        "company_rounds": report["outer_summary"]["company_rounds"],
        "outer_predictions": report["outer_summary"]["predictions"],
        "aggregate_skill": report["outer_summary"]["aggregate_skill"],
        "deployment_configs": {
            ticker: recommendation["config_id"]
            for ticker, recommendation in report["deployment_recommendations"].items()
            if recommendation is not None
        },
    }
    return result


def write_nested_report(output_directory: Path | None = None) -> dict:
    """Write the machine-readable and Markdown audit reports."""

    output_directory = output_directory or Path(ROOT) / "outputs"
    output_directory.mkdir(parents=True, exist_ok=True)
    report = nested_bundle()["report"]
    json_path = output_directory / "nested-parameter-evaluation.json"
    markdown_path = output_directory / "nested-parameter-evaluation.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
