"""One command -> four workbooks using guarded nested parameter selection.

    uv run --with-requirements agent/requirements.txt python -m agent.run
"""
from __future__ import annotations

from . import methodology, output


def main() -> None:
    print(methodology.METHODOLOGY_1["name"], "· guarded nested selection")
    manifest = output.run_pipeline(write=True)
    for c in manifest["companies"]:
        print(f"\n{c['ticker']:4} -> {c['written']}")
        for m in c["metrics"]:
            v = m["point"]
            print(f"     {m['label']:42} {v if v is not None else '—'} {m['units']}")
    print(f"\n{manifest['n_filled']}/{manifest['n_total']} numbers · run `npm run check:submission`")
    if manifest.get("nested_report"):
        print(f"nested report · {manifest['nested_report']['markdown']}")


if __name__ == "__main__":
    main()
