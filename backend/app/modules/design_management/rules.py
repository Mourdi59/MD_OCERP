# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design rules as pure functions over plain values, shared by the service and the rule set.

Nothing here reads the database. The service loads rows, turns them into the
small dataclasses below and asks; the validation rules ask the same functions
over the validation payload, so a write-time refusal and a rule finding can
never disagree.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

#: Suitability rank: how far a revision has travelled (ISO 19650 CDE states).
_RANK = {"S0": 0, "S1": 1, "S2": 1, "S3": 2, "S4": 3, "S6": 3, "S7": 3, "A1": 4, "A2": 4, "A3": 4, "A4": 4, "A5": 4}
PUBLISHED = frozenset({"A1", "A2", "A3", "A4", "A5"})
DEFAULT_TARGET = "S4"


def rank(code: str | None) -> int:
    """0 = work in progress, 1-3 shared, 4 published; unknown, archived or empty = -1."""
    return _RANK.get((code or "").upper(), -1)


# ── deliverables (rule 15) ────────────────────────────────────────────────


@dataclass(frozen=True)
class DrawingState:
    container_id: uuid.UUID
    cde_state: str
    suitability_code: str | None
    has_revision: bool = True


def deliverable_state(
    drawings: Sequence[DrawingState], *, planned_count: int, target_suitability: str | None, waived: bool = False
) -> str:
    """The computed state of a design schedule line; never typed except ``waived``."""
    if waived:
        return "waived"
    live = [d for d in drawings if d.cde_state != "archived"]
    if not live or not any(d.has_revision for d in live):
        return "not_started"
    target = rank(target_suitability or DEFAULT_TARGET)
    count_met = len(live) >= max(planned_count, 0)
    if count_met and all(rank(d.suitability_code) >= target for d in live):
        return "accepted"
    if count_met and all(rank(d.suitability_code) >= 1 for d in live):
        return "issued_for_review"
    return "in_progress"


# ── releases and distribution (rules 12-14) ──────────────────────────────


@dataclass(frozen=True)
class RevisionView:
    revision_id: uuid.UUID
    container_id: uuid.UUID
    suitability_code: str | None
    discipline_code: str | None = None
    form_code: str | None = None
    phase_code: str | None = None
    wbs_node_id: uuid.UUID | None = None


@dataclass(frozen=True)
class MatrixRule:
    id: uuid.UUID
    recipient_key: str
    discipline_codes: tuple[str, ...] = ()
    form_codes: tuple[str, ...] = ()
    phase_codes: tuple[str, ...] = ()
    wbs_node_ids: tuple[uuid.UUID, ...] = ()
    min_suitability: str | None = None
    #: Empty = the rule applies to a release of any purpose; set = only to releases of that purpose.
    purpose: str = ""


def release_content_errors(revisions: Iterable[RevisionView], purpose: str) -> list[tuple[uuid.UUID, str]]:
    """Rule 13: no work-in-progress revision; ``for_construction`` needs published (A) codes."""
    out: list[tuple[uuid.UUID, str]] = []
    for r in revisions:
        code = (r.suitability_code or "").upper()
        if rank(code) <= 0:
            out.append((r.revision_id, "release_contains_wip"))
        elif purpose == "for_construction" and code not in PUBLISHED:
            out.append((r.revision_id, "release_needs_published"))
    return out


def _matches(rule: MatrixRule, r: RevisionView) -> bool:
    if rule.discipline_codes and (r.discipline_code or "") not in rule.discipline_codes:
        return False
    if rule.form_codes and (r.form_code or "") not in rule.form_codes:
        return False
    if rule.phase_codes and (r.phase_code or "") not in rule.phase_codes:
        return False
    return not (rule.wbs_node_ids and r.wbs_node_id not in rule.wbs_node_ids)


@dataclass
class RecipientPlan:
    recipient_key: str
    rule_ids: list[uuid.UUID] = field(default_factory=list)
    purpose: str = "for_information"
    revision_ids: list[uuid.UUID] = field(default_factory=list)
    excluded: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    duplicates: list[uuid.UUID] = field(default_factory=list)


def distribution_plan(
    rules: Sequence[MatrixRule],
    revisions: Sequence[RevisionView],
    *,
    purpose: str,
    already_issued: set[tuple[str, uuid.UUID]] | None = None,
) -> list[RecipientPlan]:
    """Rule 12 and 14: one plan per matching recipient, revisions below a rule's minimum excluded with a reason.

    ``purpose`` is the release's and is what every plan carries: it is what is
    sent. A rule's own purpose only narrows: a rule that names one applies to
    releases of that purpose and to no other.

    A recipient matched by several rules gets each revision once. A revision the
    recipient already received is listed in ``duplicates`` (``duplicate_issue``),
    still included: re-issue is allowed with a reason.
    """
    issued = already_issued or set()
    plans: dict[str, RecipientPlan] = {}
    for rule in rules:
        if rule.purpose and rule.purpose != purpose:
            continue
        for r in revisions:
            if not _matches(rule, r):
                continue
            plan = plans.setdefault(rule.recipient_key, RecipientPlan(rule.recipient_key, purpose=purpose))
            if rule.id not in plan.rule_ids:
                plan.rule_ids.append(rule.id)
            if rule.min_suitability and rank(r.suitability_code) < rank(rule.min_suitability):
                if r.revision_id not in plan.revision_ids and all(e[0] != r.revision_id for e in plan.excluded):
                    plan.excluded.append((r.revision_id, "below_min_suitability"))
                continue
            if r.revision_id in plan.revision_ids:
                continue
            plan.excluded = [e for e in plan.excluded if e[0] != r.revision_id]
            plan.revision_ids.append(r.revision_id)
            if (rule.recipient_key, r.revision_id) in issued:
                plan.duplicates.append(r.revision_id)
    return [p for p in plans.values() if p.revision_ids or p.excluded]


# ── reports (rules 17, 18) ───────────────────────────────────────────────


def report_acceptance_error(
    *,
    independent_check: str,
    author_party: str | None,
    checker_party: str | None,
    external: bool,
    cycle_state: str | None,
) -> str | None:
    """Rule 17: a report needing an independent check needs a checker of another party and, when external, an approved cycle."""
    if independent_check != "required_by_rule":
        return None
    if not author_party:
        # Without an author there is no party to be independent of.
        return "report_author_required"
    if not checker_party:
        return "report_checker_required"
    if checker_party == author_party:
        return "report_checker_same_party"
    if external and cycle_state != "approved":
        return "report_external_check_not_approved"
    return None


def rationale_error(rationale: str | None, code: str = "rationale_required") -> str | None:
    """Rule 18: a decision against the default needs words, not whitespace."""
    return None if (rationale or "").strip() else code


# ── permits (rule 19) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PermitItemView:
    id: uuid.UUID
    kind: str
    required: bool
    present: bool
    state_ok: bool


def permit_missing(items: Sequence[PermitItemView]) -> list[uuid.UUID]:
    """Required items not present with a shared or published revision (or, for reports, accepted)."""
    return [i.id for i in items if i.required and not (i.present and i.state_ok)]


def superseded_items(pinned: dict[uuid.UUID, uuid.UUID | None], current: dict[uuid.UUID, uuid.UUID | None]) -> list:
    """Containers whose current revision moved past the pinned one after submission."""
    return [cid for cid, rev in pinned.items() if rev is not None and current.get(cid) not in (None, rev)]


# ── governance readiness (rule 16) ───────────────────────────────────────


@dataclass(frozen=True)
class PhaseBlockers:
    deliverables: list[str]
    reports: list[str]
    major_comments: int

    @property
    def met(self) -> bool:
        return not self.deliverables and not self.reports and self.major_comments == 0


def phase_blockers(
    phase_code: str | None,
    *,
    deliverables: Iterable[tuple[str, str, str, bool]],
    reports: Iterable[tuple[str, str, str, bool]],
    open_major_comments: Iterable[str],
) -> PhaseBlockers:
    """Rule 16 for one phase.

    ``deliverables`` and ``reports`` are ``(label, phase_code, state, required)``;
    ``open_major_comments`` lists the phase codes of reviews that still hold an
    open major comment. ``phase_code`` ``None`` asks for the whole project: a
    project without a phase model has no phase to ask for, and whatever its
    rows carry as a phase is the user's own word.
    """
    if phase_code is None:
        return PhaseBlockers(
            [lbl for lbl, _ph, st, req in deliverables if req and st not in ("accepted", "waived")],
            [lbl for lbl, _ph, st, req in reports if req and st not in ("accepted", "not_required")],
            sum(1 for _ph in open_major_comments),
        )
    d = [lbl for lbl, ph, st, req in deliverables if ph == phase_code and req and st not in ("accepted", "waived")]
    # A required report filed under no phase blocks every design gate: it cannot be parked out of sight.
    r = [
        lbl
        for lbl, ph, st, req in reports
        if (not ph or ph == phase_code) and req and st not in ("accepted", "not_required")
    ]
    c = sum(1 for ph in open_major_comments if ph == phase_code)
    return PhaseBlockers(d, r, c)


def party_key(*, contact_id: object | None, originator_code: str | None, party_kind: str | None) -> str | None:
    """The party a role belongs to: its organisation (contact) first, else its originator code."""
    if contact_id:
        return f"contact:{contact_id}"
    if originator_code:
        return f"originator:{originator_code.upper()}"
    return f"kind:{party_kind}" if party_kind else None


__all__ = [
    "DEFAULT_TARGET",
    "PUBLISHED",
    "DrawingState",
    "MatrixRule",
    "PermitItemView",
    "PhaseBlockers",
    "RecipientPlan",
    "RevisionView",
    "deliverable_state",
    "distribution_plan",
    "party_key",
    "permit_missing",
    "phase_blockers",
    "rank",
    "rationale_error",
    "release_content_errors",
    "report_acceptance_error",
    "superseded_items",
]
