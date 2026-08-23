# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Run the demo upload retention sweep by hand, or check what it would do.

The scheduler in :mod:`app.core.demo_retention` runs this once a day on the
hosted demo. This script is the operator's version of the same call: it is how
somebody standing in front of a full disk finds out how much the policy would
free before letting it free anything.

    python -m scripts.demo_retention_sweep --dry-run
    python -m scripts.demo_retention_sweep --dry-run --days 7
    python -m scripts.demo_retention_sweep

Exit codes, so a watchdog or a cron wrapper can act on the result without
parsing prose:

    0  the sweep ran (a run that found nothing to delete is a success)
    1  the sweep ran and something failed: a row, a blob, or the run itself
    2  this deployment is not an armed demo, so nothing ran

2 and 1 are deliberately different. "Nothing was asked of me" is a healthy
result on a self-hosted install; "I was asked and I could not" needs a person.

``--days`` narrows or widens the window for this one call. It cannot arm a
deployment that is not armed: that still takes ``OE_DEMO_READ_ONLY`` plus a
positive ``OE_DEMO_UPLOADS_RETENTION_DAYS``, which is what keeps this script
harmless on a self-hosted install.

The full JSON report is printed on stdout and is also written to
``demo_retention_last_run.json`` in the data directory, exactly as the
scheduled run writes it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.demo_retention import (  # noqa: E402 - after the sys.path bootstrap above
    DEFAULT_RETENTION_DAYS,
    EXCLUDED_SOURCES,
    demo_retention_enabled,
    report_path,
    retention_window_days,
    run_sweep_once,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="demo_retention_sweep",
        description="Apply (or preview) the public demo's upload retention policy.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed and how much it would free, and remove nothing.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help=(
            f"Override the retention window for this call only "
            f"(configured: {retention_window_days()}, recommended: {DEFAULT_RETENTION_DAYS})."
        ),
    )
    args = parser.parse_args(argv)
    if args.days is not None and args.days <= 0:
        parser.error("--days must be a positive number of days")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not demo_retention_enabled():
        print(
            "Not an armed demo: retention needs OE_DEMO_READ_ONLY=true and a positive "
            f"OE_DEMO_UPLOADS_RETENTION_DAYS (currently {retention_window_days()}). Nothing ran.",
            file=sys.stderr,
        )
        return 2

    report = asyncio.run(run_sweep_once(dry_run=args.dry_run, retention_days=args.days))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    print(f"\nReport written to {report_path()}", file=sys.stderr)
    if report.failed:
        print(f"The sweep failed: {report.failure}", file=sys.stderr)
        return 1
    if not report.armed:
        print(f"Nothing ran: {report.skipped_reason}", file=sys.stderr)
        return 2
    if report.capped:
        capped = ", ".join(sorted(s.kind for s in report.sources if s.capped))
        print(
            f"Hit the per-source row cap on: {capped}. There is more backlog; run this again.",
            file=sys.stderr,
        )
    if EXCLUDED_SOURCES:
        print(
            "Sources this policy deliberately does not sweep: " + ", ".join(sorted(EXCLUDED_SOURCES)),
            file=sys.stderr,
        )
    if report.errors:
        print(f"{len(report.errors)} error(s) during the sweep", file=sys.stderr)
        return 1
    verb = "would free" if report.dry_run else "freed"
    print(
        f"{report.rows_deleted} row(s), {report.blobs_deleted} blob(s), {verb} {report.bytes_freed} bytes",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
