# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cross-project performance benchmark: one KPI, read per project, ranked.

The question this answers is the one an estimator and a manager both ask of
finished work: across these projects, what did we actually achieve, and what
range is normal. It is read from the same whitelisted KPI specs as every
custom KPI, grouped by project instead of summed over the portfolio, so a
benchmark can never reach a row a KPI could not.

Three rules carry the design, and each one exists because the obvious
implementation breaks it.

* **The benchmark of a ratio is a ratio of sums.** Two projects at 100 h over
  50 m2 and 300 h over 200 m2 did 400 h over 250 m2: 1.60 h/m2. The mean of
  their own ratios is 1.75 and weighs a small job like a big one. The median
  and quartiles are still over per-project values, because they answer a
  different question (what does a typical project look like), and both are
  served so neither is mistaken for the other.
* **Units are never mixed.** Each unit and currency a KPI spans is its own
  group, with its own benchmark. There is no conversion in this slice.
* **Absent is not zero.** A project with no installed quantity has no
  productivity, and is shown as unavailable with the reason, not ranked first.

Scope is the cohort the caller picked, intersected with what the caller may
open. A project outside that intersection is not named, not counted and not
distinguished from one that does not exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.stats import quartiles, weighted_mean
from app.modules.bi_dashboards import kpi_spec

#: Largest cohort one request may name. A benchmark over more than this is a
#: portfolio report, and the default (every project the caller can open)
#: covers that case without a list in the request.
MAX_COHORT = 500

#: Why a benchmark group has no weighted figure.
WEIGHT_NOT_APPLICABLE = "not_applicable"

#: Ready-made performance KPIs, keyed by a stable id the UI translates.
#:
#: Each is an ordinary spec, validated at import time below, so a preset is
#: exactly what a person could have typed into the custom KPI form and
#: nothing more. The ids are part of the API: the frontend names its labels
#: after them.
PRESETS: dict[str, dict[str, Any]] = {
    "labour_hours_per_installed_unit": {
        "entity": "position_progress",
        "aggregation": "ratio",
        "field": "labour_hours",
        "denominator_field": "installed_quantity",
        # Only positions with something installed, which is the set
        # post-calculation compares too: hours on a position not yet started
        # are work in progress, not a slower rate.
        "filters": [{"field": "installed_quantity", "op": "gt", "value": 0}],
    },
    "plant_hours_per_installed_unit": {
        "entity": "position_progress",
        "aggregation": "ratio",
        "field": "plant_hours",
        "denominator_field": "installed_quantity",
        # Only positions with something installed, which is the set
        # post-calculation compares too: hours on a position not yet started
        # are work in progress, not a slower rate.
        "filters": [{"field": "installed_quantity", "op": "gt", "value": 0}],
    },
    "estimate_rate_per_unit": {
        "entity": "boq_position",
        "aggregation": "ratio",
        "field": "amount",
        "denominator_field": "quantity",
    },
    "budget_per_floor_area": {
        "entity": "project",
        "aggregation": "ratio",
        "field": "budget_estimate",
        "denominator_field": "gross_floor_area",
    },
    "approved_labour_hours": {
        "entity": "field_time_line",
        "aggregation": "sum",
        "field": "labour_hours",
    },
}

#: The presets in their validated, stored form.
VALIDATED_PRESETS: dict[str, dict[str, Any]] = {key: kpi_spec.validate_spec(spec) for key, spec in PRESETS.items()}


class UnknownPerformanceKPI(LookupError):
    """The request named a KPI that is neither a preset nor a custom spec."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"unknown performance KPI {code!r}")


@dataclass
class BenchmarkSummary:
    """The cohort figures for one unit/currency group."""

    weighted: Decimal | None
    weighted_unavailable_reason: str | None
    median: Decimal | None
    p25: Decimal | None
    p75: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    projects_with_data: int
    projects_with_value: int
    records: int


@dataclass
class BenchmarkGroup:
    key: str
    dimensions: dict[str, str | None]
    readings: list[kpi_spec.ProjectReading] = field(default_factory=list)
    summary: BenchmarkSummary | None = None


def summarise(readings: list[kpi_spec.ProjectReading], aggregation: str) -> BenchmarkSummary:
    """The benchmark of one group, from its per-project readings.

    Pure, so the semantics are tested without a database: the weighted figure
    re-divides the summed numerators and denominators for a ratio or a
    weighted average, weighs an average by its row counts, and has no
    weighted reading at all for a sum, count, min or max, whose per-project
    values are totals and extremes rather than rates.
    """
    available = [r for r in readings if r.value is not None]
    values = [r.value for r in available if r.value is not None]
    p25, median, p75 = quartiles(values)

    weighted: Decimal | None = None
    reason: str | None = None
    if aggregation in ("ratio", "weighted_avg"):
        numerator = sum((r.numerator or Decimal("0") for r in available), Decimal("0"))
        denominator = sum((r.denominator or Decimal("0") for r in available), Decimal("0"))
        weighted, reason = (
            kpi_spec.ratio_value(numerator, denominator) if available else (None, kpi_spec.UNAVAILABLE_NO_DATA)
        )
    elif aggregation == "avg":
        weighted = weighted_mean(values, [r.denominator or Decimal("0") for r in available])
        reason = None if weighted is not None else kpi_spec.UNAVAILABLE_NO_DATA
    else:
        reason = WEIGHT_NOT_APPLICABLE

    return BenchmarkSummary(
        weighted=weighted,
        weighted_unavailable_reason=reason,
        median=median,
        p25=p25,
        p75=p75,
        minimum=min(values) if values else None,
        maximum=max(values) if values else None,
        projects_with_data=len({r.project_id for r in readings}),
        projects_with_value=len({r.project_id for r in available}),
        records=sum(r.records for r in readings),
    )


def group_readings(readings: list[kpi_spec.ProjectReading], aggregation: str) -> list[BenchmarkGroup]:
    """Bucket readings by unit/currency partition and summarise each bucket.

    Groups come back largest evidence first, so the group most projects
    share is the one a reader sees first.
    """
    groups: dict[str, BenchmarkGroup] = {}
    for reading in readings:
        group = groups.get(reading.group_key)
        if group is None:
            group = groups[reading.group_key] = BenchmarkGroup(key=reading.group_key, dimensions=reading.dimensions)
        group.readings.append(reading)
    for group in groups.values():
        group.summary = summarise(group.readings, aggregation)
    return sorted(
        groups.values(),
        key=lambda g: (-(g.summary.projects_with_value if g.summary else 0), g.key),
    )


async def resolve_spec(session: AsyncSession, *, kpi: str | None, spec: dict[str, Any] | None) -> dict[str, Any]:
    """The validated spec a request asks for.

    A raw ``spec`` is validated here, on the same terms ``POST /kpis`` uses.
    A ``kpi`` is a preset id first and a stored custom KPI code second.

    Raises:
        KPISpecError: The raw spec is outside the whitelist.
        UnknownPerformanceKPI: ``kpi`` names nothing with a spec.
    """
    if spec is not None:
        return kpi_spec.validate_spec(spec)
    code = (kpi or "").strip()
    if code in VALIDATED_PRESETS:
        return VALIDATED_PRESETS[code]
    loaded = await kpi_spec.load_custom_spec(session, code) if code else None
    if loaded is None:
        raise UnknownPerformanceKPI(code)
    # Stored specs were validated when they were created; validating again
    # costs nothing and keeps a row edited by hand from reaching the binder.
    return kpi_spec.validate_spec(loaded.spec)


def resolve_cohort(requested: list[uuid.UUID], accessible: set[uuid.UUID]) -> set[uuid.UUID]:
    """The projects a benchmark reads: the request, narrowed to what may be seen.

    An empty request means every accessible project. A requested id outside
    ``accessible`` is dropped silently, the same way for a project that
    exists and one that does not, so the response is no existence oracle.
    """
    if not requested:
        return set(accessible)
    return {pid for pid in requested if pid in accessible}


async def project_labels(session: AsyncSession, project_ids: set[uuid.UUID]) -> list[dict[str, Any]]:
    """``[{project_id, name, currency}]`` for the cohort, by name."""
    from app.modules.projects.models import Project

    if not project_ids:
        return []
    rows = (
        await session.execute(
            select(Project.id, Project.name, Project.currency).where(Project.id.in_(sorted(project_ids)))
        )
    ).all()
    out = [{"project_id": pid, "name": name or "", "currency": currency or ""} for pid, name, currency in rows]
    out.sort(key=lambda p: (p["name"].casefold(), str(p["project_id"])))
    return out


async def benchmark(
    session: AsyncSession,
    *,
    spec: dict[str, Any],
    cohort: set[uuid.UUID],
    period_start: _date | None = None,
    period_end: _date | None = None,
) -> list[BenchmarkGroup]:
    """Read ``spec`` per project over ``cohort`` and summarise each group.

    ``cohort`` must already be access-narrowed (see :func:`resolve_cohort`).
    A source module that is not installed reads as no data, the way every
    KPI degrades.
    """
    if not cohort:
        return []
    try:
        readings = await kpi_spec.evaluate_spec_by_project(
            spec,
            session,
            project_ids=cohort,
            period_start=period_start,
            period_end=period_end,
        )
    except ImportError:
        return []
    return group_readings(readings, spec["aggregation"])


__all__ = [
    "MAX_COHORT",
    "PRESETS",
    "VALIDATED_PRESETS",
    "WEIGHT_NOT_APPLICABLE",
    "BenchmarkGroup",
    "BenchmarkSummary",
    "UnknownPerformanceKPI",
    "benchmark",
    "group_readings",
    "project_labels",
    "resolve_cohort",
    "resolve_spec",
    "summarise",
]
