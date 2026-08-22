# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The award record (Vergabevermerk) assembled from the procedure itself.

German public procurement asks the contracting authority to keep a written
record of the award procedure: VOB/A section 20 below the EU threshold, VgV
section 8 above it. The record names the individual stages, the measures taken
and the reasons for the individual decisions, so that a review body can follow
how the award was reached. Its point is that it is written while the procedure
runs rather than reconstructed once the contract is signed.

Almost everything such a record has to state this module already holds: the
package and the part of the bill it was raised over, the firms invited and when
the package went out, the bids and their sums, the levelling that put them on
one scope, and the award. Two kinds of statement need a person: why this
procedure type was chosen, and why the winning bid won. So the record is
assembled here from the procedure's own data, and the human statements are kept
beside those facts rather than in place of them. A retyped copy of a fact the
system already holds is a fact that can drift away from the procedure it claims
to describe.

Two design points worth stating.

*Due-ness is read from evidence, not from the status column.* A package may go
from ``draft`` straight to ``closed`` (see ``_PACKAGE_TRANSITIONS``), which is a
procedure cancelled before it began. Deriving what the record owes from the bare
status would make such a package owe an award reason and a bid opening. So each
section asks the procedure what actually happened: recipients or an issue stamp
mean the invitation stage is due, bids mean the opening is due, an award stamp
means the award reason is due. Whatever is due and unstated is named as a gap;
an incomplete record that names its gaps is the correct answer at an early
stage, and a record that looks complete because nothing was expected yet is not.

*Pure, and free of the database*, the way ``intl.py`` next door is: the caller
loads the package, its bids, its scope and its levelling and passes them in.
That is also what makes the interesting property testable - change a bid and the
record changes, because there is no stored copy of it to go stale.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

# ── Vocabulary ───────────────────────────────────────────────────────────────
# Section and fact keys are stable codes, never sentences: the reader's language
# is decided in the UI, and this module never guesses it. Money rides as a
# Decimal-as-string (v3 section 10) and is formatted at the presentation
# boundary only.

SOURCE_PROCEDURE = "procedure"
SOURCE_REASONING = "reasoning"

STATE_RECORDED = "recorded"
STATE_MISSING = "missing"
STATE_NOT_DUE_YET = "not_due_yet"

# The sections only a person can supply. Everything else is assembled.
REASONING_SECTIONS: tuple[str, ...] = (
    "procedure_type",
    "procedure_reason",
    "evaluation_criteria",
    "exclusions",
    "award_reason",
)

# The order a reader walks the record in, which is the order the procedure ran.
SECTION_ORDER: tuple[str, ...] = (
    "subject",
    "estimated_value",
    "procedure_type",
    "procedure_reason",
    "evaluation_criteria",
    "participants",
    "bids_received",
    "exclusions",
    "evaluation",
    "award_decision",
    "award_reason",
)

# Package statuses that are evidence the package was actually put out. ``closed``
# is deliberately absent: a package closed out of ``draft`` was cancelled before
# anybody was invited.
_ISSUED_STATUSES: frozenset[str] = frozenset({"issued", "collecting", "evaluating", "awarded"})

# Bid statuses that mean the bid was taken out of the evaluation.
_EXCLUDED_BID_STATUSES: frozenset[str] = frozenset({"rejected", "excluded", "disqualified"})

# Where the stored human statements live inside the package metadata. The same
# extensible-per-package store that already carries recipients, addenda and the
# lifecycle stamps, so no new table and no migration.
METADATA_KEY = "award_record"


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    """Parse a money value exactly, never raising (mirrors the service helper)."""
    try:
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _money(value: Any) -> str:
    """Render a money value as a plain Decimal-as-string."""
    return format(_to_decimal(value), "f")


def _fact(
    key: str,
    *,
    text: str = "",
    amount: str | None = None,
    currency: str = "",
    count: int | None = None,
    at: str | None = None,
    state: str = "",
) -> dict:
    """One stated fact: a stable key plus whichever value shapes it carries."""
    return {
        "key": key,
        "text": text,
        "amount": amount,
        "currency": currency,
        "count": count,
        "at": at,
        "state": state,
    }


def read_notes(metadata: Mapping | None) -> list[dict]:
    """The human statements stored on a package, in the order they were written.

    Insertion order is the record's order, the way ``addenda`` is ordered by its
    own revision counter rather than by a timestamp: a clock that jumps must not
    reorder what somebody wrote.
    """
    stored = (metadata or {}).get(METADATA_KEY) if isinstance(metadata, Mapping) else None
    if not isinstance(stored, Mapping):
        return []
    raw = stored.get("notes")
    if not isinstance(raw, list):
        return []
    return [n for n in raw if isinstance(n, Mapping) and n.get("section") in REASONING_SECTIONS]


def _statements_by_section(notes: Sequence[Mapping]) -> dict[str, list[dict]]:
    """Group the statements per section, newest last."""
    grouped: dict[str, list[dict]] = {}
    for note in notes:
        grouped.setdefault(str(note.get("section")), []).append(dict(note))
    return grouped


def build_award_record(
    *,
    package_name: str,
    status: str,
    metadata: Mapping | None = None,
    bids: Sequence[Any] = (),
    package_description: str = "",
    deadline: str | None = None,
    project_name: str = "",
    currency: str = "",
    boq_name: str = "",
    scope: Mapping | None = None,
    budget_total: Any = "0",
    leveling: Sequence[Any] = (),
    excluded_off_currency: int = 0,
) -> dict:
    """Assemble the award record for one package at whatever stage it stands.

    Every argument is read, none is written: the caller's ``metadata`` mapping
    comes back untouched, so building a record can never dirty a package.

    Args:
        package_name: The package's name.
        status: The package's lifecycle status.
        metadata: The package metadata, which carries the stored statements.
        bids: The bids as loaded for the package (never the lazy relationship).
        package_description: The package's description, if it has one.
        deadline: The submission deadline as stored on the package.
        project_name: The project the package belongs to.
        currency: The project currency, used for the estimated value.
        boq_name: The name of the bill the package was raised over.
        scope: The output of ``_scope_sections`` for this package, if readable.
        budget_total: The estimated value, summed over the positions in scope.
        leveling: The per-bid levelling summaries, if levelling could run.
        excluded_off_currency: Bids levelling had to leave out on currency.

    Returns:
        A mapping with ``stage``, ``started``, ``sections``, ``gaps`` and
        ``is_complete``. Each section carries its key, its source
        (``procedure`` or ``reasoning``), its state and the facts behind it.
    """
    meta = metadata if isinstance(metadata, Mapping) else {}
    described = scope if isinstance(scope, Mapping) else {}
    notes = read_notes(meta)
    statements = _statements_by_section(notes)

    recipients = [r for r in (meta.get("recipients") or []) if isinstance(r, Mapping)]
    bid_list = list(bids)
    excluded_bids = [b for b in bid_list if str(getattr(b, "status", "") or "") in _EXCLUDED_BID_STATUSES]

    awarded_bid_id = str(meta.get("awarded_bid_id") or "")
    awarded_at = meta.get("awarded_at")
    issued_at = meta.get("issued_at")

    # ── What the procedure shows has happened ────────────────────────────────
    was_issued = bool(issued_at) or bool(recipients) or bool(bid_list) or status in _ISSUED_STATUSES
    has_bids = bool(bid_list)
    was_awarded = bool(awarded_bid_id) or bool(awarded_at) or status == "awarded"

    budget = _to_decimal(budget_total)
    sections: list[dict] = []

    def _procedure_section(key: str, *, due: bool, recorded: bool, facts: list[dict]) -> None:
        if not due:
            state = STATE_NOT_DUE_YET
        else:
            state = STATE_RECORDED if recorded else STATE_MISSING
        sections.append(
            {
                "key": key,
                "source": SOURCE_PROCEDURE,
                "state": state,
                "facts": facts,
                "statement": "",
                "value": "",
                "recorded_at": None,
                "recorded_by": None,
                "superseded": [],
            }
        )

    def _reasoning_section(key: str, *, due: bool, facts: list[dict]) -> None:
        written = statements.get(key, [])
        current = written[-1] if written else None
        if current is not None:
            state = STATE_RECORDED
        elif due:
            state = STATE_MISSING
        else:
            state = STATE_NOT_DUE_YET
        sections.append(
            {
                "key": key,
                "source": SOURCE_REASONING,
                "state": state,
                "facts": facts,
                "statement": str((current or {}).get("text") or ""),
                "value": str((current or {}).get("value") or ""),
                "recorded_at": (current or {}).get("recorded_at"),
                "recorded_by": (current or {}).get("recorded_by"),
                # Earlier statements stay readable. A record that can be quietly
                # rewritten months later is not the contemporaneous document the
                # law asks for, so nothing is ever replaced, only superseded.
                "superseded": [
                    {
                        "text": str(n.get("text") or ""),
                        "value": str(n.get("value") or ""),
                        "recorded_at": n.get("recorded_at"),
                        "recorded_by": n.get("recorded_by"),
                    }
                    for n in reversed(written[:-1])
                ],
            }
        )

    # ── 1. Subject of the procurement ────────────────────────────────────────
    scope_sections = [s for s in (described.get("sections") or []) if isinstance(s, Mapping)]
    subject_facts = [_fact("package_name", text=package_name)]
    if project_name:
        subject_facts.append(_fact("project_name", text=project_name))
    if package_description:
        subject_facts.append(_fact("package_description", text=package_description))
    if boq_name:
        subject_facts.append(_fact("bill_name", text=boq_name))
    if scope_sections:
        subject_facts.append(
            _fact(
                "scope_sections",
                text=", ".join(
                    " ".join(part for part in [str(s.get("ordinal") or ""), str(s.get("description") or "")] if part)
                    for s in scope_sections
                ),
                count=len(scope_sections),
            )
        )
    included = int(described.get("included_position_count") or 0)
    bill_positions = int(described.get("boq_position_count") or 0)
    if included:
        subject_facts.append(_fact("scope_positions", count=included))
    if bill_positions:
        subject_facts.append(_fact("bill_positions", count=bill_positions))
    if described:
        # A code, not a word: "yes" here would reach a German reader untranslated.
        subject_facts.append(
            _fact("covers_whole_bill", state="whole_bill" if described.get("covers_whole_bill") else "part_of_bill")
        )
    if deadline:
        subject_facts.append(_fact("deadline", at=str(deadline)))
    _procedure_section(
        "subject",
        due=True,
        recorded=bool(boq_name or included or package_description),
        facts=subject_facts,
    )

    # ── 2. Estimated value ───────────────────────────────────────────────────
    # Summed over the positions the package was actually raised over, by the
    # caller, off the live bill: the frozen line-item template in the package
    # metadata is a copy from creation day and would drift.
    _procedure_section(
        "estimated_value",
        due=True,
        recorded=budget > 0,
        facts=[_fact("estimated_value", amount=_money(budget), currency=currency)],
    )

    # ── 3/4. Procedure type and why it was chosen ────────────────────────────
    # Due from the first day: choosing the procedure is the first decision the
    # record has to carry, and it is the one an auditor asks about first.
    _reasoning_section("procedure_type", due=True, facts=[])
    _reasoning_section("procedure_reason", due=True, facts=[])

    # ── 5. Award criteria ────────────────────────────────────────────────────
    # Due once the package went out, because bidders have to be told what they
    # are being measured on before they price.
    _reasoning_section("evaluation_criteria", due=was_issued, facts=[])

    # ── 6. Who was invited, and when the package went out ────────────────────
    participant_facts = [
        _fact(
            "invited",
            text=str(r.get("company_name") or r.get("email") or ""),
            at=str(r.get("sent_at")) if r.get("sent_at") else None,
        )
        for r in recipients
    ]
    if recipients:
        participant_facts.append(_fact("invited_count", count=len(recipients)))
    if issued_at:
        participant_facts.append(_fact("issued_at", at=str(issued_at)))
    if meta.get("last_distributed_at"):
        participant_facts.append(_fact("distributed_at", at=str(meta.get("last_distributed_at"))))
    _procedure_section(
        "participants",
        due=was_issued,
        recorded=bool(recipients),
        facts=participant_facts,
    )

    # ── 7. The bids received ─────────────────────────────────────────────────
    bid_facts = [
        _fact(
            "bid",
            text=str(getattr(b, "company_name", "") or ""),
            amount=_money(getattr(b, "total_amount", "0")),
            currency=str(getattr(b, "currency", "") or ""),
            at=str(getattr(b, "submitted_at", "") or "") or None,
        )
        for b in bid_list
    ]
    if bid_list:
        bid_facts.append(_fact("bid_count", count=len(bid_list)))
    _procedure_section("bids_received", due=has_bids or was_issued, recorded=has_bids, facts=bid_facts)

    # ── 8. Which bids were excluded, and on what ground ──────────────────────
    # The ground for taking a bid out of the evaluation is a judgement, so it is
    # a human statement; the bids and the status each one carries are shown as
    # the evidence it is written against. Due as soon as there are bids: the
    # formal examination is a stage of the procedure whether or not it ended up
    # excluding anybody, and "no bid was excluded" is a sentence a record needs
    # to contain rather than a silence a reader has to interpret.
    # The bid's own status is the procedure's word for what happened to it.
    # After an award every bid that did not win reads as rejected, which is why
    # the ground a reader needs cannot be inferred from it here.
    exclusion_facts = [
        _fact(
            "bid_status",
            text=str(getattr(b, "company_name", "") or ""),
            state=str(getattr(b, "status", "") or ""),
        )
        for b in bid_list
    ]
    if excluded_bids:
        exclusion_facts.append(_fact("excluded_count", count=len(excluded_bids)))
    _reasoning_section("exclusions", due=has_bids, facts=exclusion_facts)

    # ── 9. The evaluation of the bids that remained ──────────────────────────
    leveling_facts: list[dict] = []
    imputed_lines = 0
    for summary in leveling:
        leveling_facts.append(
            _fact(
                "leveled_bid",
                text=str(getattr(summary, "company_name", "") or ""),
                amount=_money(getattr(summary, "leveled_amount", "0")),
                currency=str(getattr(summary, "currency", "") or "") or currency,
            )
        )
        imputed_lines += int(getattr(summary, "imputed_lines", 0) or 0)
    if imputed_lines:
        leveling_facts.append(_fact("leveled_lines_imputed", count=imputed_lines))
    if excluded_off_currency:
        leveling_facts.append(_fact("off_currency_excluded", count=excluded_off_currency))
    _procedure_section(
        "evaluation",
        due=has_bids,
        recorded=bool(leveling_facts),
        facts=leveling_facts,
    )

    # ── 10. The award itself ─────────────────────────────────────────────────
    winner = None
    for b in bid_list:
        if awarded_bid_id and str(getattr(b, "id", "")) == awarded_bid_id:
            winner = b
            break
        if not awarded_bid_id and str(getattr(b, "status", "") or "") == "accepted":
            winner = b
    award_facts: list[dict] = []
    if winner is not None:
        award_facts.append(_fact("awarded_to", text=str(getattr(winner, "company_name", "") or "")))
        award_facts.append(
            _fact(
                "awarded_sum",
                amount=_money(getattr(winner, "total_amount", "0")),
                currency=str(getattr(winner, "currency", "") or "") or currency,
            )
        )
    if awarded_at:
        award_facts.append(_fact("awarded_at", at=str(awarded_at)))
    if meta.get("awarded_by"):
        award_facts.append(_fact("awarded_by", text=str(meta.get("awarded_by"))))
    _procedure_section("award_decision", due=was_awarded, recorded=winner is not None, facts=award_facts)

    # ── 11. Why that bid won ─────────────────────────────────────────────────
    _reasoning_section("award_reason", due=was_awarded, facts=[])

    by_key = {s["key"]: s for s in sections}
    ordered = [by_key[key] for key in SECTION_ORDER if key in by_key]
    gaps = [{"section": s["key"], "source": s["source"]} for s in ordered if s["state"] == STATE_MISSING]

    return {
        "stage": status,
        # The record has been started once a person has written into it. Nothing
        # is stored before that, so a package nobody opted in for stays exactly
        # as it was.
        "started": bool(notes),
        "started_at": (notes[0].get("recorded_at") if notes else None),
        "currency": currency,
        "sections": ordered,
        "gaps": gaps,
        "is_complete": not gaps,
    }


def append_note(
    metadata: Mapping | None,
    *,
    note_id: str,
    section: str,
    text: str,
    value: str = "",
    recorded_at: str,
    recorded_by: str | None = None,
) -> dict:
    """Return a new metadata mapping with one statement appended.

    Statements are append-only: an earlier statement is superseded, never
    overwritten, so the record still shows what was believed when it was
    written. The input mapping is not mutated.
    """
    if section not in REASONING_SECTIONS:
        raise ValueError(f"Unknown award record section: {section!r}")
    meta = dict(metadata or {})
    stored = meta.get(METADATA_KEY)
    record = dict(stored) if isinstance(stored, Mapping) else {}
    notes = [dict(n) for n in record.get("notes", []) if isinstance(n, Mapping)]
    notes.append(
        {
            "id": note_id,
            "section": section,
            "text": text,
            "value": value,
            "recorded_at": recorded_at,
            "recorded_by": recorded_by,
        }
    )
    record["notes"] = notes
    meta[METADATA_KEY] = record
    return meta


__all__ = [
    "METADATA_KEY",
    "REASONING_SECTIONS",
    "SECTION_ORDER",
    "SOURCE_PROCEDURE",
    "SOURCE_REASONING",
    "STATE_MISSING",
    "STATE_NOT_DUE_YET",
    "STATE_RECORDED",
    "append_note",
    "build_award_record",
    "read_notes",
]
