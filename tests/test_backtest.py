from __future__ import annotations

import unittest
from dataclasses import replace

from agent.backtest import (
    DEFAULT_BACKTEST_CONFIG,
    BacktestConfig,
    _causal_series,
    forecast_metric,
)


class StubModel:
    def __init__(self, model_id, predict):
        self.id = model_id
        self.label = model_id
        self.plug = "code"
        self._predict = predict

    def predict(self, values):
        return self._predict(values)


def seasonal_naive(values):
    return values[-4] if len(values) >= 4 else None


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.axis = list(range(30))
        self.values = [float(100 + index) for index in self.axis]
        self.baseline = StubModel("seasonal_naive", seasonal_naive)

    def test_causal_fill_never_uses_a_future_value(self):
        axis, values, filled = _causal_series(
            list(range(6)),
            [10.0, 11.0, None, 100.0, None, 102.0],
        )

        self.assertEqual(axis, list(range(6)))
        self.assertEqual(values[2], 11.0)
        self.assertEqual(values[4], 10.0)
        self.assertEqual(filled, [False, False, True, False, True, False])

    def test_invalid_config_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "origin_window"):
            BacktestConfig(origin_window=3, min_origins=4)
        with self.assertRaisesRegex(ValueError, "weight_cap"):
            BacktestConfig(weight_cap=0.0)

    def test_explicit_config_controls_warmup(self):
        perfect = StubModel("perfect", lambda values: values[-1] + 1.0)
        fast = replace(
            DEFAULT_BACKTEST_CONFIG,
            config_id="fast",
            origin_window=4,
            min_origins=2,
        )

        result = forecast_metric(
            self.axis,
            self.values,
            "money",
            models=[self.baseline, perfect],
            config=fast,
        )

        self.assertEqual(result["backtest_config"]["config_id"], "fast")
        self.assertEqual(result["origin_audit"][1]["phase"], "warmup")
        self.assertEqual(result["origin_audit"][2]["phase"], "adaptive")
        self.assertEqual(result["n_ensemble_origins"], 4)

    def test_candidate_is_scored_on_paired_origins(self):
        sparse = StubModel(
            "sparse",
            lambda values: values[-1] + 1.0 if len(values) % 2 == 0 else None,
        )

        result = forecast_metric(
            self.axis,
            self.values,
            "money",
            models=[self.baseline, sparse],
        )
        row = next(item for item in result["leaderboard"] if item["model"] == "sparse")

        self.assertEqual(row["origins"], 8)
        self.assertEqual(row["error"], 0.0)
        self.assertEqual(row["paired_baseline_error"], 4.0)
        self.assertTrue(row["eligible"])

    def test_ensemble_error_is_realized_walk_forward_mae(self):
        over_predictor = StubModel("over_by_two", lambda values: values[-1] + 3.0)

        result = forecast_metric(
            self.axis,
            self.values,
            "money",
            models=[self.baseline, over_predictor],
        )

        self.assertAlmostEqual(result["ens_error"], 0.4)
        self.assertAlmostEqual(result["ensemble_baseline_error"], 4.0)
        self.assertAlmostEqual(result["ensemble_skill"], 0.9)

    def test_perfect_baseline_keeps_worse_candidate_out(self):
        constant_values = [100.0] * len(self.axis)
        worse = StubModel("worse", lambda values: values[-1] + 1.0)

        result = forecast_metric(
            self.axis,
            constant_values,
            "money",
            models=[self.baseline, worse],
        )
        row = next(item for item in result["leaderboard"] if item["model"] == "worse")

        self.assertIsNone(row["skill"])
        self.assertFalse(row["eligible"])
        self.assertEqual(result["weights"], {"seasonal_naive": 1.0})


if __name__ == "__main__":
    unittest.main()
