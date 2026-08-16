import json
import tempfile
import unittest
from pathlib import Path

from forecast_agent.run import create_run_plan, load_manifest


ROOT = Path(__file__).resolve().parents[1]


class RunContractTests(unittest.TestCase):
    def test_organiser_manifest_is_valid(self) -> None:
        manifest = load_manifest(ROOT / "challenge" / "companies.json")
        self.assertEqual(len(manifest["companies"]), 4)
        self.assertEqual(sum(len(item["metrics"]) for item in manifest["companies"]), 12)

    def test_run_plan_contains_every_required_output(self) -> None:
        manifest = load_manifest(ROOT / "challenge" / "companies.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = create_run_plan(manifest, Path(temp_dir))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))

        expected = {company["outputFile"] for company in manifest["companies"]}
        actual = {company["output_file"] for company in plan["companies"]}
        self.assertEqual(actual, expected)
        self.assertEqual(plan["status"], "planned")


if __name__ == "__main__":
    unittest.main()

