from __future__ import annotations

import unittest

from agent.selection import selection_decision


class SelectionDecisionTests(unittest.TestCase):
    def test_positive_outer_and_deployment_evidence_enables_nested(self):
        evidence = {"origins": 3, "skill": 0.10}
        recommendation = {
            "point": 101.0,
            "fallback": False,
            "ensemble_skill": 0.05,
        }

        decision = selection_decision(evidence, recommendation)

        self.assertTrue(decision["use_nested"])
        self.assertEqual(decision["reasons"], [])

    def test_missing_outer_evidence_keeps_direct_forecast(self):
        recommendation = {
            "point": 101.0,
            "fallback": False,
            "ensemble_skill": 0.05,
        }

        decision = selection_decision(None, recommendation)

        self.assertFalse(decision["use_nested"])
        self.assertIn("no nested outer evidence", decision["reasons"])

    def test_baseline_fallback_keeps_direct_forecast(self):
        evidence = {"origins": 8, "skill": 0.40}
        recommendation = {
            "point": 101.0,
            "fallback": True,
            "ensemble_skill": None,
        }

        decision = selection_decision(evidence, recommendation)

        self.assertFalse(decision["use_nested"])
        self.assertIn(
            "deployment forecast fell back to seasonal naive",
            decision["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
