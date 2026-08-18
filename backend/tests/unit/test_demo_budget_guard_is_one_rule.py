# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Keep the budget re-seed suite honest about the guard it claims to describe.

``tests/pg/test_demo_budget_reseed_idempotent.py`` cannot call the seeder's
budget guard: it sits in the middle of an install routine that writes every
module and cannot be entered for one. So that suite mirrors the guard, and a
mirror is a second copy of a rule, which is the failure mode the suite exists
to catch wearing the other face.

It already happened. The real guard moved from ``category`` alone to the whole
of what ``ProjectBudget`` is unique on, ``(project_id, wbs_id, category)``,
because the seed began writing a WBS reference and a bill legitimately carries
one cost group under several sections. The mirror kept the old key, stayed
green, and could no longer have gone red for the defect it was written for -
nor for the new one, where a category-only guard drops the second real line.

These read the seeder's source rather than its behaviour, which is a poor
substitute for calling it and is what is available. They live in the unit lane
on purpose: everything under ``tests/pg/`` is skipped wholesale without
``OE_TEST_DB=pg``, so a pin placed beside the mirror would be missing from
exactly the runs that would otherwise never notice.
"""

from __future__ import annotations

import re
from pathlib import Path

SEEDER = Path(__file__).resolve().parents[2] / "app" / "core" / "demo_projects.py"
MIRROR = Path(__file__).resolve().parents[1] / "pg" / "test_demo_budget_reseed_idempotent.py"


def _seeder() -> str:
    return SEEDER.read_text(encoding="utf-8")


def test_the_guard_reads_both_columns_of_the_key() -> None:
    selected = re.findall(r"select\(\s*ProjectBudget\.(\w+)\s*,\s*ProjectBudget\.(\w+)\s*\)", _seeder())
    assert len(selected) == 1, (
        f"expected one two-column read of ProjectBudget in the seeder, found {len(selected)}: {selected}"
    )
    assert set(selected[0]) == {"wbs_id", "category"}, (
        f"the budget guard keys on {selected[0]}; the pg mirror keys on (wbs_id, category)"
    )


def test_the_guard_runs_before_the_insert() -> None:
    assert "if (wbs_id, bl[" in _seeder(), (
        "the budget guard's membership test is gone or reshaped - the pg mirror is now fiction"
    )


def test_the_seeder_reports_what_it_wrote_not_what_it_was_offered() -> None:
    assert 'results["finance_budgets"] = added_budgets' in _seeder(), (
        "a fully skipped re-run reads as a fully successful one again"
    )


def test_the_mirror_keys_on_the_same_pair() -> None:
    """The other half: the mirror is what these tests pin the seeder to.

    Asserting only against the seeder would let the mirror drift instead, and
    the pg suite would go on describing a rule nothing implements.
    """
    mirror = MIRROR.read_text(encoding="utf-8")
    assert "select(ProjectBudget.wbs_id, ProjectBudget.category)" in mirror, (
        "the pg mirror no longer reads the pair this file pins the seeder to"
    )
    assert "if key in existing" in mirror, "the pg mirror no longer guards on the composed key"
