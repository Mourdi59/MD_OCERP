"""‌⁠‍Schedule Advanced ORM models - Last Planner System (LPS) + baselines.

Tables:
    oe_schedule_advanced_master_schedule
    oe_schedule_advanced_phase_plan
    oe_schedule_advanced_look_ahead
    oe_schedule_advanced_constraint
    oe_schedule_advanced_commitment
    oe_schedule_advanced_weekly_plan
    oe_schedule_advanced_rnc
    oe_schedule_advanced_baseline
    oe_schedule_advanced_baseline_delta
    oe_schedule_advanced_calendar

All UUID PKs. ``task_ref`` and ``milestone_target_id`` are plain UUID columns
(NOT SQLAlchemy ForeignKey) because they reference ``oe_tasks_task`` /
``oe_schedule_*`` tables across module boundaries - see the architecture guide "critical
lessons" point 2.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# ── Master schedule ─────────────────────────────────────────────────────────


class MasterSchedule(Base):
    """‌⁠‍Top-level project schedule container for the LPS workflow.

    Each project may have many master schedules (e.g. baseline, current
    rev-B, etc.). Phase plans, look-aheads, weekly plans, and baselines
    all hang off a master schedule.
    """

    __tablename__ = "oe_schedule_advanced_master_schedule"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<MasterSchedule {self.name} ({self.status})>"


# ── Phase plan ─────────────────────────────────────────────────────────────


class PhasePlan(Base):
    """‌⁠‍A pull-planning phase (e.g. "Foundations", "Tower Crane Phase").

    Created collaboratively in a pull session. ``milestone_target_id``
    references a task UUID - kept as a plain UUID (NOT FK at ORM level)
    because it crosses module boundaries.
    """

    __tablename__ = "oe_schedule_advanced_phase_plan"

    master_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Plain UUID - references oe_tasks_task without ORM-level FK
    milestone_target_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    pulled_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="in_planning",
        server_default="in_planning",
    )
    pull_session_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    facilitator_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<PhasePlan {self.name} ({self.pulled_status})>"


# ── Look-ahead plan ────────────────────────────────────────────────────────


class LookAheadPlan(Base):
    """A rolling look-ahead window (typically 6 weeks).

    Used to surface constraints that must be cleared before activities
    can be committed to in a weekly work plan.
    """

    __tablename__ = "oe_schedule_advanced_look_ahead"

    master_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    window_weeks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=6,
        server_default="6",
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<LookAheadPlan {self.period_start}–{self.period_end} ({self.status})>"


# ── Constraint ─────────────────────────────────────────────────────────────


class Constraint(Base):
    """A make-ready constraint blocking a task.

    Categories: info / material / labor / equipment / permit / predecessor /
    weather / other.
    """

    __tablename__ = "oe_schedule_advanced_constraint"

    look_ahead_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_look_ahead.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    # Plain UUID - references oe_tasks_task across module boundary
    task_ref: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    constraint_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_clear_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cleared_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="open",
        server_default="open",
        index=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<Constraint {self.constraint_type} task={self.task_ref} {self.status}>"


# ── Weekly work plan ───────────────────────────────────────────────────────


class WeeklyWorkPlan(Base):
    """A weekly work plan - the "commitment week" of LPS.

    Holds commitments made by trade foremen in the Monday planning meeting.
    PPC (Percent Plan Complete) is computed when the plan is closed.
    """

    __tablename__ = "oe_schedule_advanced_weekly_plan"

    master_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    facilitator_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    ppc_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<WeeklyWorkPlan {self.week_start_date} ({self.status})>"


# ── Commitment (aka Promise) ───────────────────────────────────────────────


class Commitment(Base):
    """A "promise" / commitment made for a week's work plan.

    Lifecycle: planned → committed → in_progress → completed | missed | at_risk.
    Missed commitments must have a paired ReasonForNonCompletion row.
    """

    __tablename__ = "oe_schedule_advanced_commitment"

    week_plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_weekly_plan.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    task_ref: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    worker_or_crew: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    promised_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planned",
        server_default="planned",
        index=True,
    )
    made_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    made_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    actual_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 3),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<Commitment task={self.task_ref} {self.status}>"


# ── Reason for non-completion (RNC) ────────────────────────────────────────


class ReasonForNonCompletion(Base):
    """Documented reason a commitment was not completed.

    Drives the LPS RNC pareto chart - root-cause analysis input for
    continuous improvement.
    """

    __tablename__ = "oe_schedule_advanced_rnc"

    commitment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_commitment.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    root_cause_notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<RNC {self.category} for commitment={self.commitment_id}>"


# ── Baseline ───────────────────────────────────────────────────────────────


class Baseline(Base):
    """Frozen snapshot of a master schedule at a point in time.

    ``snapshot`` is a JSON dump of the task list (id, planned_start,
    planned_finish, duration, etc.) at capture time. Used for variance
    tracking via :class:`BaselineDelta`.
    """

    __tablename__ = "oe_schedule_advanced_baseline"

    master_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    captured_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot: Mapped[dict | list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<Baseline {self.name} ({self.status})>"


# ── Baseline delta ─────────────────────────────────────────────────────────


class BaselineDelta(Base):
    """Per-task delta between a baseline and current master schedule.

    Persisted result of comparing :class:`Baseline.snapshot` to the
    current task list. ``schedule_variance_days`` is the positive
    (delay) or negative (acceleration) shift in finish date.
    """

    __tablename__ = "oe_schedule_advanced_baseline_delta"

    baseline_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_baseline.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    current_master_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    task_ref: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    planned_start_baseline: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_start_current: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish_baseline: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish_current: Mapped[date | None] = mapped_column(Date, nullable=True)
    schedule_variance_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<BaselineDelta task={self.task_ref} Δ={self.schedule_variance_days}d>"


# ── Calendar ───────────────────────────────────────────────────────────────


class Calendar(Base):
    """A working calendar for a project.

    ``work_days`` is a JSON list of weekday integers (Mon=0..Sun=6).
    ``holidays`` is a JSON list of ISO date strings.
    ``special_shifts`` is a JSON dict for ad-hoc shift exceptions.
    """

    __tablename__ = "oe_schedule_advanced_calendar"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    work_days: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[0, 1, 2, 3, 4]",
    )
    work_hours_per_day: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("8"),
        server_default="8",
    )
    holidays: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    special_shifts: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<Calendar {self.name} (default={self.is_default})>"


# ── Weekly commitment (Last Planner - Slice 1 CPM build) ───────────────────


class WeeklyCommitment(Base):
    """A weekly Last-Planner commitment row tied to a CPM activity.

    Slice 1 / v4.0 - a slimmer companion to :class:`Commitment` (which is
    scoped to a :class:`WeeklyWorkPlan`). This table is keyed directly by
    ``schedule_id`` so the CPM flow can read / write commitments without
    going through the full LPS hierarchy (master schedule → weekly plan
    → commitment). The two coexist; existing UIs keep using
    :class:`Commitment`.

    PPC (Percent Plan Complete) is auto-computed at write time:
        ``ppc = actual_complete_pct / planned_complete_pct`` clamped to
        ``[0, 1]`` and stored as a fraction (not a percentage).
    """

    __tablename__ = "oe_schedule_advanced_weekly_commitment"

    # No ORM-level FK on schedule_id - schedule lives in the
    # oe_schedule_schedule table (different module). Plain UUID column
    # per the cross-module convention used throughout schedule_advanced.
    schedule_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    # No FK on activity_id either - same reason.
    activity_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    committed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    planned_complete_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc="Planned completion fraction for the week (0..1).",
    )
    actual_complete_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc="Actual completion fraction at week-close (0..1).",
    )
    ppc: Mapped[Decimal] = mapped_column(
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc=(
            "Percent Plan Complete - auto-computed as "
            "actual_complete_pct / planned_complete_pct, clamped to [0, 1]. "
            "0 when planned_complete_pct is 0."
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<WeeklyCommitment activity={self.activity_id} week={self.week_start} ppc={self.ppc}>"


# ── Takt / line-of-balance scheduling ──────────────────────────────────────
#
# Takt scheduling (a.k.a. line-of-balance / takt-time planning) models
# repetitive work that cycles a fixed crew through a sequence of locations
# (levels, blocks, zones) at a steady rhythm. It is parallel to the LPS and
# CPM hierarchies above - it does NOT merge with MasterSchedule's task tree;
# instead a TaktSchedule hangs off a MasterSchedule as an alternative planning
# lens for the repetitive portion of a project.


class TaktSchedule(Base):
    """Container for one takt / line-of-balance planning workflow.

    A takt schedule cycles a crew through an ordered list of
    :class:`Location` rows (the "location sequence") performing each
    :class:`TaktActivity` in turn. ``target_cycle_days`` is the planned
    rhythm - how long the crew spends in each location before handing
    off to the next trade. ``takt_rhythm_tolerance_days`` is the skew
    threshold above which an observed cycle is flagged as a rhythm break.
    """

    __tablename__ = "oe_schedule_advanced_takt_schedule"

    master_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_master_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    target_cycle_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=7,
        server_default="7",
    )
    takt_rhythm_tolerance_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    location_sequence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<TaktSchedule {self.name} ({self.status})>"


class Location(Base):
    """One zone / phase in the takt location sequence.

    ``sequence_order`` (1-based) drives both the y-axis ordering of the
    line-of-balance chart and the staggered start of each crew cycle.
    """

    __tablename__ = "oe_schedule_advanced_takt_location"

    takt_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_takt_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    work_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<Location #{self.sequence_order} {self.name}>"


class TaktActivity(Base):
    """A trade activity in a takt schedule.

    Each activity repeats once per location, cycling top-to-bottom through
    the location sequence at the planned rhythm. ``planned_cycle_duration_days``
    is the crew working duration per location; ``actual_cycle_duration_days``
    captures the observed duration used for rhythm-break detection.

    ``sequence_predecessor_activity_id`` is a self-referential FK encoding
    the trade hand-off order (Formwork → Concrete → Finishes). It is a
    plain ORM FK with ``ON DELETE SET NULL`` so deleting a predecessor does
    not cascade-delete its successors.
    """

    __tablename__ = "oe_schedule_advanced_takt_activity"

    takt_schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_takt_schedule.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_code: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    planned_cycle_duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    crew_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    crew_skill_codes: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    buffer_days_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    sequence_predecessor_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_schedule_advanced_takt_activity.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planned",
        server_default="planned",
    )
    actual_cycle_duration_days: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<TaktActivity {self.name} ({self.status})>"
