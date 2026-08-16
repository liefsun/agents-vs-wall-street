"""Nested causal evaluation for shared backtest-policy parameters.

The inner loop selects one :class:`BacktestConfig` using paired observations that
finish strictly before an outer target. The outer loop then records genuinely unseen
method and seasonal-naive errors. Deployment selection is reported separately.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import mean, median
from types import MappingProxyType

import numpy as np

from . import governance, prequential
from .backtest import DEFAULT_BACKTEST_CONFIG, BacktestConfig, forecast_metric
from .forecast import METRIC_MAP, company_spec


@dataclass(frozen=True, slots=True)
class BacktestSeries:
    """One metric history supplied to the shared-config evaluator."""

    name: str
    ticker: str
    label: str
    kind: str
    axis: tuple[int, ...]
    values: tuple[float | None, ...]
    season: int = 4
    guidance_by_key: Mapping[int, float] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    models: tuple[object, ...] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("series name must be non-empty")
        axis = tuple(self.axis)
        values = tuple(self.values)
        if len(axis) != len(values):
            raise ValueError("axis and values must have the same length")
        if tuple(sorted(set(axis))) != axis:
            raise ValueError("axis must be strictly increasing")
        if self.season < 1:
            raise ValueError("season must be at least 1")
        object.__setattr__(self, "axis", axis)
        object.__setattr__(self, "values", values)
        object.__setattr__(
            self,
            "guidance_by_key",
            MappingProxyType(dict(self.guidance_by_key)),
        )
        if self.models is not None:
            object.__setattr__(self, "models", tuple(self.models))


@dataclass(frozen=True, slots=True)
class NestedEvaluationConfig:
    """Fixed evaluation protocol; these values are not tuned by the report."""

    inner_window: int = 12
    min_inner_origins: int = 6
    outer_window: int = 8
    min_series: int = 1

    def __post_init__(self) -> None:
        if self.min_inner_origins < 1:
            raise ValueError("min_inner_origins must be at least 1")
        if self.inner_window < self.min_inner_origins:
            raise ValueError("inner_window must be at least min_inner_origins")
        if self.outer_window < 1:
            raise ValueError("outer_window must be at least 1")
        if self.min_series < 1:
            raise ValueError("min_series must be at least 1")

    def to_dict(self) -> dict:
        return {
            "inner_window": self.inner_window,
            "min_inner_origins": self.min_inner_origins,
            "outer_window": self.outer_window,
            "min_series": self.min_series,
        }


DEFAULT_NESTED_EVALUATION_CONFIG = NestedEvaluationConfig()

DEFAULT_PARAMETER_CONFIGS = (
    DEFAULT_BACKTEST_CONFIG,
    replace(
        DEFAULT_BACKTEST_CONFIG,
        config_id="responsive",
        origin_window=8,
        min_origins=4,
    ),
    replace(
        DEFAULT_BACKTEST_CONFIG,
        config_id="diversified",
        origin_window=12,
        weight_cap=0.50,
        baseline_weight_floor=0.25,
    ),
    replace(
        DEFAULT_BACKTEST_CONFIG,
        config_id="strict",
        min_train=12,
        min_origins=8,
        weight_cap=0.50,
        min_improvement=0.10,
    ),
)


def parameter_configs_for_season(season: int) -> tuple[BacktestConfig, ...]:
    """Pre-registered policy candidates scaled to the reporting frequency."""

    if season == 4:
        return DEFAULT_PARAMETER_CONFIGS
    if season != 2:
        raise ValueError(f"unsupported reporting season: {season}")
    base = replace(
        DEFAULT_BACKTEST_CONFIG,
        season=2,
        origin_window=8,
        min_train=4,
        min_origins=3,
    )
    return (
        base,
        replace(base, config_id="responsive", origin_window=4, min_origins=2),
        replace(
            base,
            config_id="diversified",
            origin_window=6,
            weight_cap=0.50,
            baseline_weight_floor=0.25,
        ),
        replace(
            base,
            config_id="strict",
            min_train=6,
            min_origins=4,
            weight_cap=0.50,
            min_improvement=0.10,
        ),
    )


def nested_evaluation_for_season(season: int) -> NestedEvaluationConfig:
    """Pre-registered nested windows measured in observations, not calendar quarters."""

    if season == 4:
        return DEFAULT_NESTED_EVALUATION_CONFIG
    if season == 2:
        return NestedEvaluationConfig(
            inner_window=6,
            min_inner_origins=3,
            outer_window=4,
        )
    raise ValueError(f"unsupported reporting season: {season}")


def _mae(errors: Sequence[float]) -> float | None:
    return float(mean(errors)) if errors else None


def _relative_mae(method_mae: float, baseline_mae: float) -> float | None:
    if baseline_mae > 0:
        return method_mae / baseline_mae
    if method_mae == 0:
        return 1.0
    return None


def _baseline_prediction(result: dict, baseline: str) -> float | None:
    for row in result.get("leaderboard", []):
        if row["model"] == baseline:
            return row["final_pred"]
    return None


def _one_step_record(
    series: BacktestSeries,
    target_index: int,
    config: BacktestConfig,
) -> dict | None:
    actual = series.values[target_index]
    if actual is None or target_index == 0:
        return None

    result = forecast_metric(
        series.axis[:target_index],
        series.values[:target_index],
        series.kind,
        guidance_by_key=series.guidance_by_key,
        models=series.models,
        config=config,
    )
    target_key = series.axis[target_index]
    prediction = result.get("point")
    baseline_prediction = _baseline_prediction(result, config.baseline)
    if result.get("target_key") != target_key:
        return None
    if prediction is None or baseline_prediction is None:
        return None
    if not np.isfinite(prediction) or not np.isfinite(baseline_prediction):
        return None

    actual_value = float(actual)
    prediction_value = float(prediction)
    baseline_value = float(baseline_prediction)
    return {
        "series": series.name,
        "ticker": series.ticker,
        "label": series.label,
        "kind": series.kind,
        "target_key": target_key,
        "actual": actual_value,
        "prediction": prediction_value,
        "baseline_prediction": baseline_value,
        "absolute_error": abs(actual_value - prediction_value),
        "baseline_absolute_error": abs(actual_value - baseline_value),
    }


def _validate_inputs(
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig],
    evaluation: NestedEvaluationConfig,
) -> None:
    if not series:
        raise ValueError("at least one series is required")
    if not configs:
        raise ValueError("at least one BacktestConfig is required")
    series_names = [item.name for item in series]
    if len(series_names) != len(set(series_names)):
        raise ValueError("series names must be unique")
    config_ids = [item.config_id for item in configs]
    if len(config_ids) != len(set(config_ids)):
        raise ValueError("config_id values must be unique")
    if evaluation.min_series > len(series):
        raise ValueError("min_series cannot exceed the number of series")
    tickers = {item.ticker for item in series}
    if len(tickers) != 1:
        raise ValueError("one nested evaluation must use one company fiscal timeline")
    baselines = {item.baseline for item in configs}
    seasons = {item.season for item in configs}
    if len(baselines) != 1 or len(seasons) != 1:
        raise ValueError("nested candidates must share one baseline and season")
    series_seasons = {item.season for item in series}
    if series_seasons != seasons:
        raise ValueError("series and nested candidates must share one season")


def _precompute_records(series, configs) -> dict:
    records = defaultdict(lambda: defaultdict(dict))
    for item in series:
        for config in configs:
            for target_index in range(1, len(item.axis)):
                record = _one_step_record(item, target_index, config)
                if record is not None:
                    records[item.name][config.config_id][record["target_key"]] = record
    return records


def _common_inner_keys(
    records: dict,
    series_name: str,
    config_ids: Sequence[str],
    outer_target_key: int,
    inner_window: int,
) -> list[int]:
    key_sets = [
        {
            key
            for key in records[series_name][config_id]
            if key < outer_target_key
        }
        for config_id in config_ids
    ]
    if not key_sets:
        return []
    return sorted(set.intersection(*key_sets))[-inner_window:]


def _score_configs_before(
    outer_target_key: int,
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig],
    records: dict,
    evaluation: NestedEvaluationConfig,
) -> list[dict] | None:
    config_ids = [config.config_id for config in configs]
    common_keys = {
        item.name: _common_inner_keys(
            records,
            item.name,
            config_ids,
            outer_target_key,
            evaluation.inner_window,
        )
        for item in series
    }

    scores = []
    for config in configs:
        per_series = []
        for item in series:
            keys = common_keys[item.name]
            if len(keys) < evaluation.min_inner_origins:
                continue
            rows = [records[item.name][config.config_id][key] for key in keys]
            method_mae = _mae([row["absolute_error"] for row in rows])
            baseline_mae = _mae([row["baseline_absolute_error"] for row in rows])
            relative_mae = _relative_mae(method_mae, baseline_mae)
            if relative_mae is None:
                continue
            per_series.append(
                {
                    "series": item.name,
                    "origins": len(rows),
                    "first_target_key": keys[0],
                    "last_target_key": keys[-1],
                    "mae": method_mae,
                    "baseline_mae": baseline_mae,
                    "relative_mae": relative_mae,
                }
            )
        if len(per_series) < evaluation.min_series:
            return None
        scores.append(
            {
                "config_id": config.config_id,
                "relative_mae": float(
                    median(row["relative_mae"] for row in per_series)
                ),
                "series_count": len(per_series),
                "origins": sum(row["origins"] for row in per_series),
                "per_series": per_series,
            }
        )
    return scores


def _select_score(scores: Sequence[dict], config_order: Mapping[str, int]) -> dict:
    return min(
        scores,
        key=lambda row: (row["relative_mae"], config_order[row["config_id"]]),
    )


def _summarize_rows(rows: Sequence[dict]) -> dict:
    by_series = defaultdict(list)
    for row in rows:
        by_series[row["series"]].append(row)

    metric_summaries = []
    for series_name in sorted(by_series):
        metric_rows = by_series[series_name]
        method_mae = _mae([row["absolute_error"] for row in metric_rows])
        baseline_mae = _mae(
            [row["baseline_absolute_error"] for row in metric_rows]
        )
        relative_mae = _relative_mae(method_mae, baseline_mae)
        metric_summaries.append(
            {
                "series": series_name,
                "ticker": metric_rows[0]["ticker"],
                "label": metric_rows[0]["label"],
                "origins": len(metric_rows),
                "mae": method_mae,
                "baseline_mae": baseline_mae,
                "relative_mae": relative_mae,
                "skill": None if relative_mae is None else 1.0 - relative_mae,
                "wins": sum(
                    row["absolute_error"] < row["baseline_absolute_error"]
                    for row in metric_rows
                ),
            }
        )

    usable_ratios = [
        row["relative_mae"]
        for row in metric_summaries
        if row["relative_mae"] is not None
    ]
    aggregate_relative_mae = float(median(usable_ratios)) if usable_ratios else None
    return {
        "predictions": len(rows),
        "metrics": metric_summaries,
        "aggregate_relative_mae": aggregate_relative_mae,
        "aggregate_skill": (
            None if aggregate_relative_mae is None else 1.0 - aggregate_relative_mae
        ),
    }


def evaluate_nested_parameters(
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig] = DEFAULT_PARAMETER_CONFIGS,
    evaluation: NestedEvaluationConfig = DEFAULT_NESTED_EVALUATION_CONFIG,
) -> dict:
    """Select configs on inner origins and score them on unseen outer targets."""

    series = tuple(series)
    configs = tuple(configs)
    _validate_inputs(series, configs, evaluation)
    records = _precompute_records(series, configs)
    config_order = {config.config_id: index for index, config in enumerate(configs)}
    target_keys = sorted({key for item in series for key in item.axis})

    eligible_rounds = []
    for target_key in target_keys:
        scores = _score_configs_before(
            target_key, series, configs, records, evaluation
        )
        if scores is None:
            continue
        selected_score = _select_score(scores, config_order)
        selected_id = selected_score["config_id"]
        outer_rows = [
            records[item.name][selected_id][target_key]
            for item in series
            if target_key in records[item.name][selected_id]
        ]
        if not outer_rows:
            continue
        inner_last_target_key = max(
            row["last_target_key"] for row in selected_score["per_series"]
        )
        eligible_rounds.append(
            {
                "target_key": target_key,
                "selected_config": selected_id,
                "selected_inner_relative_mae": selected_score["relative_mae"],
                "inner_last_target_key": inner_last_target_key,
                "candidate_scores": scores,
                "outer_rows": outer_rows,
            }
        )

    outer_rounds = eligible_rounds[-evaluation.outer_window :]
    if not outer_rounds:
        raise ValueError("not enough history for nested outer evaluation")
    outer_rows = [row for round_ in outer_rounds for row in round_["outer_rows"]]
    outer_keys = [round_["target_key"] for round_ in outer_rounds]

    fixed_config_evaluation = []
    for config in configs:
        config_rows = [
            records[item.name][config.config_id][target_key]
            for target_key in outer_keys
            for item in series
            if target_key in records[item.name][config.config_id]
        ]
        fixed_config_evaluation.append(
            {"config_id": config.config_id, **_summarize_rows(config_rows)}
        )

    deployment_scores = _score_configs_before(
        max(target_keys) + 1,
        series,
        configs,
        records,
        evaluation,
    )
    recommendation = None
    if deployment_scores is not None:
        recommended_score = _select_score(deployment_scores, config_order)
        recommendation = {
            "config_id": recommended_score["config_id"],
            "relative_mae": recommended_score["relative_mae"],
            "as_of_target_key": max(target_keys),
            "candidate_scores": deployment_scores,
            "performance_included_in_outer_evaluation": False,
        }

    selection_counts = Counter(round_["selected_config"] for round_ in outer_rounds)
    return {
        "method": "nested causal prequential parameter evaluation",
        "loss": {
            "within_series": "MAE",
            "across_series": "median paired relative MAE vs seasonal-naive",
            "skill": "1 - relative MAE",
        },
        "scope": {
            "series": [item.name for item in series],
            "series_count": len(series),
            "evidence_status": (
                "sensitivity evidence only; historical coverage is not portfolio-wide"
            ),
        },
        "evaluation_config": evaluation.to_dict(),
        "candidate_configs": [config.to_dict() for config in configs],
        "outer_rounds": outer_rounds,
        "outer_summary": {
            "rounds": len(outer_rounds),
            "selection_counts": dict(selection_counts),
            **_summarize_rows(outer_rows),
        },
        "fixed_config_evaluation": fixed_config_evaluation,
        "deployment_recommendation": recommendation,
    }


def evaluate_nested_portfolio(
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig] | None = None,
    evaluation: NestedEvaluationConfig | None = None,
) -> dict:
    """Evaluate each company timeline independently, then aggregate outer errors."""

    grouped_series = defaultdict(list)
    for item in series:
        grouped_series[item.ticker].append(item)
    if not grouped_series:
        raise ValueError("at least one series is required")

    company_reports = {}
    company_configs = {}
    company_evaluations = {}
    for ticker, items in sorted(grouped_series.items()):
        seasons = {item.season for item in items}
        if len(seasons) != 1:
            raise ValueError("one company fiscal timeline must use one season")
        season = seasons.pop()
        active_configs = tuple(configs) if configs is not None else parameter_configs_for_season(season)
        active_evaluation = evaluation or nested_evaluation_for_season(season)
        company_reports[ticker] = evaluate_nested_parameters(
            items,
            active_configs,
            active_evaluation,
        )
        company_configs[ticker] = [config.to_dict() for config in active_configs]
        company_evaluations[ticker] = active_evaluation.to_dict()
    outer_rows = [
        row
        for report in company_reports.values()
        for round_ in report["outer_rounds"]
        for row in round_["outer_rows"]
    ]
    selection_counts = Counter(
        round_["selected_config"]
        for report in company_reports.values()
        for round_ in report["outer_rounds"]
    )
    rounds_per_company = {
        ticker: report["outer_summary"]["rounds"]
        for ticker, report in company_reports.items()
    }
    return {
        "method": "company-local nested causal prequential parameter evaluation",
        "loss": {
            "within_series": "MAE",
            "across_series": "median paired relative MAE vs seasonal-naive",
            "skill": "1 - relative MAE",
        },
        "scope": {
            "series": [item.name for item in series],
            "series_count": len(series),
            "company_count": len(company_reports),
            "companies": list(company_reports),
            "evidence_status": (
                "sensitivity evidence only; historical coverage is not portfolio-wide"
            ),
        },
        "evaluation_config": (
            evaluation.to_dict()
            if evaluation is not None
            else {"company_local": True, "by_company": company_evaluations}
        ),
        "candidate_configs": (
            [config.to_dict() for config in configs]
            if configs is not None
            else {"company_local": True, "by_company": company_configs}
        ),
        "company_reports": company_reports,
        "outer_summary": {
            "company_rounds": sum(rounds_per_company.values()),
            "rounds_per_company": rounds_per_company,
            "selection_counts": dict(selection_counts),
            **_summarize_rows(outer_rows),
        },
        "deployment_recommendations": {
            ticker: report["deployment_recommendation"]
            for ticker, report in company_reports.items()
        },
    }


def build_available_series() -> list[BacktestSeries]:
    """Build every scoreable target history from the current repository."""

    output = []
    for ticker in ("HD", "ADI", "HAS", "DE"):
        spec = company_spec(ticker)
        for metric in spec["metrics"]:
            label = metric["label"]
            historical = prequential.history_for(ticker, label)
            axis, values = historical.axis_values() if historical else (None, None)
            if not axis:
                continue
            mapped_kind = METRIC_MAP.get(ticker, {}).get(label, (None, None))[1]
            kind = mapped_kind or prequential._kind_from_units(metric["units"])
            diagnostic = prequential.backtest_metric(ticker, label, kind)
            if diagnostic.get("insufficient"):
                continue
            output.append(
                BacktestSeries(
                    name=f"{ticker} · {label} ({metric['units']})",
                    ticker=ticker,
                    label=label,
                    kind=kind,
                    axis=tuple(axis),
                    values=tuple(values),
                    season=historical.season,
                    guidance_by_key=prequential.guidance_for(ticker, label),
                    models=tuple(governance.active_models(kind, season=historical.season)),
                )
            )
    return output


def recommended_config(
    report: dict,
    ticker: str,
    configs: Sequence[BacktestConfig] | None = None,
    season: int = 4,
) -> BacktestConfig | None:
    recommendation = report.get("deployment_recommendations", {}).get(ticker)
    if not recommendation:
        return None
    active_configs = tuple(configs) if configs is not None else parameter_configs_for_season(season)
    by_id = {config.config_id: config for config in active_configs}
    return by_id.get(recommendation["config_id"])


def forecast_recommendations(report: dict, series: Sequence[BacktestSeries]) -> list[dict]:
    """Generate next points using the deployment config, with no direct override."""

    recommendations = []
    for item in series:
        config = recommended_config(report, item.ticker, season=item.season)
        if config is None:
            continue
        result = forecast_metric(
            item.axis,
            item.values,
            item.kind,
            guidance_by_key=item.guidance_by_key,
            models=item.models,
            config=config,
        )
        recommendations.append(
            {
                "ticker": item.ticker,
                "label": item.label,
                "kind": item.kind,
                "point": result.get("point"),
                "band": result.get("band"),
                "config_id": config.config_id,
                "fallback": result.get("fallback", True),
                "ensemble_skill": result.get("ensemble_skill"),
                "n_origins": result.get("n_ensemble_origins", 0),
            }
        )
    return recommendations


def _number(value: float | None, digits=3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def render_markdown_report(report: dict) -> str:
    """Render a compact, auditable nested-evaluation report."""

    evaluation = report["evaluation_config"]
    scope = report["scope"]
    summary = report["outer_summary"]
    company_rounds = summary.get("company_rounds", summary.get("rounds", 0))
    if evaluation.get("company_local"):
        protocol_line = (
            "- Protocol windows are company-local and frequency-aware; see the JSON "
            "report for each company's fixed values."
        )
    else:
        protocol_line = (
            f"- Protocol: inner window {evaluation['inner_window']} "
            f"(minimum {evaluation['min_inner_origins']}); "
            f"outer window {evaluation['outer_window']}."
        )
    lines = [
        "# Nested causal parameter evaluation",
        "",
        (
            f"> Status: sensitivity evidence across {scope['series_count']} scoreable "
            "series; this does not claim portfolio-wide parameter optimality."
        ),
        "",
        "## Evaluation contract",
        "",
        "- Inner selection uses paired origins strictly before each outer target.",
        "- Primary loss is MAE; cross-series aggregation is median relative MAE.",
        "- Deployment recommendation is excluded from outer performance.",
        "- Config selection is company-local; fiscal keys are never ordered across companies.",
        protocol_line,
        "",
        "## Nested outer evaluation",
        "",
        (
            f"Company-rounds: **{company_rounds}** · predictions: **{summary['predictions']}** · "
            f"relative MAE: **{_number(summary['aggregate_relative_mae'])}** · "
            f"skill: **{_percent(summary['aggregate_skill'])}**"
        ),
        "",
        "| Metric | Origins | MAE | Baseline MAE | Relative MAE | Skill |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for metric in summary["metrics"]:
        lines.append(
            f"| {metric['series']} | {metric['origins']} | {_number(metric['mae'])} | "
            f"{_number(metric['baseline_mae'])} | {_number(metric['relative_mae'])} | "
            f"{_percent(metric['skill'])} |"
        )

    lines.extend(["", "## Deployment recommendation", ""])
    recommendations = report.get("deployment_recommendations")
    if recommendations is None:
        ticker = scope["series"][0].split(" · ", 1)[0]
        recommendations = {ticker: report.get("deployment_recommendation")}
    for ticker, recommendation in recommendations.items():
        if recommendation is None:
            lines.append(f"- **{ticker}:** insufficient history for a recommendation.")
            continue
        lines.append(
            f"- **{ticker}:** use **{recommendation['config_id']}**; latest-window relative MAE "
            f"is **{_number(recommendation['relative_mae'])}**. This choice is not "
            "included in outer performance."
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--inner-window", type=int)
    parser.add_argument("--min-inner-origins", type=int)
    parser.add_argument("--outer-window", type=int)
    parser.add_argument("--min-series", type=int)
    args = parser.parse_args(argv)

    series = build_available_series()
    evaluation_args = (
        args.inner_window,
        args.min_inner_origins,
        args.outer_window,
        args.min_series,
    )
    evaluation = None
    if any(value is not None for value in evaluation_args):
        defaults = DEFAULT_NESTED_EVALUATION_CONFIG
        evaluation = NestedEvaluationConfig(
            inner_window=(
                args.inner_window
                if args.inner_window is not None
                else defaults.inner_window
            ),
            min_inner_origins=(
                args.min_inner_origins
                if args.min_inner_origins is not None
                else defaults.min_inner_origins
            ),
            outer_window=(
                args.outer_window
                if args.outer_window is not None
                else defaults.outer_window
            ),
            min_series=(
                args.min_series
                if args.min_series is not None
                else defaults.min_series
            ),
        )
    report = evaluate_nested_portfolio(series, evaluation=evaluation)
    markdown = render_markdown_report(report)

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.markdown}")
    else:
        print(markdown)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
