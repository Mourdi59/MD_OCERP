# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who points at a WBS node: one resolver over the known reference columns (SPEC rules 3, 4).

The columns are bare strings or GUIDs in other modules, none with a foreign key
(SPEC decision 3). They hold a ``ProjectWBS`` id or its code, sometimes
something else entirely (a finance budget may key on a BOQ section id). This
module reads them by table and column name through SQL, so it imports none of
those modules and a missing table (a module not installed) is skipped.

A value resolves when it equals a node id or, case-insensitively, a node code.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefColumn:
    """One column that may hold a WBS id or code, and how its rows reach the project."""

    module: str
    table: str
    column: str
    # SQL joining ``t`` (the table) to ``project_id``; ``{pid}`` is bound as :pid.
    scope: str


REFERENCE_COLUMNS: tuple[RefColumn, ...] = (
    RefColumn(
        "boq",
        "oe_boq_position",
        "wbs_id",
        "JOIN oe_boq_boq p ON p.id = t.boq_id WHERE p.project_id = :pid",
    ),
    RefColumn(
        "finance",
        "oe_finance_invoice_item",
        "wbs_id",
        "JOIN oe_finance_invoice p ON p.id = t.invoice_id WHERE p.project_id = :pid",
    ),
    RefColumn("finance", "oe_finance_budget", "wbs_id", "WHERE t.project_id = :pid"),
    RefColumn(
        "procurement",
        "oe_procurement_po_item",
        "wbs_id",
        "JOIN oe_procurement_po p ON p.id = t.po_id WHERE p.project_id = :pid",
    ),
    RefColumn(
        "fieldreports",
        "oe_fieldreports_workforce",
        "wbs_id",
        "JOIN oe_fieldreports_report p ON p.id = t.field_report_id WHERE p.project_id = :pid",
    ),
    RefColumn("inspections", "oe_inspections_inspection", "wbs_id", "WHERE t.project_id = :pid"),
    RefColumn("cvr", "oe_cvr_line", "wbs_id", "JOIN oe_cvr_report p ON p.id = t.report_id WHERE p.project_id = :pid"),
    RefColumn(
        "field_time",
        "oe_field_time_line",
        "wbs",
        "JOIN oe_field_time_timesheet p ON p.id = t.timesheet_id WHERE p.project_id = :pid",
    ),
    RefColumn(
        "schedule",
        "oe_schedule_activity",
        "wbs_code",
        "JOIN oe_schedule_schedule p ON p.id = t.schedule_id WHERE p.project_id = :pid",
    ),
    RefColumn("design_management", "oe_design_drawing", "wbs_node_id", "WHERE t.project_id = :pid"),
    RefColumn("design_management", "oe_design_deliverable", "wbs_node_id", "WHERE t.project_id = :pid"),
)


@dataclass(frozen=True)
class Reference:
    module: str
    table: str
    row_id: str
    value: str


async def _existing_tables(session: AsyncSession) -> set[str]:
    def _names(sync_conn: Any) -> set[str]:
        from sqlalchemy import inspect

        return set(inspect(sync_conn).get_table_names())

    conn = await session.connection()
    return await conn.run_sync(_names)


async def collect_references(session: AsyncSession, project_id: uuid.UUID) -> list[Reference]:
    """Every non-empty value in every known column for this project."""
    tables = await _existing_tables(session)
    out: list[Reference] = []
    for ref in REFERENCE_COLUMNS:
        if ref.table not in tables:
            continue
        sql = (
            f"SELECT t.id, t.{ref.column} FROM {ref.table} t {ref.scope} "  # noqa: S608 - names are constants above
            f"AND t.{ref.column} IS NOT NULL"
        )
        try:
            async with session.begin_nested():
                rows = (await session.execute(text(sql), {"pid": project_id})).all()
        except Exception:
            logger.warning("design: WBS reference column %s.%s unreadable", ref.table, ref.column, exc_info=True)
            continue
        for row_id, value in rows:
            v = str(value).strip()
            if v:
                out.append(Reference(ref.module, ref.table, str(row_id), v))
    return [*out, *await _list_references(session, project_id)]


def _node_index(nodes: list[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_id = {str(n.id).lower(): n for n in nodes}
    by_code = {(n.code or "").strip().casefold(): n for n in nodes}
    return by_id, by_code


def resolve_value(nodes: list[Any], value: str) -> Any | None:
    """A node for an id or a code, else ``None`` (rule 4)."""
    by_id, by_code = _node_index(nodes)
    v = (value or "").strip()
    return by_id.get(v.lower()) or by_code.get(v.casefold())


async def _list_references(session: AsyncSession, project_id: uuid.UUID) -> list[Reference]:
    """WBS ids this module keeps in JSON lists (role responsibility, distribution matrix)."""
    from sqlalchemy import select

    from app.modules.design_management.models import DesignDistributionRule, DesignRole

    out: list[Reference] = []
    for model, column in ((DesignRole, "responsible_wbs_ids"), (DesignDistributionRule, "wbs_node_ids")):
        rows = (await session.execute(select(model).where(model.project_id == project_id))).scalars()
        for row in rows:
            out.extend(
                Reference("design_management", model.__tablename__, str(row.id), str(value))
                for value in getattr(row, column) or []
                if value
            )
    return out


async def reference_counts(session: AsyncSession, project_id: uuid.UUID, nodes: list[Any]) -> dict[str, Counter]:
    """``{node_id: Counter(module -> rows)}`` for every node that is referenced."""
    out: dict[str, Counter] = {}
    for ref in await collect_references(session, project_id):
        node = resolve_value(nodes, ref.value)
        if node is not None:
            out.setdefault(str(node.id), Counter())[ref.module] += 1
    return out


async def unresolved_references(session: AsyncSession, project_id: uuid.UUID, nodes: list[Any]) -> list[Reference]:
    """References whose value matches no node of the project (``wbs_reference_unresolved``)."""
    return [r for r in await collect_references(session, project_id) if resolve_value(nodes, r.value) is None]


__all__ = [
    "REFERENCE_COLUMNS",
    "RefColumn",
    "Reference",
    "collect_references",
    "reference_counts",
    "resolve_value",
    "unresolved_references",
]
