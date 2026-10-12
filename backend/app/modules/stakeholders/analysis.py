# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure stakeholder analysis: score validation, classification, engagement gap, review and feedback due.

No database, no clock: every function takes what it needs, so the rules of the
SPEC (2, 3, 4, 5, 8) are tested as plain functions and the service only feeds
them rows.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.modules.stakeholders.catalogue import AnalysisMethod, StakeholderFramework

NOT_ASSESSED = "not_assessed"


class ScoreError(ValueError):
    """Scores that do not fit the method. ``problems`` lists every one, ``(dimension, code)``."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{d}: {c}" for d, c in problems))
        self.problems = problems


def jsonable(value: Any) -> Any:
    """A JSON column value with no non-JSON scalar left in it.

    UUIDs and Decimals become strings, dates and datetimes ISO strings, tuples
    and sets lists. Every JSON write of this module goes through here, so a row
    never fails to insert on PostgreSQL over a ``date`` hiding in a list.
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [jsonable(v) for v in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"not JSON-safe: {type(value).__name__}")


def assert_json_safe(value: Any) -> Any:
    """Raise ``TypeError`` unless ``json.dumps`` takes the value without a ``default``."""
    json.dumps(value)
    return value


def validate_scores(method: AnalysisMethod, scores: dict[str, Any]) -> dict[str, int | bool]:
    """Normalise ``scores`` against the method (rule 2): all dimensions, in range, nothing extra.

    Raises:
        ScoreError: listing every problem at once.
    """
    problems: list[tuple[str, str]] = []
    out: dict[str, int | bool] = {}
    known = {d.code for d in method.dimensions}
    for extra in sorted(set(scores) - known):
        problems.append((extra, "unknown_dimension"))
    for d in method.dimensions:
        if d.code not in scores or scores[d.code] is None:
            problems.append((d.code, "missing"))
            continue
        raw = scores[d.code]
        if d.type == "bool":
            if not isinstance(raw, bool):
                problems.append((d.code, "not_boolean"))
                continue
            out[d.code] = raw
            continue
        if isinstance(raw, bool) or not isinstance(raw, int):
            problems.append((d.code, "not_integer"))
            continue
        if not d.min <= raw <= d.max:
            problems.append((d.code, "out_of_range"))
            continue
        out[d.code] = raw
    if problems:
        raise ScoreError(problems)
    return out


def classify(method: AnalysisMethod, scores: dict[str, int | bool]) -> str | None:
    """The method's classification for validated scores: first matching rule, else the default."""
    for rule in method.rules:
        ok = True
        for dim, cond in rule.when.items():
            v = scores.get(dim)
            if cond.eq is not None and v is not cond.eq:
                ok = False
            if cond.gte is not None and not (isinstance(v, int) and not isinstance(v, bool) and v >= cond.gte):
                ok = False
            if cond.lte is not None and not (isinstance(v, int) and not isinstance(v, bool) and v <= cond.lte):
                ok = False
            if not ok:
                break
        if ok:
            return rule.classification
    return method.default


def engagement_gap(fw: StakeholderFramework, current: str | None, desired: str | None) -> int | None:
    """``desired - current`` on the ordinal engagement scale; ``None`` when either is unknown (rule 5)."""
    order = fw.engagement_order()
    if current not in order or desired not in order:
        return None
    return order[desired] - order[current]  # type: ignore[index]


@dataclass(frozen=True)
class AssessmentView:
    """What the rules need of one assessment."""

    stakeholder_id: str
    method_code: str
    classification: str | None
    engagement_current: str | None
    engagement_desired: str | None
    assessed_at: datetime


def latest_by_stakeholder(assessments: Iterable[AssessmentView]) -> dict[str, AssessmentView]:
    """Newest assessment per stakeholder, any method (the review clock, rule 4)."""
    out: dict[str, AssessmentView] = {}
    for a in assessments:
        cur = out.get(a.stakeholder_id)
        if cur is None or a.assessed_at > cur.assessed_at:
            out[a.stakeholder_id] = a
    return out


def current_classification(
    assessments: Iterable[AssessmentView], stakeholder_id: str, method_code: str
) -> AssessmentView | None:
    """Newest assessment of a stakeholder under the CURRENT method; older methods are history (rule 3)."""
    mine = [a for a in assessments if a.stakeholder_id == stakeholder_id and a.method_code == method_code]
    return max(mine, key=lambda a: a.assessed_at) if mine else None


def review_due(*, latest_at: datetime | None, external: bool, interval_days: int, today: date) -> bool:
    """Rule 4: latest assessment older than the interval, or none at all for an external stakeholder."""
    if latest_at is None:
        return external
    return (today - latest_at.date()).days > interval_days


def feedback_due_on(held_on: date, days: int) -> date:
    return held_on + timedelta(days=days)


def feedback_not_reported(
    fw: StakeholderFramework,
    *,
    level: str | None,
    status: str,
    held_on: date | None,
    feedback_summary: str | None,
    today: date,
) -> bool:
    """Rule 8: a held event at ``feedback_from_level`` or higher with no feedback after N days."""
    if status != "held" or held_on is None or (feedback_summary or "").strip():
        return False
    order = fw.level_order()
    if level not in order or order[level] < order.get(fw.feedback_from_level, 1):
        return False
    return today > feedback_due_on(held_on, fw.feedback_due_days)


def grid_position(method: AnalysisMethod, scores: dict[str, Any]) -> dict[str, Any] | None:
    """Axis values for the grid: the first two int dimensions, else the bool set (salience Venn)."""
    ints = [d for d in method.dimensions if d.type == "int"]
    if len(ints) >= 2:
        return {
            "x": scores.get(ints[1].code),
            "y": scores.get(ints[0].code),
            "x_dim": ints[1].code,
            "y_dim": ints[0].code,
        }
    bools = [d.code for d in method.dimensions if d.type == "bool"]
    if bools:
        return {"sets": [b for b in bools if scores.get(b) is True]}
    if ints:
        return {"x": scores.get(ints[0].code), "x_dim": ints[0].code}
    return None
