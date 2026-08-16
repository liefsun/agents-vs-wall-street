"""Causal walk-forward backtest with a paired seasonal-naive benchmark.

Every origin is evaluated causally with respect to the supplied period series:

* missing history is filled from past data only;
* the ensemble at origin ``t`` uses errors observed strictly before ``t``;
* the first ``MIN_ORIGINS`` origins are a baseline-only warm-up;
* candidates qualify only by beating seasonal naive on the same origins; and
* reported ensemble error is the realized walk-forward MAE, not a weighted
  average of candidate errors.

Guidance remains an exogenous candidate aligned by fiscal target key.  The final
forecast uses the most recent completed origin window to form its weights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import governance
from .methodology import METHOD

GUIDANCE_KEY = "guidance"
GUIDANCE_LABEL = "Company guidance (issued t-1)"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Immutable policy for one causal backtest run.

    ``config_id`` is report metadata. The remaining fields change forecast
    behavior and are therefore selected only inside a nested causal evaluation.
    """

    config_id: str = "current"
    origin_window: int = METHOD.origin_window
    min_train: int = METHOD.min_train
    min_origins: int = METHOD.min_origins
    weight_cap: float = METHOD.weight_cap
    baseline_weight_floor: float = METHOD.baseline_weight_floor
    min_improvement: float = METHOD.min_improvement
    season: int = METHOD.season
    baseline: str = METHOD.baseline

    def __post_init__(self):
        if not self.config_id.strip():
            raise ValueError("config_id must be non-empty")
        if self.season < 1:
            raise ValueError("season must be at least 1")
        if self.min_train < self.season:
            raise ValueError("min_train must be at least season")
        if self.min_origins < 1:
            raise ValueError("min_origins must be at least 1")
        if self.origin_window < self.min_origins:
            raise ValueError("origin_window must be at least min_origins")
        if not 0.0 < self.weight_cap <= 1.0:
            raise ValueError("weight_cap must be greater than 0 and at most 1")
        if not 0.0 <= self.baseline_weight_floor <= 1.0:
            raise ValueError("baseline_weight_floor must be between 0 and 1")
        if not 0.0 <= self.min_improvement < 1.0:
            raise ValueError("min_improvement must be between 0 and 1")
        if not self.baseline.strip():
            raise ValueError("baseline must be non-empty")

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_BACKTEST_CONFIG = BacktestConfig()

# Compatibility aliases for callers that displayed these values before config
# injection. Forecast logic below reads the explicit config object instead.
WEIGHT_CAP = DEFAULT_BACKTEST_CONFIG.weight_cap
BASELINE_WEIGHT_FLOOR = DEFAULT_BACKTEST_CONFIG.baseline_weight_floor
MIN_IMPROVEMENT = DEFAULT_BACKTEST_CONFIG.min_improvement
MIN_TRAIN = DEFAULT_BACKTEST_CONFIG.min_train
MIN_ORIGINS = DEFAULT_BACKTEST_CONFIG.min_origins
ORIGIN_WINDOW = DEFAULT_BACKTEST_CONFIG.origin_window
SEASON = DEFAULT_BACKTEST_CONFIG.season


def _causal_series(axis, values, season=SEASON):
    """Trim the series and fill gaps using information available before the gap.

    A missing value uses the value from the same seasonal position when possible,
    otherwise the last observed/filled value.  Unlike bidirectional interpolation,
    this rule cannot import a later actual into an earlier forecast origin.
    """
    known = [i for i, value in enumerate(values) if value is not None]
    if len(known) < 2:
        return [], [], []

    lo, hi = known[0], known[-1]
    axis2 = axis[lo:hi + 1]
    segment = values[lo:hi + 1]
    result: list[float] = []
    filled: list[bool] = []

    for i, value in enumerate(segment):
        if value is not None:
            result.append(float(value))
            filled.append(False)
            continue

        seasonal_index = i - season
        replacement = result[seasonal_index] if seasonal_index >= 0 else result[-1]
        result.append(float(replacement))
        filled.append(True)

    return axis2, result, filled


def _mae(pairs):
    """Mean absolute error for ``(actual, prediction)`` pairs."""
    if not pairs:
        return None
    return float(np.mean([abs(actual - prediction) for actual, prediction in pairs]))


def _normalise(weights):
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in weights.items()}


def _cap(weights, cap=WEIGHT_CAP):
    """Cap a multi-model allocation and redistribute excess weight."""
    weights = _normalise(dict(weights))
    if len(weights) <= 1:
        return weights
    cap = max(cap, 1.0 / len(weights))

    for _ in range(len(weights) + 2):
        over = {key: value for key, value in weights.items() if value > cap + 1e-12}
        if not over:
            break
        excess = sum(value - cap for value in over.values())
        for key in over:
            weights[key] = cap
        under = {key: value for key, value in weights.items() if key not in over}
        under_total = sum(under.values())
        if under_total <= 0:
            break
        for key, value in under.items():
            weights[key] += excess * value / under_total

    return _normalise(weights)


def _with_baseline_floor(weights, baseline, floor=BASELINE_WEIGHT_FLOOR):
    """Keep the mandatory benchmark represented after performance weighting."""
    weights = _normalise(weights)
    if len(weights) <= 1 or weights.get(baseline, 0.0) >= floor:
        return weights

    other_total = sum(value for key, value in weights.items() if key != baseline)
    if other_total <= 0:
        return {baseline: 1.0}
    scale = (1.0 - floor) / other_total
    adjusted = {
        key: floor if key == baseline else value * scale
        for key, value in weights.items()
    }
    return _normalise(adjusted)


def _paired_stats(history, candidate, baseline, config=DEFAULT_BACKTEST_CONFIG):
    """Score a candidate and baseline on their common forecast origins."""
    paired = []
    for row in history:
        predictions = row["predictions"]
        candidate_prediction = predictions.get(candidate)
        baseline_prediction = predictions.get(baseline)
        if candidate_prediction is None or baseline_prediction is None:
            continue
        paired.append((row["actual"], candidate_prediction, baseline_prediction))

    candidate_error = _mae([(actual, prediction) for actual, prediction, _ in paired])
    baseline_error = _mae([(actual, prediction) for actual, _, prediction in paired])
    skill = None
    if candidate_error is not None and baseline_error is not None:
        if baseline_error > 0:
            skill = 1.0 - candidate_error / baseline_error
        else:
            skill = 0.0 if candidate_error == 0 else None

    eligible = (
        len(paired) >= config.min_origins
        and baseline_error is not None
        and baseline_error > 0
        and candidate_error <= baseline_error * (1.0 - config.min_improvement)
    )
    return {
        "error": candidate_error,
        "paired_baseline_error": baseline_error,
        "skill": skill,
        "origins": len(paired),
        "eligible": eligible,
    }


def _baseline_stats(history, baseline):
    pairs = [
        (row["actual"], row["predictions"][baseline])
        for row in history
        if row["predictions"].get(baseline) is not None
    ]
    error = _mae(pairs)
    return {
        "error": error,
        "paired_baseline_error": error,
        "skill": 0.0 if error is not None else None,
        "origins": len(pairs),
        "eligible": bool(pairs),
    }


def _weights_from_history(
    history,
    candidate_ids,
    baseline,
    config=DEFAULT_BACKTEST_CONFIG,
):
    """Learn weights from completed origins only.

    Candidate inverse-error weights use paired relative MAE, which keeps a model
    with sparse predictions comparable to seasonal naive on exactly the same rows.
    """
    stats = {baseline: _baseline_stats(history, baseline)}
    for candidate in candidate_ids:
        if candidate != baseline:
            stats[candidate] = _paired_stats(history, candidate, baseline, config)

    if stats[baseline]["origins"] < config.min_origins:
        return {baseline: 1.0}, stats, False

    raw = {baseline: 1.0}
    for candidate in candidate_ids:
        if candidate == baseline or not stats[candidate]["eligible"]:
            continue
        candidate_error = stats[candidate]["error"]
        paired_baseline_error = stats[candidate]["paired_baseline_error"]
        relative_error = candidate_error / paired_baseline_error
        raw[candidate] = 1.0 / max(relative_error, 1e-9)

    weights = _with_baseline_floor(
        _cap(raw, config.weight_cap),
        baseline,
        config.baseline_weight_floor,
    )
    return weights, stats, True


def _available_weights(weights, predictions, baseline):
    available = {
        key: weight
        for key, weight in weights.items()
        if predictions.get(key) is not None and np.isfinite(predictions[key])
    }
    if not available and predictions.get(baseline) is not None:
        return {baseline: 1.0}
    return _normalise(available)


def _ensemble_prediction(predictions, weights):
    if not weights:
        return None
    return float(sum(weights[key] * predictions[key] for key in weights))


def forecast_metric(
    axis,
    values,
    kind,
    guidance_by_key=None,
    models=None,
    config=None,
):
    """Backtest candidates causally, then forecast the next period.

    The returned payload preserves the original UI contract while adding an
    ``origin_audit`` trail and realized ensemble diagnostics.
    """
    config = config or DEFAULT_BACKTEST_CONFIG
    guidance_by_key = guidance_by_key or {}
    models = models if models is not None else governance.active_models(kind)
    model_map = {model.id: model for model in models}
    baseline = config.baseline
    if baseline not in model_map:
        raise ValueError(f"models must include mandatory baseline '{baseline}'")

    axis2, series, filled = _causal_series(axis, values, config.season)
    if len(series) < config.min_train + 1:
        return {
            "kind": kind,
            "point": None,
            "insufficient": True,
            "n_used": len(series),
            "backtest_config": config.to_dict(),
        }

    candidate_ids = [model.id for model in models] + [GUIDANCE_KEY]
    origin_audit = []
    for index in range(config.min_train, len(series)):
        if filled[index]:
            continue

        train = series[:index]
        actual = series[index]
        target_key = axis2[index]
        predictions = {}
        for model in models:
            prediction = model.predict(train)
            if prediction is not None and np.isfinite(prediction):
                predictions[model.id] = float(prediction)

        guidance = guidance_by_key.get(target_key)
        if guidance is not None and np.isfinite(guidance):
            predictions[GUIDANCE_KEY] = float(guidance)
        if predictions.get(baseline) is None:
            continue

        history = origin_audit[-config.origin_window:]
        planned_weights, _, ready = _weights_from_history(
            history,
            candidate_ids,
            baseline,
            config,
        )
        weights = _available_weights(planned_weights, predictions, baseline)
        ensemble_prediction = _ensemble_prediction(predictions, weights)
        origin_audit.append({
            "target_key": target_key,
            "actual": actual,
            "predictions": predictions,
            "weights": weights,
            "ensemble_prediction": ensemble_prediction,
            "ensemble_error": abs(actual - ensemble_prediction),
            "baseline_error": abs(actual - predictions[baseline]),
            "phase": "adaptive" if ready else "warmup",
        })

    history = origin_audit[-config.origin_window:]
    planned_weights, stats, ready = _weights_from_history(
        history,
        candidate_ids,
        baseline,
        config,
    )

    target_key = axis2[-1] + 1
    final_predictions = {}
    for model in models:
        prediction = model.predict(series)
        if prediction is not None and np.isfinite(prediction):
            final_predictions[model.id] = float(prediction)
    final_guidance = guidance_by_key.get(target_key)
    if final_guidance is not None and np.isfinite(final_guidance):
        final_predictions[GUIDANCE_KEY] = float(final_guidance)

    weights = _available_weights(planned_weights, final_predictions, baseline)
    point = _ensemble_prediction(final_predictions, weights)

    evaluation_rows = [
        row for row in origin_audit if row["phase"] == "adaptive"
    ][-config.origin_window:]
    ensemble_error = _mae([
        (row["actual"], row["ensemble_prediction"])
        for row in evaluation_rows
    ])
    ensemble_baseline_error = _mae([
        (row["actual"], row["predictions"][baseline])
        for row in evaluation_rows
    ])
    ensemble_skill = None
    if ensemble_error is not None and ensemble_baseline_error:
        ensemble_skill = 1.0 - ensemble_error / ensemble_baseline_error

    band = None
    if point is not None and ensemble_error is not None:
        band = (point - ensemble_error, point + ensemble_error)

    def label(model_id):
        if model_id == GUIDANCE_KEY:
            return GUIDANCE_LABEL
        return model_map[model_id].label if model_id in model_map else model_id

    def plug(model_id):
        if model_id == GUIDANCE_KEY:
            return "hot"
        return model_map[model_id].plug if model_id in model_map else "code"

    leaderboard = []
    for model_id in candidate_ids:
        row_stats = stats.get(model_id, {
            "error": None,
            "paired_baseline_error": None,
            "skill": None,
            "origins": 0,
            "eligible": False,
        })
        leaderboard.append({
            "model": model_id,
            "label": label(model_id),
            "plug": plug(model_id),
            **row_stats,
            "weight": round(weights.get(model_id, 0.0), 3),
            "final_pred": final_predictions.get(model_id),
        })
    leaderboard.sort(key=lambda row: (
        row["error"] is None,
        row["error"] if row["error"] is not None else float("inf"),
    ))

    baseline_error = stats[baseline]["error"]
    return {
        "kind": kind,
        "loss": "MAE",
        "backtest_config": config.to_dict(),
        "point": point,
        "band": band,
        "ens_error": ensemble_error,
        "ensemble_baseline_error": ensemble_baseline_error,
        "ensemble_skill": ensemble_skill,
        "baseline_error": baseline_error,
        "weights": weights,
        "leaderboard": leaderboard,
        "origin_audit": origin_audit,
        "n_used": len(series),
        "n_origins": max((item["origins"] for item in stats.values()), default=0),
        "n_ensemble_origins": len(evaluation_rows),
        "target_key": target_key,
        "fallback": not ready or set(weights) == {baseline},
        "insufficient": False,
        "imputed_periods": [key for key, was_filled in zip(axis2, filled) if was_filled],
    }
