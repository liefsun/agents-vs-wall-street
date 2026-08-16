"""One command -> four workbooks in submission/ (Methodology 1, direct output).

    uv run --with-requirements agent/requirements.txt python -m agent.run
"""
from __future__ import annotations

from . import output, methodology


def main() -> None:
    print(methodology.METHODOLOGY_1["name"], "· direct output + ADI causal evaluation")
    manifest = output.run_pipeline(write=True)
    for c in manifest["companies"]:
        print(f"\n{c['ticker']:4} -> {c['written']}")
        for m in c["metrics"]:
            v = m["point"]
            print(f"     {m['label']:42} {v if v is not None else '—'} {m['units']}")
    print(f"\n{manifest['n_filled']}/{manifest['n_total']} numbers · run `npm run check:submission`")


if __name__ == "__main__":
    main()
