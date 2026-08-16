"""One command -> all available company workbooks in submission/.

    uv run --with-requirements agent/requirements.txt python -m agent.run

This is the shape of the challenge's required "final command". Companies without a
wired extractor are skipped with a clear notice (no silent gaps).
"""
from __future__ import annotations

from .forecast import forecast_company, METRIC_MAP
from . import workbook

TICKERS = ["HD", "ADI", "HAS", "DE"]


def main() -> None:
    for t in TICKERS:
        if t not in METRIC_MAP:
            print(f"SKIP {t:4} — extractor pending")
            continue
        fc = forecast_company(t)
        path = workbook.write_workbook(fc)
        vals = "  ".join(
            f"{m.label}={m.point:.2f}" for m in fc["metrics"] if m.point is not None
        )
        print(f"OK   {t:4} -> {path}")
        print(f"        {vals}")


if __name__ == "__main__":
    main()
