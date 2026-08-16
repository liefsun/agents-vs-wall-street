from __future__ import annotations

import unittest
from dataclasses import replace

from agent.backtest import DEFAULT_BACKTEST_CONFIG
from agent.parameter_evaluation import (
    BacktestSeries,
    NestedEvaluationConfig,
    evaluate_nested_parameters,
    evaluate_nested_portfolio,
    render_markdown_report,
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


class NestedParameterEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = StubModel("seasonal_naive", seasonal_naive)
        self.perfect = StubModel("perfect", lambda values: values[-1] + 1.0)
        self.configs = (
            replace(
                DEFAULT_BACKTEST_CONFIG,
                config_id="slow",
                origin_window=8,
                min_origins=6,
            ),
            replace(
                DEFAULT_BACKTEST_CONFIG,
                config_id="fast",
                origin_window=4,
                min_origins=2,
            ),
        )
        self.evaluation = NestedEvaluationConfig(
            inner_window=8,
            min_inner_origins=4,
            outer_window=4,
        )

    def _series(self, final_actual=135.0, ticker="SYN"):
        axis = tuple(range(36))
        values = [float(100 + index) for index in axis]
        values[-1] = final_actual
        return BacktestSeries(
            name=f"{ticker} synthetic revenue",
            ticker=ticker,
            label="Revenue",
            kind="money",
            axis=axis,
            values=tuple(values),
            models=(self.baseline, self.perfect),
        )

    def test_outer_selection_never_uses_target_actual(self):
        normal = evaluate_nested_parameters(
            [self._series()], self.configs, self.evaluation
        )
        shocked = evaluate_nested_parameters(
            [self._series(final_actual=999.0)], self.configs, self.evaluation
        )

        normal_last = normal["outer_rounds"][-1]
        shocked_last = shocked["outer_rounds"][-1]
        self.assertEqual(normal_last["target_key"], 35)
        self.assertEqual(
            normal_last["selected_config"], shocked_last["selected_config"]
        )
        self.assertEqual(
            normal_last["outer_rows"][0]["prediction"],
            shocked_last["outer_rows"][0]["prediction"],
        )
        self.assertLess(normal_last["inner_last_target_key"], normal_last["target_key"])
        self.assertNotEqual(
            normal_last["outer_rows"][0]["absolute_error"],
            shocked_last["outer_rows"][0]["absolute_error"],
        )

    def test_candidates_use_identical_paired_inner_origins(self):
        report = evaluate_nested_parameters(
            [self._series()], self.configs, self.evaluation
        )

        for round_ in report["outer_rounds"]:
            origin_counts = {
                score["per_series"][0]["origins"]
                for score in round_["candidate_scores"]
            }
            last_inner_keys = {
                score["per_series"][0]["last_target_key"]
                for score in round_["candidate_scores"]
            }
            self.assertEqual(origin_counts, {8})
            self.assertEqual(len(last_inner_keys), 1)
            self.assertLess(last_inner_keys.pop(), round_["target_key"])

    def test_report_separates_outer_performance_from_recommendation(self):
        report = evaluate_nested_parameters(
            [self._series()], self.configs, self.evaluation
        )
        markdown = render_markdown_report(report)

        recommendation = report["deployment_recommendation"]
        self.assertFalse(recommendation["performance_included_in_outer_evaluation"])
        self.assertIn("Nested outer evaluation", markdown)
        self.assertIn("not included in outer performance", markdown)

    def test_portfolio_keeps_company_timelines_separate(self):
        series = [self._series(ticker="AAA"), self._series(ticker="BBB")]

        with self.assertRaisesRegex(ValueError, "one company fiscal timeline"):
            evaluate_nested_parameters(series, self.configs, self.evaluation)

        report = evaluate_nested_portfolio(series, self.configs, self.evaluation)

        self.assertEqual(report["scope"]["company_count"], 2)
        self.assertEqual(set(report["deployment_recommendations"]), {"AAA", "BBB"})
        self.assertEqual(report["outer_summary"]["rounds_per_company"], {"AAA": 4, "BBB": 4})


if __name__ == "__main__":
    unittest.main()
