from __future__ import annotations

import unittest

from agent import history, prequential
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

    def test_short_adjusted_eps_history_remains_explicitly_skipped(self):
        adjusted_eps = history.series_for("HD", "Adjusted diluted EPS")
        self.assertIsNotNone(adjusted_eps)
        result = prequential.backtest_metric("HD", "Adjusted diluted EPS", "eps")

        self.assertEqual(len(adjusted_eps.observations), 7)
        self.assertTrue(result["insufficient"])

    def test_frozen_corpus_supports_ten_prequential_metrics(self):
        rows = prequential.run_all()

        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(not row.get("insufficient") for row in rows), 10)


if __name__ == "__main__":
    unittest.main()
