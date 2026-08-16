"""Nested causal evaluation for backtest-policy parameters.

The inner loop selects one shared :class:`BacktestConfig` from observations that
completed before an outer target. The outer loop then records the selected
configuration's genuinely unseen error against the same seasonal-naive baseline.

This module intentionally searches a small, pre-registered configuration set.
With short quarterly histories, a large Cartesian grid would optimize noise.
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

from . import extract, governance
from .backtest import DEFAULT_BACKTEST_CONFIG, BacktestConfig, forecast_metric
from .forecast import METRIC_MAP, company_spec


@dataclass(frozen=True, slots=True)
class BacktestSeries:
    """One metric series supplied to the shared-config evaluator."""

    name: str
    kind: str
    axis: tuple[int, ...]
    values: tuple[float | None, ...]
    guidance_by_key: Mapping[int, float] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    models: tuple[object, ...] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("series name must be non-empty")
        axis = tuple(self.axis)
        values = tuple(self.values)
        if len(axis) != len(values):
            raise ValueError("axis and values must have the same length")
        if tuple(sorted(set(axis))) != axis:
            raise ValueError("axis must be strictly increasing")
        object.__setattr__(self, "axis", axis)
        object.__setattr__(self, "values", values)
        object.__setattr__(
            self, "guidance_by_key", MappingProxyType(dict(self.guidance_by_key))
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

    def __post_init__(self):
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

    return {
        "series": series.name,
        "kind": series.kind,
        "target_key": target_key,
        "actual": float(actual),
        "prediction": float(prediction),
        "baseline_prediction": float(baseline_prediction),
        "absolute_error": abs(float(actual) - float(prediction)),
        "baseline_absolute_error": abs(float(actual) - float(baseline_prediction)),
    }


def _validate_inputs(
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig],
    evaluation: NestedEvaluationConfig,
):
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
    baselines = {item.baseline for item in configs}
    seasons = {item.season for item in configs}
    if len(baselines) != 1 or len(seasons) != 1:
        raise ValueError(
            "nested candidates must share one structural baseline and season"
        )


def _precompute_records(
    series: Sequence[BacktestSeries],
    configs: Sequence[BacktestConfig],
) -> dict:
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
        {key for key in records[series_name][config_id] if key < outer_target_key}
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
        baseline_mae = _mae([row["baseline_absolute_error"] for row in metric_rows])
        relative_mae = _relative_mae(method_mae, baseline_mae)
        metric_summaries.append(
            {
                "series": series_name,
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
    """Evaluate a shared parameter-selection policy without lookahead.

    Candidate scores at target ``t`` use only common paired origins with keys
    strictly less than ``t``. Reported outer loss contains only the unseen rows
    generated after that selection.
    """
    series = tuple(series)
    configs = tuple(configs)
    _validate_inputs(series, configs, evaluation)
    records = _precompute_records(series, configs)
    config_order = {config.config_id: index for index, config in enumerate(configs)}
    target_keys = sorted({key for item in series for key in item.axis})

    eligible_rounds = []
    for target_key in target_keys:
        scores = _score_configs_before(
            target_key,
            series,
            configs,
            records,
            evaluation,
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

    fixed_config_evaluation = []
    outer_keys = [round_["target_key"] for round_ in outer_rounds]
    for config in configs:
        config_rows = [
            records[item.name][config.config_id][target_key]
            for target_key in outer_keys
            for item in series
            if target_key in records[item.name][config.config_id]
        ]
        fixed_config_evaluation.append(
            {
                "config_id": config.config_id,
                **_summarize_rows(config_rows),
            }
        )

    deployment_target_key = max(target_keys) + 1
    deployment_scores = _score_configs_before(
        deployment_target_key,
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
                "sensitivity evidence only; structured panel coverage is not yet portfolio-wide"
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


def build_company_series(ticker: str) -> list[BacktestSeries]:
    """Build every currently mapped structured series for one company."""
    ticker = ticker.upper()
    panel = extract.build_panel(ticker)
    metric_map = METRIC_MAP.get(ticker, {})
    if not panel or not metric_map:
        raise ValueError(f"{ticker} has no structured backtest panel")

    spec = company_spec(ticker)
    mapped_units = {item["label"]: item["units"] for item in spec["metrics"]}
    output = []
    for label, (internal_metric, kind) in metric_map.items():
        axis, values = extract.metric_series(panel, internal_metric)
        guidance_by_key = {
            row.key + 1: row.guidance_next[internal_metric]
            for row in panel
            if internal_metric in row.guidance_next
        }
        output.append(
            BacktestSeries(
                name=f"{ticker} · {label} ({mapped_units.get(label, '')})",
                kind=kind,
                axis=tuple(axis),
                values=tuple(values),
                guidance_by_key=guidance_by_key,
                models=tuple(governance.active_models(kind)),
            )
        )
    return output


def _number(value: float | None, digits=3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def render_markdown_report(report: dict) -> str:
    """Render a compact, auditable Markdown report."""
    evaluation = report["evaluation_config"]
    scope = report["scope"]
    lines = [
        "# Nested causal parameter evaluation",
        "",
        (
            f"> Status: sensitivity evidence only across {scope['series_count']} structured "
            "series; this report does not claim portfolio-wide parameter optimality."
        ),
        "",
        "## Evaluation contract",
        "",
        "- Inner selection uses only common paired origins strictly before each outer target.",
        "- One configuration is shared across all available metrics at an outer target.",
        "- Primary loss is MAE within a metric and median relative MAE versus seasonal-naive across metrics.",
        "- Deployment recommendation uses only completed history and is excluded from outer performance.",
        (
            f"- Protocol: trailing {evaluation['inner_window']} inner origins "
            f"(minimum {evaluation['min_inner_origins']}); "
            f"at least {evaluation['min_series']} series; "
            f"last {evaluation['outer_window']} eligible outer rounds."
        ),
        "",
        "## Candidate configurations",
        "",
        "| Config | Window | Min train | Min origins | Cap | Baseline floor | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for config in report["candidate_configs"]:
        lines.append(
            f"| {config['config_id']} | {config['origin_window']} | {config['min_train']} | "
            f"{config['min_origins']} | {config['weight_cap']:.2f} | "
            f"{config['baseline_weight_floor']:.2f} | {config['min_improvement']:.0%} |"
        )

    summary = report["outer_summary"]
    lines.extend(
        [
            "",
            "## Nested outer evaluation",
            "",
            (
                f"Outer rounds: **{summary['rounds']}** · "
                f"predictions: **{summary['predictions']}** · "
                f"aggregate relative MAE: **{_number(summary['aggregate_relative_mae'])}** · "
                f"skill: **{_percent(summary['aggregate_skill'])}**"
            ),
            "",
            "| Metric | Origins | Method MAE | Baseline MAE | Relative MAE | Skill | Wins |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in summary["metrics"]:
        lines.append(
            f"| {metric['series']} | {metric['origins']} | {_number(metric['mae'])} | "
            f"{_number(metric['baseline_mae'])} | {_number(metric['relative_mae'])} | "
            f"{_percent(metric['skill'])} | {metric['wins']}/{metric['origins']} |"
        )

    lines.extend(
        [
            "",
            "### Outer decisions",
            "",
            "| Target | Selected config | Inner relative MAE | Last inner target |",
            "|---|---|---:|---|",
        ]
    )
    for round_ in report["outer_rounds"]:
        lines.append(
            f"| {extract.key_to_period(round_['target_key'])} | {round_['selected_config']} | "
            f"{_number(round_['selected_inner_relative_mae'])} | "
            f"{extract.key_to_period(round_['inner_last_target_key'])} |"
        )

    lines.extend(
        [
            "",
            "## Fixed-config sensitivity on the same outer targets",
            "",
            "| Config | Predictions | Aggregate relative MAE | Skill |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in report["fixed_config_evaluation"]:
        lines.append(
            f"| {item['config_id']} | {item['predictions']} | "
            f"{_number(item['aggregate_relative_mae'])} | {_percent(item['aggregate_skill'])} |"
        )

    recommendation = report["deployment_recommendation"]
    lines.extend(["", "## Deployment recommendation", ""])
    if recommendation is None:
        lines.append("Insufficient common history to recommend a configuration.")
    else:
        lines.append(
            f"Use **{recommendation['config_id']}** for the next forecast. Its latest-window "
            f"relative MAE is **{_number(recommendation['relative_mae'])}**. "
            "This choice is operational guidance, not part of the outer performance estimate."
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--company", default="ADI", help="ticker with a structured panel"
    )
    parser.add_argument("--markdown", type=Path, help="write the Markdown report")
    parser.add_argument("--json", type=Path, help="write the machine-readable report")
    parser.add_argument("--inner-window", type=int, default=12)
    parser.add_argument("--min-inner-origins", type=int, default=6)
    parser.add_argument("--outer-window", type=int, default=8)
    parser.add_argument(
        "--min-series",
        type=int,
        help="minimum series per inner score (default: all company series)",
    )
    args = parser.parse_args(argv)

    company_series = build_company_series(args.company)
    evaluation = NestedEvaluationConfig(
        inner_window=args.inner_window,
        min_inner_origins=args.min_inner_origins,
        outer_window=args.outer_window,
        min_series=(
            len(company_series) if args.min_series is None else args.min_series
        ),
    )
    report = evaluate_nested_parameters(
        company_series,
        evaluation=evaluation,
    )
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
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
