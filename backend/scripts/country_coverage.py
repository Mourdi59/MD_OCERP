#!/usr/bin/env python3
# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Print the country coverage manifest for one or more countries.

    python scripts/country_coverage.py CA
    python scripts/country_coverage.py CA US DE CN

The exit code reports the health of the instrument, not the health of the
product. A country with no rows anywhere still exits 0, because that is a
finding and the tool found it. A probe that could not resolve its registry
exits 1, because then the tool is the thing that is broken and its zeroes must
not be read as coverage. Use --strict to also fail on a country with nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.country_coverage import (  # noqa: E402
    ABSENT,
    COVERED,
    FALLBACK,
    MISSING,
    NOT_KEYED,
    UNRESOLVED,
    country_coverage,
    dimensions,
    shared_calendar_rows,
)

_MARK = {
    COVERED: "COVERED  ",
    FALLBACK: "fallback ",
    MISSING: "MISSING  ",
    NOT_KEYED: "not-keyed",
    ABSENT: "ABSENT   ",
    UNRESOLVED: "UNRESOLVED",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", nargs="*", default=["CA"], help="ISO 3166-1 alpha-2 codes")
    parser.add_argument("--strict", action="store_true", help="also fail when a country has no covered dimension")
    args = parser.parse_args()

    unresolved_total = 0
    bare = []

    for code in args.countries or ["CA"]:
        report = country_coverage(code)
        print(f"\n=== {report.country_code} " + "=" * 52)
        width = max(len(d) for d in dimensions())
        for d in report.dimensions:
            note = "" if d.method == "import" else f"  [read from {d.method}]"
            print(f"  {_MARK.get(d.verdict, d.verdict):<10}  {d.dimension:<{width}}  {d.detail}{note}")
            if d.verdict == UNRESOLVED:
                print(f"  {'':<10}  {'':<{width}}  source: {d.source or '(unknown)'}")
        print("  " + report.summary())
        counts = report.counts
        unresolved_total += counts[UNRESOLVED]
        if not counts[COVERED] and not counts[FALLBACK]:
            bare.append(report.country_code)

    # Registry-level, so it is printed once rather than per country. A shared
    # row is a limit on how far per-country divergence can go before the row has
    # to be split, and no country's own report can carry the size of it: DE
    # knows it is on a row with AT and CH and cannot know how much of the axis
    # is like that. Counted over the axis and not over the countries asked
    # about, so the number does not move when this command is given a longer
    # list.
    census_failure = ""
    try:
        census = shared_calendar_rows()
    except Exception as exc:  # noqa: BLE001 - reported below, the same way a probe's failure is
        census_failure = f"{type(exc).__name__}: {exc}"
        print(f"\nregistry limits: the shared-row census could not be taken ({census_failure})")
    else:
        note = "" if census.method == "import" else f"  [read from {census.method}]"
        print(f"\nregistry limits: {census.summary()}{note}")

    print()
    if unresolved_total or census_failure:
        if unresolved_total:
            print(f"INSTRUMENT UNHEALTHY: {unresolved_total} probe(s) could not resolve a registry.")
        if census_failure:
            print("INSTRUMENT UNHEALTHY: the shared-row census could not read its registry.")
        print("Those are not coverage gaps. Do not count them as either covered or missing.")
        return 1
    print("instrument healthy: every probe resolved its registry and returned a verdict")
    if args.strict and bare:
        print(f"strict: {', '.join(bare)} has no covered or fallback dimension")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
