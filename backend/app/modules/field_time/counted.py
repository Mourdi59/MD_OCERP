# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Which timesheets count as actuals, written once for SQL and for Python.

A timesheet's hours are actuals when the sheet is approved and is not itself a
reversal. Correcting an approved sheet does not edit it: the original flips to
``reversed`` and a mirror sheet is written, approved, with ``reverses_id`` set
and its hours still positive (the sign lives on the sheet, see
``field_time_math.net_hours``). So ``status == 'approved'`` alone drops the
original and counts the mirror at face value, which reports a cancelled day in
full. Excluding sheets that reverse something drops both halves and a cancelled
day is worth nothing, which is what it is worth.

Post-calculation, position actuals and the KPI catalog all read hours, and each
used to spell this rule out for itself. They live here so that a fourth reader
cannot get it backwards.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement

#: The one status whose hours are actuals.
COUNTED_STATUS = "approved"


def counted_timesheet_clause() -> ColumnElement[bool]:
    """SQL predicate on ``FieldTimesheet`` selecting the sheets whose hours count."""
    from app.modules.field_time.models import FieldTimesheet

    return and_(FieldTimesheet.status == COUNTED_STATUS, FieldTimesheet.reverses_id.is_(None))


def is_counted_timesheet(sheet: Any) -> bool:
    """The same rule for a loaded sheet, for callers that filter in Python."""
    return getattr(sheet, "status", None) == COUNTED_STATUS and getattr(sheet, "reverses_id", None) is None


__all__ = ["COUNTED_STATUS", "counted_timesheet_clause", "is_counted_timesheet"]
