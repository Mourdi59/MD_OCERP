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


def _method_note(method: str) -> str:
    """The bracketed mark that says how one verdict was read.

    Args:
        method: A DimensionReport method string.

    Returns:
        The mark to append to the printed line, empty for a plain import.
    """
    if method == "import":
        return ""
    if method == "declared":
        return "  [declared; there is no registry to read]"
    if method == "(none)":
        return "  [nothing was read; the probe raised]"
    return f"  [read from {method}]"


def _provenance(methods: dict[str, int]) -> list[str]:
    """The lines that say how the verdicts above were read.

    Always returns at least one line. The per-verdict marks cannot carry this on
    their own, because they are printed only on the weaker kind of read: a run
    with no marks anywhere looks exactly like a run by a tool that never tracked
    provenance at all. The unmarked run is the one taken on a machine with a
    cluster, which is the same environment that hid this instrument's own defect
    for a day, so the page has to say so in words rather than by their absence.

    Args:
        methods: How many verdicts came back under each method string.

    Returns:
        One line when every verdict came from an import; two when some were
        parsed from a table on purpose; three when any read happened because a
        module would not import, which is the only weaker kind.
    """
    total = sum(methods.values())
    imported = methods.get("import", 0)
    if imported == total:
        return [f"provenance: all {total} verdicts came from importing the live module"]

    read = sum(count for name, count in methods.items() if name.startswith("source"))
    declared = methods.get("declared", 0)
    unread = total - imported - read - declared

    parts = [f"{imported} from importing the live module"]
    if read:
        parts.append(f"{read} from reading the file on disk")
    if declared:
        parts.append(f"{declared} declared, because there is no registry to read")
    if unread:
        parts.append(f"{unread} from nothing at all, because the probe raised")
    lines = [f"provenance: of {total} verdicts, " + ", ".join(parts) + "."]

    # Only the reads that name an exception are the weaker kind. Lumping the two
    # together would flatten the distinction the instrument itself draws, and
    # would call a deliberate parse a degraded one.
    if read:
        lines.append(
            'A structural question answered by parsing a table is marked "source" and is a fair way to ask it.'
        )
        fell_back = sum(count for name, count in methods.items() if name.startswith("source ("))
        if fell_back:
            lines.append(
                f"{fell_back} of those name an exception: the module would not import, so what ran was the file "
                "rather than the object the live process holds, which is weaker evidence than an import."
            )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", nargs="*", default=["CA"], help="ISO 3166-1 alpha-2 codes")
    parser.add_argument("--strict", action="store_true", help="also fail when a country has no covered dimension")
    args = parser.parse_args()

    unresolved_total = 0
    bare = []
    methods: dict[str, int] = {}

    for code in args.countries or ["CA"]:
        report = country_coverage(code)
        print(f"\n=== {report.country_code} " + "=" * 52)
        width = max(len(d) for d in dimensions())
        for d in report.dimensions:
            note = _method_note(d.method)
            methods[d.method] = methods.get(d.method, 0) + 1
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
        # Labelled in both directions. An unlabelled line would mean "imported"
        # only to somebody who already knew the tool labels the other case.
        note = "  [read by import]" if census.method == "import" else _method_note(census.method)
        print(f"\nregistry limits: {census.summary()}{note}")

    print()
    for line in _provenance(methods):
        print(line)

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
