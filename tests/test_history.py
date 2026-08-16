from __future__ import annotations

import unittest

from agent import history, prequential, research
from agent.corpus import Doc


class HistoricalSeriesTests(unittest.TestCase):
    def test_period_parsers_do_not_mix_quarterly_and_half_year_axes(self):
        self.assertEqual(history.quarterly_period_key("Q2 and H1 2025"), 2025 * 4 + 1)
        self.assertEqual(history.quarterly_period_key("FY 2024"), 2024 * 4 + 3)
        self.assertIsNone(history.quarterly_period_key("H1 FY2020"))
        self.assertEqual(history.semiannual_period_key("H1 FY2020"), 2020 * 2)
        self.assertEqual(history.semiannual_period_key("FY 2024"), 2024 * 2 + 1)

    def test_quarterly_doc_key_uses_an_explicit_filename_when_metadata_is_h1(self):
        doc = Doc(
            path="/tmp/2021-05-21__de-us-20210521-q2-8k__example.md",
            ticker="DE",
            company="Deere & Company",
            published_at="2021-05-21",
            document_type="FILING",
            period="H1 2021",
            kind="filings",
        )

        self.assertIsNone(history.quarterly_period_key(doc.period))
        self.assertEqual(history.quarterly_doc_key(doc), 2021 * 4 + 1)

    def test_hays_prefers_group_headline_values_over_note_and_region_rows(self):
        operating_profit = history.series_for(
            "HAS", "Pre-exceptional operating profit"
        )
        self.assertIsNotNone(operating_profit)
        by_period = {
            observation.period: observation.value
            for observation in operating_profit.observations
        }

        self.assertEqual(operating_profit.season, 2)
        self.assertEqual(by_period["FY 2018"], 243.4)
        self.assertEqual(by_period["FY 2022"], 210.1)
        self.assertEqual(by_period["FY 2024"], 105.1)

    def test_deere_ppa_uses_the_segment_block(self):
        ppa = history.series_for(
            "DE", "Production & Precision Ag operating profit"
        )
        self.assertIsNotNone(ppa)
        by_period = {
            observation.period: observation.value for observation in ppa.observations
        }

        self.assertEqual(ppa.season, 4)
        self.assertEqual(by_period["Q1 2021"], 643.0)
        self.assertEqual(by_period["H1 2021"], 1007.0)
        self.assertEqual(by_period["Q2 2023"], 2170.0)
        self.assertGreaterEqual(len(ppa.observations), 20)

    def test_research_agent_extends_the_short_adjusted_eps_history(self):
        """The deterministic parser finds 7; the agent reads more without loosening a gate.

        Home Depot's adjusted EPS is a recent non-GAAP disclosure, so most of the corpus
        genuinely does not state it. The agent refuses to substitute GAAP EPS on those
        filings — the extra observations come from documents that do state the adjusted
        figure, not from a relaxed definition.
        """
        parsed = history._SERIES_BUILDERS[("HD", "Adjusted diluted EPS")]()
        self.assertEqual(len(parsed.observations), 7, "deterministic parser baseline")

        if not research.available():
            self.skipTest("no API key and no committed answers to replay")

        merged = history.series_for("HD", "Adjusted diluted EPS")
        self.assertIsNotNone(merged)
        self.assertGreater(len(merged.observations), len(parsed.observations))

    def test_every_target_metric_becomes_scoreable_with_the_agent(self):
        if not research.available():
            self.skipTest("no API key and no committed answers to replay")

        rows = prequential.run_all()

        self.assertEqual(len(rows), 12)
        scoreable = sum(not row.get("insufficient") for row in rows)
        self.assertEqual(scoreable, 12, f"expected all 12 scoreable, got {scoreable}")


if __name__ == "__main__":
    unittest.main()
