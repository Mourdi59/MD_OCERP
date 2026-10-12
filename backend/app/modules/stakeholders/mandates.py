# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure mandate resolution: who decides, conflicts, vacancies and quorum (SPEC rules 11 to 15).

Inputs are plain dataclasses the service builds from rows; nothing here reads
the database or the clock. A mandate row names a role or a body and a letter
(``P`` propose, ``D`` decide, ``A`` approve or co-sign, ``C`` consulted,
``I`` informed) for a decision type and a scope (``""`` = the whole project).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.modules.stakeholders.catalogue import StakeholderFramework

GLOBAL_SCOPE = ""
# Letter pairs that may not meet in one person for one decision type (rule 12).
CONFLICT_PAIRS: tuple[tuple[str, str], ...] = (("P", "D"), ("D", "A"))


@dataclass(frozen=True)
class MandateRow:
    decision_type: str
    holder_kind: str  # role | body
    holder_code: str
    letter: str
    scope: str = GLOBAL_SCOPE


@dataclass(frozen=True)
class Holder:
    """One holder of a project role. ``user_id`` is ``None`` for an organisation or a non-user person."""

    role_code: str
    user_id: str | None = None
    contact_id: str | None = None
    roster_member_id: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    conflict_rationale: str = ""

    def valid_on(self, day: date) -> bool:
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_to is None or self.valid_to >= day)


@dataclass(frozen=True)
class Member:
    role_code: str | None = None
    user_id: str | None = None
    contact_id: str | None = None
    voting: bool = True
    valid_from: date | None = None
    valid_to: date | None = None

    def valid_on(self, day: date) -> bool:
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_to is None or self.valid_to >= day)


@dataclass(frozen=True)
class Body:
    code: str
    quorum_kind: str = "majority"  # min_members | majority | unanimous
    quorum_min: int | None = None
    members: tuple[Member, ...] = ()
    decision_level: int = 1


@dataclass(frozen=True)
class Party:
    """A resolved person or organisation behind a role or body seat."""

    user_id: str | None
    contact_id: str | None
    roster_member_id: str | None
    via_role: str | None
    voting: bool = True


@dataclass
class Resolution:
    """Answer of ``who_decides`` for one decision type and scope (rule 11)."""

    decision_type: str
    scope: str
    holder_kind: str | None = None
    holder_code: str | None = None
    parties: list[Party] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    quorum_needed: int | None = None
    quorum_present: int | None = None

    @property
    def user_ids(self) -> list[str]:
        """Everyone seated, voting or not (who is informed of the decision)."""
        return sorted({p.user_id for p in self.parties if p.user_id})

    @property
    def voting_user_ids(self) -> list[str]:
        """Who may take the decision: a guest without a vote sits in the body but does not decide."""
        return sorted({p.user_id for p in self.parties if p.user_id and p.voting})


@dataclass(frozen=True)
class Conflict:
    decision_type: str
    scope: str
    user_id: str
    letters: tuple[str, str]
    roles: tuple[str, ...]
    severity: str  # error | warning
    acknowledged: bool


def role_parties(role_code: str, holders: Iterable[Holder], today: date) -> list[Party]:
    """Holders of a role valid today (rule 14: an expired holder is not returned)."""
    return [
        Party(h.user_id, h.contact_id, h.roster_member_id, role_code)
        for h in holders
        if h.role_code == role_code and h.valid_on(today)
    ]


def quorum_needed(body: Body, today: date) -> int:
    """Voting seats that must be filled today for the body to decide (rule 15).

    Only seats valid today count, on both sides of the comparison: a member
    whose term ended no longer sits, so the expired row neither fills a seat
    nor raises the bar. A body with no valid voting seat needs one and has
    none, so it is never quorate by being empty.
    """
    seats = sum(1 for m in body.members if m.voting and m.valid_on(today))
    if body.quorum_kind == "min_members":
        return int(body.quorum_min or 1)
    if body.quorum_kind == "unanimous":
        return max(seats, 1)
    return seats // 2 + 1


def body_parties(body: Body, holders: Iterable[Holder], today: date) -> list[Party]:
    """Members valid today; a role seat expands to that role's holders valid today."""
    holders = list(holders)
    out: list[Party] = []
    for m in body.members:
        if not m.valid_on(today):
            continue
        if m.role_code:
            out.extend(
                Party(p.user_id, p.contact_id, p.roster_member_id, m.role_code, m.voting)
                for p in role_parties(m.role_code, holders, today)
            )
        else:
            out.append(Party(m.user_id, m.contact_id, None, None, m.voting))
    return out


def body_present(body: Body, holders: Iterable[Holder], today: date) -> int:
    """Voting seats filled today (a role seat counts once however many holders it has)."""
    holders = list(holders)
    present = 0
    for m in body.members:
        if not m.voting or not m.valid_on(today):
            continue
        if m.role_code:
            present += 1 if role_parties(m.role_code, holders, today) else 0
        else:
            present += 1
    return present


def deciders(rows: Iterable[MandateRow], decision_type: str, scope: str = GLOBAL_SCOPE) -> list[MandateRow]:
    return [r for r in rows if r.decision_type == decision_type and r.scope == scope and r.letter == "D"]


def decider_counts(rows: Iterable[MandateRow]) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for r in rows:
        if r.letter == "D":
            out[(r.decision_type, r.scope)] = out.get((r.decision_type, r.scope), 0) + 1
    return out


def missing_deciders(fw: StakeholderFramework, rows: Iterable[MandateRow]) -> list[str]:
    """Required decision types with no ``D`` for the whole project (rule 13, ``mandate_missing``)."""
    counts = decider_counts(rows)
    return [d.code for d in fw.decision_types if d.required and counts.get((d.code, GLOBAL_SCOPE), 0) == 0]


def who_decides(
    rows: Iterable[MandateRow],
    decision_type: str,
    scope: str,
    holders: Iterable[Holder],
    bodies: Iterable[Body],
    today: date,
) -> Resolution:
    """Rule 11: the ``D`` holder resolved to parties; a scope without its own row falls back to the project.

    Flags: ``mandate_missing`` (no ``D``), ``role_vacant`` (rule 14), ``body_inquorate`` (rule 15),
    ``unknown_body``.
    """
    rows = list(rows)
    holders = list(holders)
    res = Resolution(decision_type, scope)
    found = deciders(rows, decision_type, scope) or (
        deciders(rows, decision_type, GLOBAL_SCOPE) if scope != GLOBAL_SCOPE else []
    )
    if not found:
        res.flags.append("mandate_missing")
        return res
    row = found[0]
    res.holder_kind, res.holder_code = row.holder_kind, row.holder_code
    if row.holder_kind == "role":
        res.parties = role_parties(row.holder_code, holders, today)
        if not res.parties:
            res.flags.append("role_vacant")
        return res
    body = next((b for b in bodies if b.code == row.holder_code), None)
    if body is None:
        res.flags.append("unknown_body")
        return res
    res.parties = body_parties(body, holders, today)
    res.quorum_needed = quorum_needed(body, today)
    res.quorum_present = body_present(body, holders, today)
    if res.quorum_present < res.quorum_needed:
        res.flags.append("body_inquorate")
    return res


def vacant_roles(fw: StakeholderFramework, holders: Iterable[Holder], today: date, *, required_only: bool) -> list[str]:
    """Framework roles with no holder valid today (rule 14 ``role_vacant``)."""
    holders = list(holders)
    return [r.code for r in fw.roles if (r.required or not required_only) and not role_parties(r.code, holders, today)]


def conflicts(
    fw: StakeholderFramework,
    rows: Iterable[MandateRow],
    holders: Iterable[Holder],
    bodies: Iterable[Body],
    today: date,
) -> list[Conflict]:
    """Rule 12: one user holding letters that must not meet (P and D, D and A) for one decision type.

    ``forbid_self_approval`` on the decision type makes it an error; otherwise it
    is a warning, acknowledged when a holder row of that user in one of the
    involved roles carries a rationale.
    """
    rows = list(rows)
    holders = list(holders)
    bodies_by_code = {b.code: b for b in bodies}
    letters: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    for r in rows:
        if r.holder_kind == "role":
            parties = role_parties(r.holder_code, holders, today)
        else:
            body = bodies_by_code.get(r.holder_code)
            parties = body_parties(body, holders, today) if body else []
        for p in parties:
            if not p.user_id or not p.voting:
                # A seat without a vote does not hold the body's letter.
                continue
            slot = letters.setdefault((r.decision_type, r.scope, p.user_id), {})
            slot.setdefault(r.letter, set()).add(p.via_role or r.holder_code)
    out: list[Conflict] = []
    for (dt, scope, user), by_letter in sorted(letters.items()):
        decision = fw.decision_type(dt)
        for a, b in CONFLICT_PAIRS:
            if a in by_letter and b in by_letter:
                roles = tuple(sorted(by_letter[a] | by_letter[b]))
                ack = any(h.user_id == user and h.role_code in roles and h.conflict_rationale.strip() for h in holders)
                strict = bool(decision and decision.forbid_self_approval)
                out.append(
                    Conflict(dt, scope, user, (a, b), roles, "error" if strict else "warning", ack and not strict)
                )
    return out
