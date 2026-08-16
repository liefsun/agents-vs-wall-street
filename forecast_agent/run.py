"""Create an auditable run plan from the organiser challenge manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_COMPANY_FIELDS = {"company", "ticker", "period", "outputFile", "metrics"}
REQUIRED_METRIC_FIELDS = {"label", "units"}


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate the organiser manifest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    companies = manifest.get("companies")
    if not isinstance(companies, list) or len(companies) != 4:
        raise ValueError("challenge manifest must contain exactly four companies")

    output_files: set[str] = set()
    for company in companies:
        missing = REQUIRED_COMPANY_FIELDS - company.keys()
        if missing:
            raise ValueError(f"company is missing fields: {sorted(missing)}")
        if len(company["metrics"]) != 3:
            raise ValueError(f"{company['ticker']} must contain exactly three metrics")
        for metric in company["metrics"]:
            metric_missing = REQUIRED_METRIC_FIELDS - metric.keys()
            if metric_missing:
                raise ValueError(
                    f"{company['ticker']} metric is missing fields: {sorted(metric_missing)}"
                )
        output_file = company["outputFile"]
        if output_file in output_files:
            raise ValueError(f"duplicate output file: {output_file}")
        output_files.add(output_file)

    return manifest


def create_run_plan(manifest: dict[str, Any], run_root: Path) -> Path:
    """Write a timestamped plan that later stages can extend with evidence."""
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    plan = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "status": "planned",
        "companies": [
            {
                "company": company["company"],
                "ticker": company["ticker"],
                "period": company["period"],
                "output_file": company["outputFile"],
                "metrics": company["metrics"],
                "status": "pending",
            }
            for company in manifest["companies"]
        ],
    }
    plan_path = run_dir / "run.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("challenge/companies.json"),
        help="path to the organiser company manifest",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs"),
        help="directory for timestamped run records",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    plan_path = create_run_plan(manifest, args.run_root)
    print(plan_path)


if __name__ == "__main__":
    main()

