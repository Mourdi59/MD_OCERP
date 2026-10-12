# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness and decision rules, pure.

Nothing here touches a session, a clock or a request. The service reads the
rows, turns them into the frozen values below, asks this module what blocks a
gate and whether a proposed decision is admissible, and only then writes. That
split is what lets every one of the fifteen behaviours of the specification be
a plain unit test with a case that must fail when the rule is removed.

Codes returned here are stable identifiers. Each one is also a message key,
``governance.errors.<code>`` in ``messages/en.json``, so the API can hand the
code to a client and the client can render it in the reader's language.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

OUTCOMES: tuple[str, ...] = ("go", "go_with_conditions", "hold", "recycle", "stop")
CHECK_STATUSES: tuple[str, ...] = ("not_assessed", "ready", "ready_with_risks", "not_ready", "not_applicable")
CONDITION_STATUSES: tuple[str, ...] = ("open", "cleared", "waived", "overdue")
CONDITION_SEVERITIES: tuple[str, ...] = ("critical", "essential", "recommended")
RAG_VALUES: tuple[str, ...] = ("", "red", "amber", "green")

# Document states in which a required frame document counts as approvable at a
# gate: submitted for it, or already approved at an earlier one.
_DOC_READY_STATES = frozenset({"in_review", "approved_at_gate", "binding"})
_DOC_FROZEN_STATES = frozenset({"approved_at_gate", "binding", "superseded"})
_CHECK_PASSING = frozenset({"ready", "ready_with_risks"})
_UNDECIDED_GATE_STATES = frozenset({"not_started", "in_preparation", "in_review", "on_hold"})

# The blockers a go with conditions may lift by naming the area as proceeding at
# risk: gaps in the area's readiness. A stale check is not one of them, because
# nobody has attested the document as it now stands.
PROCEED_AT_RISK_LIFTABLE: frozenset[str] = frozenset({"area_not_ready", "evidence_not_met"})

ALL_CODES: tuple[str, ...] = (
    "unknown_outcome",
    "gate_not_in_review",
    "gate_not_decided",
    "rationale_required",
    "required_document_not_approved",
    "area_without_owner",
    "area_not_ready",
    "evidence_not_met",
    "unknown_evidence_not_acknowledged",
    "unknown_criterion",
    "check_stale",
    "condition_overdue",
    "conditions_required",
    "conditions_not_allowed",
    "condition_text_required",
    "condition_unknown_area",
    "waiver_needs_rationale",
    "not_applicable_needs_rationale",
    "not_applicable_not_accepted",
    "decider_not_entitled",
    "decider_is_area_owner",
    "hold_needs_resume_date",
    "proceed_at_risk_needs_conditions",
    "proceed_at_risk_area_not_blocking",
    "project_stopped",
    "document_read_only",
    "binding_requires_change_request",
    "phase_mapping_missing",
    "phase_mapping_unknown_target",
    "gate_historic",
    "gate_not_on_hold",
    "later_gate_active",
    "invalid_transition",
    "gate_out_of_order",
    "model_unchanged",
    "condition_not_open",
    "not_condition_owner",
    "route_needs_more_approvals",
    "route_not_pinnable",
    "no_change_route",
    "area_retired",
    "pack_catalogue_invalid",
    "settings_frozen_in_review",
    "null_not_allowed",
    "activity_not_in_project",
    "target_date_owned_by_schedule",
    # Refusals of the service and the catalogue store that no rule of this module computes.
    "area_not_found",
    "catalogue_code_taken",
    "catalogue_invalid",
    "catalogue_retired",
    "change_request_not_open",
    "concurrent_decision",
    "condition_not_found",
    "container_not_in_project",
    "document_exists",
    "document_not_binding",
    "document_not_found",
    "gate_not_found",
    "invalid_status",
    "model_exists",
    "model_missing",
    "no_decision_route",
    "no_pending_revision",
    "not_area_owner",
    "owner_not_project_member",
    "route_not_at_final_step",
    "route_not_pending",
    "unknown_catalogue",
    "unknown_document_type",
)


# ── Inputs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AreaState:
    """One management area of the project as the evaluator needs it."""

    code: str
    owner_user_id: str | None
    deputy_user_id: str | None = None
    applicable: bool = True
    na_rationale: str = ""


@dataclass(frozen=True)
class DocumentState:
    """A frame document and the CDE revision facts read for it."""

    id: str
    area_code: str
    doc_type: str
    required: bool
    status: str
    container_id: str | None
    current_revision_id: str | None
    current_content_hash: str | None = None
    bound_revision_id: str | None = None
    read_only: bool = False
    bound_content_hash: str | None = None


@dataclass(frozen=True)
class CheckState:
    """The readiness attestation of one area for the current attempt."""

    area_code: str
    status: str
    confirmed_by: str | None = None
    confirmed_revisions: Mapping[str, str] = field(default_factory=dict)
    stale: bool = False
    na_rationale: str = ""
    rag: str = ""
    note: str = ""
    confirmed_at: str | None = None
    criteria: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConditionState:
    """A condition attached to an earlier decision."""

    id: str
    gate_code: str
    area_code: str | None
    status: str
    due_date: date | None = None
    severity: str = "essential"
    document_type: str | None = None


@dataclass(frozen=True)
class EvidenceState:
    """One readiness evidence item a registered provider reported for an area."""

    area_code: str
    code: str
    state: str  # met | not_met | unknown | warning
    blocking: bool = False
    provider: str = ""


@dataclass(frozen=True)
class GateContext:
    """Everything that decides whether one gate attempt can pass."""

    gate_code: str
    gate_status: str
    areas: Sequence[AreaState]
    documents: Sequence[DocumentState]
    checks: Sequence[CheckState]
    prior_conditions: Sequence[ConditionState]
    today: date
    model_stopped: bool = False
    four_eyes: bool = True
    evidence: Sequence[EvidenceState] = ()


@dataclass(frozen=True)
class ProposedCondition:
    """A condition the decider attaches to a go-with-conditions decision."""

    area_code: str | None
    document_type: str | None
    text: str
    owner_user_id: str | None
    due_date: date | None = None
    severity: str = "essential"


@dataclass(frozen=True)
class DecisionRequest:
    """What the decider asks for."""

    outcome: str
    rationale: str
    decider_id: str
    conditions: Sequence[ProposedCondition] = ()
    proceed_at_risk_areas: Sequence[str] = ()
    accepted_not_applicable: Sequence[str] = ()
    hold_resume_date: date | None = None
    # (area_code, evidence code) of every unknown item the decider has seen.
    acknowledged_evidence: Sequence[tuple[str, str]] = ()


@dataclass(frozen=True)
class Violation:
    """A blocker on a gate, or a reason a decision is refused."""

    code: str
    area_code: str | None = None
    document_type: str | None = None
    ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form used by the API and the snapshot."""
        return {
            "code": self.code,
            "message_key": f"governance.errors.{self.code}",
            "area_code": self.area_code,
            "document_type": self.document_type,
            "ref": self.ref,
        }


Blocker = Violation


@dataclass(frozen=True)
class DecisionEffects:
    """What a decision outcome does to the gate, the project and the route."""

    next_gate_status: str
    advance_phase: bool = False
    approve_documents: bool = False
    mark_checks_stale: bool = False
    new_attempt: bool = False
    stop_project: bool = False
    # approved / rejected: submit that decision on the route instance;
    # cancel: cancel the pending instance; None: leave it.
    route_action: str | None = None


# ── Documents ───────────────────────────────────────────────────────────────


def revision_in_force(doc: DocumentState) -> str | None:
    """The revision that counts: the bound one once approved, else the current one."""
    if doc.status in _DOC_FROZEN_STATES and doc.bound_revision_id:
        return doc.bound_revision_id
    return doc.current_revision_id


def pending_revision(doc: DocumentState) -> str | None:
    """A newer CDE revision of a binding document that is not yet in force."""
    if doc.status != "binding" or not doc.current_revision_id:
        return None
    if doc.current_revision_id == doc.bound_revision_id:
        return None
    return doc.current_revision_id


def binding_document_changed(doc: DocumentState) -> bool:
    """Whether a binding document has a revision waiting for change control."""
    return pending_revision(doc) is not None


def document_edit_violation(doc: DocumentState, action: str) -> str | None:
    """Why ``action`` (attach, submit, return) is refused on ``doc``, or None."""
    if doc.read_only:
        return "document_read_only"
    if doc.status in _DOC_FROZEN_STATES and action in {"attach", "submit", "return"}:
        return "binding_requires_change_request"
    return None


def documents_to_freeze(docs: Iterable[DocumentState]) -> tuple[str, ...]:
    """Documents a stop decision makes read-only: every one still in the frame.

    Binding documents are frozen too, so no change request can move a stopped
    project's baseline. A superseded document is already out of the frame.
    """
    return tuple(d.id for d in docs if d.status != "superseded" and not d.read_only)


def _document_ready(doc: DocumentState) -> bool:
    if doc.status not in _DOC_READY_STATES:
        return False
    if doc.status in {"approved_at_gate", "binding"}:
        return bool(doc.bound_revision_id)
    return bool(doc.container_id and doc.current_revision_id)


# ── Checks ──────────────────────────────────────────────────────────────────


def check_is_stale(check: CheckState, docs: Iterable[DocumentState]) -> bool:
    """A check is stale when flagged, or when a document it confirmed has moved on."""
    if check.stale:
        return True
    by_id = {d.id: d for d in docs}
    for doc_id, revision_id in check.confirmed_revisions.items():
        doc = by_id.get(doc_id)
        if doc is not None and revision_in_force(doc) != revision_id:
            return True
    return False


def reset_checks_for_owner_change(checks: Iterable[CheckState], *, area_code: str) -> tuple[CheckState, ...]:
    """A new owner has to attest again; other areas keep their attestations."""
    return tuple(
        replace(c, status="not_assessed", confirmed_by=None, confirmed_at=None, confirmed_revisions={}, stale=False)
        if c.area_code == area_code
        else c
        for c in checks
    )


def criterion_tick(
    ticks: Mapping[str, Any], code: str, *, met: bool, note: str, actor_id: str, at: str
) -> dict[str, dict[str, Any]]:
    """The ticks of a check after one criterion was ticked or unticked; the input is left alone.

    Taking a tick back is recorded like setting it, with who and when, so the
    list never shows an unticked line that silently lost its history.
    """
    out = {k: dict(v) for k, v in ticks.items()}
    out[code] = {"met": bool(met), "note": (note or "").strip(), "by": actor_id, "at": at}
    return out


def criteria_rows(codes: Iterable[str], ticks: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The checklist of one area at one gate: every criterion of the catalogue, ticked or not."""
    rows = []
    for code in codes:
        tick = ticks.get(code) or {}
        rows.append(
            {
                "code": code,
                "met": bool(tick.get("met")),
                "note": tick.get("note") or "",
                "ticked_by": tick.get("by"),
                "ticked_at": tick.get("at"),
            }
        )
    return rows


def gate_accepts_readiness_reset(gate_status: str) -> bool:
    """Only an undecided gate has its readiness reset; a decision stays as taken."""
    return gate_status in _UNDECIDED_GATE_STATES


def next_attempt_checks(checks: Iterable[CheckState], *, carry_stale: bool) -> tuple[CheckState, ...]:
    """The checks a new attempt starts with: copies, stale when asked."""
    return tuple(replace(c, stale=True) if carry_stale else c for c in checks)


def next_attempt_number(attempt_no: int) -> int:
    """Attempts are numbered from one and never reused."""
    return attempt_no + 1


# ── Conditions ──────────────────────────────────────────────────────────────


def condition_status(cond: ConditionState, today: date) -> str:
    """Effective status: an open condition past its due date is overdue."""
    if cond.status in {"cleared", "waived"}:
        return cond.status
    if cond.due_date is not None and cond.due_date < today:
        return "overdue"
    return "open"


def conditions_to_escalate(conds: Iterable[ConditionState], today: date) -> list[ConditionState]:
    """Open conditions that are overdue and must be raised to the decider."""
    return [c for c in conds if condition_status(c, today) == "overdue"]


def waiver_violation(rationale: str) -> str | None:
    """A waiver without a written reason is refused."""
    return None if (rationale or "").strip() else "waiver_needs_rationale"


def not_applicable_violation(rationale: str) -> str | None:
    """Marking an area or a check not applicable needs a written reason."""
    return None if (rationale or "").strip() else "not_applicable_needs_rationale"


def condition_clear_violation(status: str, owner_user_id: str | None, *, actor_id: str, is_manager: bool) -> str | None:
    """Clearing is for the person the condition was given to, or a manager."""
    if status not in {"open", "overdue"}:
        return "condition_not_open"
    if not is_manager and (not owner_user_id or str(owner_user_id) != str(actor_id)):
        return "not_condition_owner"
    return None


def authority_violation(actor_id: str, *, decided_by: str | None, route_entitled: bool) -> str | None:
    """Who may revisit a decision: its decider, or a user the gate route entitles.

    Reopening or resuming a gate, waiving a condition and adding one all change
    what a decision meant, so the permission to decide is not enough on its own.
    """
    if decided_by and str(decided_by) == str(actor_id):
        return None
    return None if route_entitled else "decider_not_entitled"


def condition_waive_violation(
    status: str,
    *,
    actor_id: str,
    decided_by: str | None,
    route_entitled: bool,
    four_eyes: bool,
    areas: Iterable[AreaState],
    area_code: str | None,
) -> str | None:
    """A waiver needs an open condition, authority, and under four-eyes a second pair of eyes.

    The owner or deputy of the area the condition is on may not waive it; a
    condition on no area concerns every area.
    """
    if status not in {"open", "overdue"}:
        return "condition_not_open"
    code = authority_violation(actor_id, decided_by=decided_by, route_entitled=route_entitled)
    if code:
        return code
    if four_eyes:
        concerned = [a for a in areas if area_code is None or a.code == area_code]
        if str(actor_id) in area_owner_ids(concerned):
            return "decider_is_area_owner"
    return None


def preparation_violation(gate_status: str, *, historic: bool, model_stopped: bool) -> str | None:
    """Preparation starts once, on a gate nobody has touched yet."""
    if historic:
        return "gate_historic"
    if model_stopped:
        return "project_stopped"
    return None if gate_status == "not_started" else "invalid_transition"


def resume_violation(gate_status: str, *, historic: bool, model_stopped: bool) -> str | None:
    """Only a held gate is resumed."""
    if historic:
        return "gate_historic"
    if model_stopped:
        return "project_stopped"
    return None if gate_status == "on_hold" else "gate_not_on_hold"


def reopen_violation(
    gate_status: str, rationale: str, *, historic: bool = False, later_gate_statuses: Iterable[str] = ()
) -> str | None:
    """Only a decided gate of the pinned model is reopened, with a reason, and never behind a later gate."""
    if historic:
        return "gate_historic"
    if gate_status != "decided":
        return "gate_not_decided"
    if not (rationale or "").strip():
        return "rationale_required"
    # A later gate counts from the moment it is submitted. Its preparation can be opened by
    # anyone who may edit and cannot be taken back, so it must not lock the gate before it.
    if any(s in GATE_UNDER_DECISION or s == "decided" for s in later_gate_statuses):
        return "later_gate_active"
    return None


GATE_UNDER_DECISION: tuple[str, ...] = ("in_review", "on_hold")


def settings_freeze_violation(gate_statuses: Iterable[str]) -> str | None:
    """What decides who may decide a gate does not change while a gate is being decided.

    Four-eyes and the applicability of an area are inputs of the decision. If
    they could be changed with a gate in review or on hold, a manager could
    switch a rule off, decide, and switch it back.
    """
    return "settings_frozen_in_review" if any(s in GATE_UNDER_DECISION for s in gate_statuses) else None


def reopen_rewinds_phase(last_outcome: str) -> bool:
    """A reopened gate takes the phase back exactly when its decision had advanced it."""
    return last_outcome in OUTCOMES and decision_effects(last_outcome).advance_phase


# ── Entitlement ─────────────────────────────────────────────────────────────


def entitlement_violation(
    decider_id: str,
    *,
    entitled_user_ids: frozenset[str] | None,
    role_satisfies: bool,
) -> str | None:
    """Route entitlement: a named user set, or a role check when the step is role-based."""
    if entitled_user_ids is None:
        return None if role_satisfies else "decider_not_entitled"
    return None if decider_id in entitled_user_ids else "decider_not_entitled"


def area_owner_ids(areas: Iterable[AreaState]) -> frozenset[str]:
    """Owners and deputies of the applicable areas: the people four-eyes keeps out."""
    ids: set[str] = set()
    for area in areas:
        if not area.applicable:
            continue
        for uid in (area.owner_user_id, area.deputy_user_id):
            if uid:
                ids.add(str(uid))
    return frozenset(ids)


def four_eyes_violation(ctx: GateContext, decider_id: str) -> bool:
    """Under four-eyes, an owner or deputy of an applicable area may not decide the gate."""
    return bool(ctx.four_eyes) and str(decider_id) in area_owner_ids(ctx.areas)


def decision_refusal(violations: Sequence[Violation]) -> tuple[str, int]:
    """The error code and HTTP status a list of decision violations is answered with."""
    if any(v.code == "decider_is_area_owner" for v in violations):
        return "decider_is_area_owner", 403
    return violations[0].code, 422


# ── Gate readiness ──────────────────────────────────────────────────────────


def gate_blockers(ctx: GateContext, *, accepted_not_applicable: Iterable[str] = ()) -> list[Violation]:
    """Everything that stops a go on this gate attempt, area by area."""
    accepted = set(accepted_not_applicable)
    out: list[Violation] = []
    if ctx.model_stopped:
        out.append(Violation("project_stopped"))
    checks = {c.area_code: c for c in ctx.checks}
    for area in ctx.areas:
        if not area.applicable:
            if not_applicable_violation(area.na_rationale):
                out.append(Violation("not_applicable_needs_rationale", area_code=area.code))
            elif area.code not in accepted:
                out.append(Violation("not_applicable_not_accepted", area_code=area.code))
            continue
        if not area.owner_user_id:
            out.append(Violation("area_without_owner", area_code=area.code))
        for doc in ctx.documents:
            if doc.area_code == area.code and doc.required and not _document_ready(doc):
                out.append(
                    Violation(
                        "required_document_not_approved", area_code=area.code, document_type=doc.doc_type, ref=doc.id
                    )
                )
        for item in ctx.evidence:
            # Only a blocking provider's explicit not_met blocks; unknown (provider
            # failure) is shown but never invents a blocker.
            if item.area_code == area.code and item.blocking and item.state == "not_met":
                out.append(Violation("evidence_not_met", area_code=area.code, ref=item.code))
        check = checks.get(area.code)
        if check is None or check.status in {"not_assessed", "not_ready"}:
            out.append(Violation("area_not_ready", area_code=area.code))
        elif check.status == "not_applicable":
            if not_applicable_violation(check.na_rationale):
                out.append(Violation("not_applicable_needs_rationale", area_code=area.code))
            elif area.code not in accepted:
                out.append(Violation("not_applicable_not_accepted", area_code=area.code))
        elif check.status in _CHECK_PASSING and check_is_stale(check, ctx.documents):
            out.append(Violation("check_stale", area_code=area.code))
    for cond in ctx.prior_conditions:
        if condition_status(cond, ctx.today) == "overdue":
            out.append(Violation("condition_overdue", area_code=cond.area_code, ref=cond.id))
    return out


def evidence_to_acknowledge(ctx: GateContext) -> list[EvidenceState]:
    """The unknown items of blocking providers a go on this gate has to name.

    Unknown never blocks: a provider that failed, or said nothing about the
    area it is registered for, has not said the area is unready. It is not a
    yes either, so the decider names each item and the record keeps the list.
    An item is one code in one area; the same code in two areas is two items.

    A ``warning`` is named the same way, whoever reports it: the provider says
    the gate may pass by its rule and that something is still outstanding.
    """
    applicable = {a.code for a in ctx.areas if a.applicable}
    return [
        e
        for e in ctx.evidence
        if e.area_code in applicable and (e.state == "warning" or (e.blocking and e.state == "unknown"))
    ]


# ── Decisions ───────────────────────────────────────────────────────────────


def decision_effects(outcome: str) -> DecisionEffects:
    """What each outcome does. Raises ``KeyError`` on an unknown outcome."""
    return {
        "go": DecisionEffects("decided", advance_phase=True, approve_documents=True, route_action="approved"),
        "go_with_conditions": DecisionEffects(
            "decided", advance_phase=True, approve_documents=True, route_action="approved"
        ),
        "hold": DecisionEffects("on_hold", route_action="cancel"),
        "recycle": DecisionEffects("in_preparation", mark_checks_stale=True, new_attempt=True, route_action="rejected"),
        "stop": DecisionEffects("decided", stop_project=True, route_action="rejected"),
    }[outcome]


def validate_decision(ctx: GateContext, req: DecisionRequest) -> list[Violation]:
    """Every reason the proposed decision cannot be recorded; empty means admissible."""
    if req.outcome not in OUTCOMES:
        return [Violation("unknown_outcome", ref=req.outcome)]
    out: list[Violation] = []
    if ctx.gate_status != "in_review":
        out.append(Violation("gate_not_in_review"))
    if req.outcome != "go" and not (req.rationale or "").strip():
        out.append(Violation("rationale_required"))
    if four_eyes_violation(ctx, req.decider_id):
        out.append(Violation("decider_is_area_owner"))

    area_codes = {a.code for a in ctx.areas}
    if req.outcome == "go_with_conditions":
        if not req.conditions:
            out.append(Violation("conditions_required"))
    elif req.conditions:
        out.append(Violation("conditions_not_allowed"))
    for cond in req.conditions:
        if not (cond.text or "").strip():
            out.append(Violation("condition_text_required", area_code=cond.area_code))
        if cond.area_code is not None and cond.area_code not in area_codes:
            out.append(Violation("condition_unknown_area", area_code=cond.area_code))

    if req.outcome == "hold" and (req.hold_resume_date is None or req.hold_resume_date <= ctx.today):
        out.append(Violation("hold_needs_resume_date"))

    at_risk = set(req.proceed_at_risk_areas)
    if at_risk and req.outcome != "go_with_conditions":
        out.append(Violation("proceed_at_risk_needs_conditions"))

    if req.outcome in {"go", "go_with_conditions"}:
        conditional = req.outcome == "go_with_conditions"
        covered_docs = {(c.area_code, c.document_type) for c in req.conditions if c.document_type}
        not_ready_areas: set[str] = set()
        for blocker in gate_blockers(ctx, accepted_not_applicable=req.accepted_not_applicable):
            # Blocking evidence is a readiness gap of the area, liftable the same way.
            if blocker.code in PROCEED_AT_RISK_LIFTABLE:
                not_ready_areas.add(blocker.area_code or "")
                if conditional and blocker.area_code in at_risk:
                    continue
            if (
                blocker.code == "required_document_not_approved"
                and conditional
                and (blocker.area_code, blocker.document_type) in covered_docs
            ):
                continue
            out.append(blocker)
        for code in sorted(at_risk - not_ready_areas):
            out.append(Violation("proceed_at_risk_area_not_blocking", area_code=code))
        # Proceeding at risk answers a known gap. It says nothing about an answer nobody got.
        named = {(area, code) for area, code in req.acknowledged_evidence}
        for item in evidence_to_acknowledge(ctx):
            if (item.area_code, item.code) not in named:
                out.append(Violation("unknown_evidence_not_acknowledged", area_code=item.area_code, ref=item.code))
    return out


# ── Model change ────────────────────────────────────────────────────────────


def validate_phase_mapping(
    *,
    new_phase_codes: Sequence[str],
    mapping: Mapping[str, str],
    current_phase: str | None,
    phases_with_decisions: Iterable[str],
) -> list[Violation]:
    """A model change must say where the current phase and every decided phase go."""
    out: list[Violation] = []
    needed = set(phases_with_decisions)
    if current_phase:
        needed.add(current_phase)
    for phase in sorted(needed):
        if phase not in mapping:
            out.append(Violation("phase_mapping_missing", ref=phase))
    valid = set(new_phase_codes)
    for src, dst in sorted(mapping.items()):
        if dst not in valid:
            out.append(Violation("phase_mapping_unknown_target", ref=f"{src}->{dst}"))
    return out


def gates_kept_on_model_change(decision_counts: Mapping[str, int]) -> set[str]:
    """Gates with at least one decision are history and are never deleted."""
    return {code for code, count in decision_counts.items() if count > 0}


# ── Snapshot and trail ──────────────────────────────────────────────────────


def build_snapshot(ctx: GateContext, req: DecisionRequest) -> dict[str, Any]:
    """The frozen record of what a decision approved: revisions, hashes, checks, areas."""
    return {
        "gate_code": ctx.gate_code,
        "decider_id": str(req.decider_id),
        "four_eyes": bool(ctx.four_eyes),
        "today": ctx.today.isoformat(),
        "areas": [
            {
                "code": a.code,
                "owner_user_id": a.owner_user_id,
                "deputy_user_id": a.deputy_user_id,
                "applicable": a.applicable,
                "na_rationale": a.na_rationale,
            }
            for a in ctx.areas
        ],
        "documents": [
            {
                "document_id": d.id,
                "area_code": d.area_code,
                "doc_type": d.doc_type,
                "status": d.status,
                "container_id": d.container_id,
                "revision_id": revision_in_force(d),
                "content_hash": d.bound_content_hash
                if d.status in _DOC_FROZEN_STATES and d.bound_content_hash
                else d.current_content_hash,
                "required": d.required,
            }
            for d in ctx.documents
        ],
        "checks": [
            {
                "area_code": c.area_code,
                "status": c.status,
                "rag": c.rag,
                "note": c.note,
                "confirmed_by": c.confirmed_by,
                "confirmed_at": c.confirmed_at,
                "confirmed_revisions": dict(c.confirmed_revisions),
                "stale": check_is_stale(c, ctx.documents),
                "na_rationale": c.na_rationale,
                "criteria": {code: dict(tick) for code, tick in c.criteria.items()},
            }
            for c in ctx.checks
        ],
        "blockers": [b.as_dict() for b in gate_blockers(ctx, accepted_not_applicable=req.accepted_not_applicable)],
        "accepted_not_applicable": list(req.accepted_not_applicable),
        "proceed_at_risk_areas": list(req.proceed_at_risk_areas),
        "evidence": [
            {"area_code": e.area_code, "code": e.code, "state": e.state, "blocking": e.blocking, "provider": e.provider}
            for e in ctx.evidence
        ],
        # Only what was unknown when the decision was taken: a name the request carried for an
        # item that had been answered meanwhile is not part of the record.
        "acknowledged_evidence": [
            {"area_code": e.area_code, "code": e.code, "provider": e.provider, "state": e.state}
            for e in evidence_to_acknowledge(ctx)
            if (e.area_code, e.code) in {(area, code) for area, code in req.acknowledged_evidence}
        ],
    }


def trail_rows(decisions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rows of the exportable decision trail; labels as i18n keys, never English."""
    rows: list[dict[str, Any]] = []
    for d in decisions:
        rows.append(
            {
                "gate_code": d.get("gate_code"),
                "attempt_no": d.get("attempt_no"),
                "outcome": d.get("outcome"),
                "outcome_key": f"governance.outcome.{d.get('outcome')}",
                "decided_by": d.get("decided_by"),
                "decided_at": d.get("decided_at"),
                "rationale": d.get("rationale") or "",
                "conditions": len(d.get("conditions") or []),
                "proceed_at_risk_areas": ", ".join(d.get("proceed_at_risk_areas") or []),
            }
        )
    return rows
