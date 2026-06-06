"""‌⁠‍Schedule Advanced Pydantic schemas - request / response models.

Covers all 10 LPS entities plus aggregate response schemas for the
LPS dashboard, PPC chart, RNC pareto, baseline delta, and look-ahead.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Common patterns ────────────────────────────────────────────────────────

_PHASE_STATUS = r"^(in_planning|pulled|active|completed)$"
_LOOK_AHEAD_STATUS = r"^(draft|reviewed|published)$"
_CONSTRAINT_TYPE = r"^(info|material|labor|equipment|permit|predecessor|weather|other)$"
_CONSTRAINT_STATUS = r"^(open|in_progress|cleared|escalated|cannot_clear)$"
_COMMITMENT_STATUS = r"^(planned|committed|in_progress|completed|at_risk|missed)$"
_WEEKLY_STATUS = r"^(draft|committed|in_progress|closed)$"
_BASELINE_STATUS = r"^(active|superseded|archived)$"
_MASTER_STATUS = r"^(active|archived)$"
_RNC_CATEGORY = r"^(manpower|material|equipment|info|weather|predecessor|changes|quality|other)$"


# ── MasterSchedule ─────────────────────────────────────────────────────────


class MasterScheduleCreate(BaseModel):
    """‌⁠‍Create a new master schedule for a project."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    baseline_date: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str = Field(default="active", pattern=_MASTER_STATUS)
    notes: str = ""


class MasterScheduleUpdate(BaseModel):
    """‌⁠‍Patch update for a master schedule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    baseline_date: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str | None = Field(default=None, pattern=_MASTER_STATUS)
    notes: str | None = None


class MasterScheduleResponse(BaseModel):
    """Master schedule returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    baseline_date: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str = "active"
    notes: str = ""
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


# ── PhasePlan ──────────────────────────────────────────────────────────────


class PhasePlanCreate(BaseModel):
    """Create a new phase plan inside a pull session."""

    model_config = ConfigDict(str_strip_whitespace=True)

    master_schedule_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    planned_start: date | None = None
    planned_finish: date | None = None
    milestone_target_id: UUID | None = None
    pulled_status: str = Field(default="in_planning", pattern=_PHASE_STATUS)
    pull_session_at: datetime | None = None
    facilitator_id: UUID | None = None
    notes: str = ""


class PhasePlanUpdate(BaseModel):
    """Patch update for a phase plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    planned_start: date | None = None
    planned_finish: date | None = None
    milestone_target_id: UUID | None = None
    pulled_status: str | None = Field(default=None, pattern=_PHASE_STATUS)
    pull_session_at: datetime | None = None
    facilitator_id: UUID | None = None
    notes: str | None = None


class PhasePlanResponse(BaseModel):
    """Phase plan returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_schedule_id: UUID
    name: str
    planned_start: date | None = None
    planned_finish: date | None = None
    milestone_target_id: UUID | None = None
    pulled_status: str = "in_planning"
    pull_session_at: datetime | None = None
    facilitator_id: UUID | None = None
    notes: str = ""
    created_at: datetime
    updated_at: datetime


# ── LookAheadPlan ──────────────────────────────────────────────────────────


class LookAheadCreate(BaseModel):
    """Create a new look-ahead plan window."""

    model_config = ConfigDict(str_strip_whitespace=True)

    master_schedule_id: UUID
    period_start: date
    period_end: date
    window_weeks: int = Field(default=6, ge=1, le=24)
    generated_at: datetime | None = None
    status: str = Field(default="draft", pattern=_LOOK_AHEAD_STATUS)


class LookAheadUpdate(BaseModel):
    """Patch update for a look-ahead plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    period_start: date | None = None
    period_end: date | None = None
    window_weeks: int | None = Field(default=None, ge=1, le=24)
    generated_at: datetime | None = None
    status: str | None = Field(default=None, pattern=_LOOK_AHEAD_STATUS)


class LookAheadResponse(BaseModel):
    """Look-ahead plan returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_schedule_id: UUID
    period_start: date
    period_end: date
    window_weeks: int = 6
    generated_at: datetime | None = None
    status: str = "draft"
    created_at: datetime
    updated_at: datetime


# ── Constraint ─────────────────────────────────────────────────────────────


class ConstraintCreate(BaseModel):
    """Create a constraint blocking a task."""

    model_config = ConfigDict(str_strip_whitespace=True)

    look_ahead_id: UUID | None = None
    task_ref: UUID
    constraint_type: str = Field(..., pattern=_CONSTRAINT_TYPE)
    description: str = ""
    owner_user_id: UUID | None = None
    target_clear_date: date | None = None
    status: str = Field(default="open", pattern=_CONSTRAINT_STATUS)


class ConstraintUpdate(BaseModel):
    """Patch update for a constraint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    look_ahead_id: UUID | None = None
    constraint_type: str | None = Field(default=None, pattern=_CONSTRAINT_TYPE)
    description: str | None = None
    owner_user_id: UUID | None = None
    target_clear_date: date | None = None
    cleared_at: datetime | None = None
    cleared_by: UUID | None = None
    status: str | None = Field(default=None, pattern=_CONSTRAINT_STATUS)


class ConstraintResponse(BaseModel):
    """Constraint returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    look_ahead_id: UUID | None = None
    task_ref: UUID
    constraint_type: str
    description: str = ""
    owner_user_id: UUID | None = None
    target_clear_date: date | None = None
    cleared_at: datetime | None = None
    cleared_by: UUID | None = None
    status: str = "open"
    created_at: datetime
    updated_at: datetime


# ── WeeklyWorkPlan ─────────────────────────────────────────────────────────


class WeeklyWorkPlanCreate(BaseModel):
    """Create a weekly work plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    master_schedule_id: UUID
    week_start_date: date
    week_end_date: date
    facilitator_id: UUID | None = None
    status: str = Field(default="draft", pattern=_WEEKLY_STATUS)
    notes: str = ""


class WeeklyWorkPlanUpdate(BaseModel):
    """Patch update for a weekly work plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    week_start_date: date | None = None
    week_end_date: date | None = None
    facilitator_id: UUID | None = None
    status: str | None = Field(default=None, pattern=_WEEKLY_STATUS)
    notes: str | None = None


class WeeklyWorkPlanResponse(BaseModel):
    """Weekly work plan returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_schedule_id: UUID
    week_start_date: date
    week_end_date: date
    generated_at: datetime | None = None
    facilitator_id: UUID | None = None
    status: str = "draft"
    ppc_percent: Decimal | None = None
    notes: str = ""
    created_at: datetime
    updated_at: datetime


# ── Commitment ─────────────────────────────────────────────────────────────


class CommitmentCreate(BaseModel):
    """Create a commitment (promise) for a weekly work plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    week_plan_id: UUID
    task_ref: UUID
    worker_or_crew: str = ""
    promised_qty: Decimal = Decimal("0")
    unit: str = ""
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str = Field(default="planned", pattern=_COMMITMENT_STATUS)
    made_by_user_id: UUID | None = None
    made_at: datetime | None = None


class CommitmentUpdate(BaseModel):
    """Patch update for a commitment."""

    model_config = ConfigDict(str_strip_whitespace=True)

    worker_or_crew: str | None = None
    promised_qty: Decimal | None = None
    unit: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str | None = Field(default=None, pattern=_COMMITMENT_STATUS)
    actual_qty: Decimal | None = None
    completed_at: datetime | None = None


class CommitmentResponse(BaseModel):
    """Commitment returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    week_plan_id: UUID
    task_ref: UUID
    worker_or_crew: str = ""
    promised_qty: Decimal = Decimal("0")
    unit: str = ""
    planned_start: date | None = None
    planned_finish: date | None = None
    status: str = "planned"
    made_by_user_id: UUID | None = None
    made_at: datetime | None = None
    completed_at: datetime | None = None
    actual_qty: Decimal | None = None
    created_at: datetime
    updated_at: datetime


# ── ReasonForNonCompletion ─────────────────────────────────────────────────


class RNCCreate(BaseModel):
    """Record a reason a commitment was not completed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    commitment_id: UUID
    category: str = Field(..., pattern=_RNC_CATEGORY)
    description: str = ""
    recorded_at: datetime | None = None
    root_cause_notes: str = ""


class RNCUpdate(BaseModel):
    """Patch update for an RNC."""

    model_config = ConfigDict(str_strip_whitespace=True)

    category: str | None = Field(default=None, pattern=_RNC_CATEGORY)
    description: str | None = None
    root_cause_notes: str | None = None


class RNCResponse(BaseModel):
    """RNC returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    commitment_id: UUID
    category: str
    description: str = ""
    recorded_at: datetime | None = None
    recorded_by: UUID | None = None
    root_cause_notes: str = ""
    created_at: datetime
    updated_at: datetime


# ── Baseline ───────────────────────────────────────────────────────────────


class BaselineCreate(BaseModel):
    """Create a baseline by capturing the current schedule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    master_schedule_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    snapshot: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    status: str = Field(default="active", pattern=_BASELINE_STATUS)


class BaselineUpdate(BaseModel):
    """Patch update for a baseline."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: str | None = Field(default=None, pattern=_BASELINE_STATUS)


class BaselineResponse(BaseModel):
    """Baseline returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_schedule_id: UUID
    name: str
    captured_at: datetime | None = None
    captured_by: UUID | None = None
    snapshot: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    status: str = "active"
    created_at: datetime
    updated_at: datetime


# ── BaselineDelta ──────────────────────────────────────────────────────────


class BaselineDeltaEntry(BaseModel):
    """One row in the baseline-vs-current variance comparison."""

    task_ref: UUID
    planned_start_baseline: date | None = None
    planned_start_current: date | None = None
    planned_finish_baseline: date | None = None
    planned_finish_current: date | None = None
    schedule_variance_days: int = 0
    # Carried through from the snapshot row when present (e.g. phase plans
    # captured via the front-end's ``captureBaseline`` helper include the
    # phase name). Lets the UI render "Foundation +5d" instead of a raw
    # UUID. Optional + tolerant so legacy snapshots without ``name`` keep
    # validating cleanly.
    name: str | None = None


class BaselineDeltaResponse(BaseModel):
    """Result of a baseline delta computation."""

    baseline_id: UUID
    current_master_id: UUID
    entries: list[BaselineDeltaEntry] = Field(default_factory=list)
    total_tasks: int = 0
    delayed_tasks: int = 0
    accelerated_tasks: int = 0


# ── Calendar ───────────────────────────────────────────────────────────────


class CalendarCreate(BaseModel):
    """Create a working calendar."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    work_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    work_hours_per_day: Decimal = Decimal("8")
    holidays: list[str] = Field(default_factory=list)
    special_shifts: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class CalendarUpdate(BaseModel):
    """Patch update for a calendar."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    work_days: list[int] | None = None
    work_hours_per_day: Decimal | None = None
    holidays: list[str] | None = None
    special_shifts: dict[str, Any] | None = None
    is_default: bool | None = None


class CalendarResponse(BaseModel):
    """Calendar returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    work_days: list[int] = Field(default_factory=list)
    work_hours_per_day: Decimal = Decimal("8")
    holidays: list[str] = Field(default_factory=list)
    special_shifts: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


# ── Aggregate / dashboard responses ────────────────────────────────────────


class PPCResponse(BaseModel):
    """Percent Plan Complete result for one week or aggregate."""

    week_start_date: date | None = None
    total_commitments: int = 0
    completed_commitments: int = 0
    ppc_percent: Decimal = Decimal("0")


class RNCParetoResponse(BaseModel):
    """RNC pareto distribution by category."""

    period_start: date
    period_end: date
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0


class LPSDashboardResponse(BaseModel):
    """Aggregated LPS dashboard for one project."""

    project_id: UUID
    ppc_trend: list[PPCResponse] = Field(default_factory=list)
    open_constraints: int = 0
    constraints_by_type: dict[str, int] = Field(default_factory=dict)
    rnc_pareto: dict[str, int] = Field(default_factory=dict)
    active_master_schedules: int = 0
    active_baselines: int = 0
    current_week_commitments: int = 0


# ── CPM / EVM / TIA ────────────────────────────────────────────────────────


class CPMActivityInput(BaseModel):
    """One activity for the /cpm endpoint.

    ``predecessors`` is a list of activity ids that must finish before this
    activity can start (FS relationships). Use the top-level
    ``dependencies`` array on :class:`CPMRequest` for cleaner modelling.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(default="", max_length=255)
    duration: int = Field(default=0, ge=0)
    predecessors: list[str] = Field(default_factory=list)


class CPMDependencyInput(BaseModel):
    """One FS edge between two activities."""

    model_config = ConfigDict(str_strip_whitespace=True)

    predecessor: str
    successor: str


class CPMRequest(BaseModel):
    """Payload for /cpm - runs forward + backward pass."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activities: list[CPMActivityInput]
    dependencies: list[CPMDependencyInput] | None = None


class CPMActivityResult(BaseModel):
    """Per-activity CPM result."""

    id: str
    es: int = 0
    ef: int = 0
    ls: int = 0
    lf: int = 0
    total_float: int = 0
    free_float: int = 0
    is_critical: bool = False
    duration: int = 0


class CPMResponse(BaseModel):
    """Response from /cpm - per-activity schedule + project finish."""

    project_finish_workday: int = 0
    critical_path_count: int = 0
    activities: list[CPMActivityResult] = Field(default_factory=list)


class TIARequest(BaseModel):
    """Payload for /tia - time-impact-analysis."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activities: list[CPMActivityInput]
    dependencies: list[CPMDependencyInput] | None = None
    impacted_activity_id: str
    delay_days: int = Field(..., ge=0)


class TIAResponse(BaseModel):
    """Response from /tia - schedule slip + critical-path drift."""

    original_finish_workday: int = 0
    impacted_finish_workday: int = 0
    delta_days: int = 0
    newly_critical_activity_ids: list[str] = Field(default_factory=list)
    no_longer_critical_activity_ids: list[str] = Field(default_factory=list)


class EVMActivityInput(BaseModel):
    """One activity for the /evm endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=80)
    budget_at_completion: Decimal = Decimal("0")
    percent_complete: Decimal = Decimal("0")
    actual_cost: Decimal = Decimal("0")
    planned_start_workday: int = 0
    planned_finish_workday: int = 0


class EVMRequest(BaseModel):
    """Payload for /evm - earned value computation at a given workday."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activities: list[EVMActivityInput]
    today_workday: int = Field(..., ge=0)


class EVMResponse(BaseModel):
    """Response from /evm - full EVM dashboard."""

    bac: Decimal = Decimal("0")
    pv: Decimal = Decimal("0")
    ev: Decimal = Decimal("0")
    ac: Decimal = Decimal("0")
    spi: Decimal = Decimal("0")
    cpi: Decimal = Decimal("0")
    eac: Decimal = Decimal("0")
    etc: Decimal = Decimal("0")
    vac: Decimal = Decimal("0")
    sv: Decimal = Decimal("0")
    cv: Decimal = Decimal("0")


class RNCParetoRow(BaseModel):
    """One row in the sorted Pareto chart."""

    category: str
    count: int = 0
    percent: float = 0.0
    cum_percent: float = 0.0


class RNCParetoSortedResponse(BaseModel):
    """Response for the sorted Pareto endpoint."""

    period_start: date
    period_end: date
    rows: list[RNCParetoRow] = Field(default_factory=list)
    total: int = 0


class ConstraintReadinessBlocker(BaseModel):
    """One open constraint blocking a task."""

    id: str
    type: str
    description: str = ""
    owner_user_id: str | None = None
    target_clear_date: str | None = None


class ConstraintReadinessResponse(BaseModel):
    """Per-task readiness summary for a Look-Ahead screen."""

    task_ref: str
    is_ready: bool = True
    open_count: int = 0
    blockers: list[ConstraintReadinessBlocker] = Field(default_factory=list)


# ── CPM Slice 1 - persisted compute + leveling + weekly commitments ────────


class CPMComputeSummary(BaseModel):
    """Summary returned by ``POST /schedule-advanced/{schedule_id}/compute-cpm``.

    The per-activity ES/EF/LS/LF/total_float/is_critical values are written
    back onto the schedule's :class:`Activity` rows; only the aggregate
    summary travels over the wire.
    """

    schedule_id: UUID
    critical_path: list[UUID] = Field(default_factory=list)
    project_duration_days: int = 0
    num_critical: int = 0
    num_activities: int = 0


class LevelResourcesRequest(BaseModel):
    """Body for ``POST /schedule-advanced/{schedule_id}/level-resources``.

    ``resource_limits`` is a mapping of resource code → max concurrent
    units. Resources omitted from the dict are unconstrained.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    resource_limits: dict[str, int] = Field(default_factory=dict)


class LevelResourcesShift(BaseModel):
    """One activity-shift row produced by resource leveling."""

    activity_id: UUID
    original_es: int = 0
    shifted_es: int = 0
    delta_days: int = 0


class LevelResourcesResponse(BaseModel):
    """Response for /level-resources - only changed activities listed."""

    schedule_id: UUID
    shifts: list[LevelResourcesShift] = Field(default_factory=list)
    num_shifted: int = 0


class WeeklyCommitmentCreate(BaseModel):
    """Body for ``POST /schedule-advanced/{schedule_id}/commitments``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activity_id: UUID
    week_start: date
    planned_complete_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    actual_complete_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class WeeklyCommitmentResponse(BaseModel):
    """Stored weekly commitment row with auto-computed PPC."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    activity_id: UUID
    week_start: date
    committed_by: UUID | None = None
    planned_complete_pct: Decimal = Decimal("0")
    actual_complete_pct: Decimal = Decimal("0")
    ppc: Decimal = Decimal("0")


class PPCWeeklyResponse(BaseModel):
    """Schedule-level PPC roll-up for a single week."""

    schedule_id: UUID
    week_start: date
    num_commitments: int = 0
    avg_planned_pct: Decimal = Decimal("0")
    avg_actual_pct: Decimal = Decimal("0")
    ppc: Decimal = Decimal("0")


# ── Takt / line-of-balance scheduling ──────────────────────────────────────

_TAKT_STATUS = r"^(draft|active|completed|archived)$"
_TAKT_ACTIVITY_STATUS = r"^(planned|in_progress|completed)$"


class LocationCreate(BaseModel):
    """One location in a takt schedule's location sequence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    sequence_order: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    work_area_sqm: Decimal | None = None


class LocationResponse(BaseModel):
    """Location returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    takt_schedule_id: UUID
    sequence_order: int
    name: str
    description: str = ""
    work_area_sqm: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class TaktScheduleCreate(BaseModel):
    """Create a takt schedule with its location sequence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    master_schedule_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    target_cycle_days: int = Field(default=7, ge=1, le=365)
    takt_rhythm_tolerance_days: int = Field(default=1, ge=0, le=60)
    locations: list[LocationCreate] = Field(default_factory=list)


class TaktScheduleUpdate(BaseModel):
    """Patch update for a takt schedule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    target_cycle_days: int | None = Field(default=None, ge=1, le=365)
    takt_rhythm_tolerance_days: int | None = Field(default=None, ge=0, le=60)
    status: str | None = Field(default=None, pattern=_TAKT_STATUS)


class TaktScheduleResponse(BaseModel):
    """Takt schedule returned from the API (with nested locations)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_schedule_id: UUID
    name: str
    description: str = ""
    target_cycle_days: int = 7
    takt_rhythm_tolerance_days: int = 1
    location_sequence_count: int = 0
    status: str = "draft"
    created_by: UUID | None = None
    locations: list[LocationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TaktActivityCreate(BaseModel):
    """One trade activity in a takt schedule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    activity_code: str = Field(default="", max_length=50)
    sequence_order: int = Field(default=1, ge=1)
    planned_cycle_duration_days: int = Field(..., ge=1, le=365)
    crew_size: int = Field(default=1, ge=1, le=10_000)
    crew_skill_codes: list[str] = Field(default_factory=list)
    buffer_days_before: int = Field(default=0, ge=0, le=365)
    sequence_predecessor_activity_id: UUID | None = None


class TaktActivityImport(BaseModel):
    """Bulk-import payload for takt activities."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activities: list[TaktActivityCreate] = Field(default_factory=list)


class TaktActivityUpdate(BaseModel):
    """Patch update for a takt activity."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    activity_code: str | None = Field(default=None, max_length=50)
    sequence_order: int | None = Field(default=None, ge=1)
    planned_cycle_duration_days: int | None = Field(default=None, ge=1, le=365)
    crew_size: int | None = Field(default=None, ge=1, le=10_000)
    crew_skill_codes: list[str] | None = None
    buffer_days_before: int | None = Field(default=None, ge=0, le=365)
    actual_cycle_duration_days: Decimal | None = None
    status: str | None = Field(default=None, pattern=_TAKT_ACTIVITY_STATUS)


class TaktActivityResponse(BaseModel):
    """Takt activity returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    takt_schedule_id: UUID
    name: str
    activity_code: str = ""
    sequence_order: int = 1
    planned_cycle_duration_days: int = 1
    crew_size: int = 1
    crew_skill_codes: list[str] = Field(default_factory=list)
    buffer_days_before: int = 0
    sequence_predecessor_activity_id: UUID | None = None
    status: str = "planned"
    actual_cycle_duration_days: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class LineOfBalanceBar(BaseModel):
    """One diagonal bar on the line-of-balance chart.

    ``start_day`` / ``end_day`` are 0-based working-day indices relative to
    the takt schedule's day-zero. The chart plots the bar from
    ``(start_day, location)`` to ``(end_day, next location)`` - the diagonal
    that gives line-of-balance its name.
    """

    activity_id: UUID
    location_id: UUID
    activity_name: str
    location_name: str
    sequence_order: int
    start_day: int
    end_day: int
    crew_size: int
    is_critical: bool = False
    has_rhythm_break: bool = False


class TaktViolation(BaseModel):
    """A detected takt feasibility / rhythm issue."""

    activity_id: UUID
    location_id: UUID | None = None
    activity_name: str = ""
    location_name: str = ""
    violation_type: str  # "rhythm_break" | "overlap" | "buffer_infeasible"
    deviation_days: float = 0.0
    severity: str  # "warning" | "error"
    message: str


class LineOfBalanceResponse(BaseModel):
    """Computed line-of-balance geometry + violations + critical path."""

    takt_schedule_id: UUID
    total_makespan_days: int = 0
    bars: list[LineOfBalanceBar] = Field(default_factory=list)
    violations: list[TaktViolation] = Field(default_factory=list)
    critical_path: list[UUID] = Field(default_factory=list)
    total_locations: int = 0
    total_activities: int = 0
    average_cycle_days: float = 0.0
