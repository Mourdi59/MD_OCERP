# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the governance demo seed leaves a project, as data.

Nothing here touches a database. ``seed.py`` turns a story into service calls;
this module says which story a project gets and reads the demo file of a pack.

The other module seeders tell their own story from the state governance left:
a project whose gate into the phase that enables ``construction_start`` is
undecided shows preparation, one where it is decided shows a running site. So
the variety of the demo estate is set here, in :data:`PLACEMENT`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Demo projects the seed moves past the first gate, by ``metadata.demo_id``.
#: ``execution``: every gate up to the one that starts construction is decided.
#: ``near_handover``: the same, and the gate into handover is being prepared.
#: Every other demo project keeps the first-gate story.
PLACEMENT: dict[str, str] = {
    "residential-berlin": "execution",
    "medical-us": "near_handover",
}

#: The story of the project the active pack's demo file names, and the story of every other one.
PACK = "pack"
FIRST_GATE = "first_gate"

#: Why a project was not left at its planned moment. Stable codes: the
#: integration seed fails the demo build on any of them.
FALLBACK_REASONS = frozenset(
    {
        "gate_blocked",  # a gate on the walk has a blocker a go with conditions cannot lift
        "no_construction_phase",  # the pinned model has no phase that enables construction_start
        "demo_file_invalid",  # the demo file of the pack breaks a rule of this seed
        "pack_catalogue_unavailable",  # the phase model the demo file pins did not load
        "story_error",  # a story raised anything else; the traceback is in the log
        "no_decider",  # the manager login is missing, so four-eyes has nobody to decide
        "no_owner",  # the project has no owner and the owner login is missing
        "owner_is_decider",  # the owner is the decider; four-eyes would refuse every decision
        "project_not_found",
    }
)

#: The words a demo file may use for a login. The decider is never an owner:
#: under four-eyes a decider who owns an area cannot decide.
OWNER_WORDS = frozenset({"owner", "cost"})
DOCUMENT_STATES = frozenset({"draft", "in_review"})
STOP_AT = ("not_started", "in_preparation", "in_review", "decided")
CHECK_STATUSES = frozenset({"ready", "ready_with_risks", "not_ready", "not_assessed"})


class DemoFileError(ValueError):
    """The demo file of a pack breaks a rule; the project gets the built-in story instead."""


@dataclass(frozen=True)
class DocumentPlan:
    """One frame document as the seed issues it into the common data environment."""

    doc_type: str
    container_code: str
    title: str
    file_name: str
    revisions: int = 1
    submit: bool = False


@dataclass(frozen=True)
class CheckPlan:
    area: str
    status: str
    rag: str
    note: str


@dataclass(frozen=True)
class ConditionPlan:
    area: str | None
    document_type: str | None
    text: str
    owner: str
    due_in_days: int
    severity: str


@dataclass(frozen=True)
class DecisionPlan:
    outcome: str
    rationale: str
    conditions: tuple[ConditionPlan, ...]


@dataclass(frozen=True)
class PackStory:
    """The governance part of a pack's demo file, checked against the pack's phase model."""

    four_eyes: bool
    area_owners: dict[str, str]
    documents: tuple[DocumentPlan, ...]
    gate_code: str
    target_in_days: int | None
    stop_at: str
    checks: tuple[CheckPlan, ...]
    decision: DecisionPlan | None


def gates_until(catalogue: Any, capability: str) -> list[str]:
    """Gate codes in phase order, up to and including the gate into the phase enabling ``capability``.

    Empty when no phase of the catalogue enables it. The gate is found by the
    tag on its target phase, never by its code, so the walk holds for any model.
    """
    targets = {p.code for p in catalogue.phases_enabling(capability)}
    order = {p.code: p.order for p in catalogue.phases}
    walk: list[str] = []
    for gate in sorted(catalogue.gates, key=lambda g: order.get(g.from_phase, 0)):
        walk.append(gate.code)
        if gate.to_phase in targets:
            return walk
    return []


def document_plan(doc_type: str) -> DocumentPlan:
    """A container for a frame document the built-in stories issue, named after its type."""
    return DocumentPlan(
        doc_type=doc_type,
        container_code=f"GOV-{doc_type.upper().replace('_', '-')}",
        title=doc_type.replace("_", " ").capitalize(),
        file_name=f"{doc_type.replace('_', '-')}.pdf",
    )


# ── the demo file of a pack ──


def _text(value: Any, locale: str) -> str:
    """Plain text, or the entry of a ``{locale: text}`` map for the project's language."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get(locale) or value.get("en") or "")
    return ""


def _need(ok: bool, reason: str) -> None:
    if not ok:
        raise DemoFileError(reason)


def pack_pin(data: Any) -> tuple[str, int]:
    """``(catalogue id, version)`` of the pack phase model the file pins."""
    pins = data.get("pins") if isinstance(data, dict) else None
    models = [p for p in pins or [] if isinstance(p, dict) and p.get("kind") == "phase_model"]
    _need(len(models) == 1, "the file pins exactly one phase model")
    pin = models[0]
    _need(pin.get("source") == "pack", "the phase model is a catalogue of the pack")
    _need(isinstance(pin.get("id"), str) and isinstance(pin.get("version"), int), "the pin names an id and a version")
    return pin["id"], pin["version"]


def _decision(raw: Any, areas: set[str], locale: str) -> DecisionPlan:
    _need(isinstance(raw, dict) and isinstance(raw.get("outcome"), str), "a decided gate carries its decision")
    conditions = []
    for item in raw.get("conditions") or []:
        _need(isinstance(item, dict), "a condition is an object")
        _need(item.get("area") is None or item["area"] in areas, "a condition names an area of the model")
        _need(item.get("owner") in OWNER_WORDS, "a condition is owned by the owner or the cost login")
        _need(isinstance(item.get("due_in_days"), int), "a condition is due a number of days after the seed")
        conditions.append(
            ConditionPlan(
                area=item.get("area"),
                document_type=item.get("document_type"),
                text=_text(item.get("text"), locale),
                owner=item["owner"],
                due_in_days=item["due_in_days"],
                severity=item.get("severity") or "essential",
            )
        )
    return DecisionPlan(raw["outcome"], _text(raw.get("rationale"), locale), tuple(conditions))


def pack_story(data: Any, catalogue: Any, locale: str) -> PackStory:
    """The story a demo file tells, checked against the phase model it pins.

    Raises:
        DemoFileError: The file breaks a rule. Nothing of it is used then: a
            half-read story would leave a screen of the film empty.
    """
    gov = data.get("governance") if isinstance(data, dict) else None
    _need(isinstance(gov, dict), "the file has a governance section")
    _need(isinstance(gov.get("four_eyes"), bool), "four_eyes is true or false")

    areas = {a.code for a in catalogue.areas}
    owners = gov.get("area_owners")
    _need(isinstance(owners, dict) and set(owners) == areas, "area_owners names exactly the areas of the model")
    _need(set(owners.values()) <= OWNER_WORDS, "an area is owned by the owner or the cost login")

    types = {d.code for d in catalogue.document_types}
    rows = gov.get("frame_documents")
    _need(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "frame_documents is a list")
    _need(
        sorted(str(r.get("doc_type")) for r in rows) == sorted(types),
        "frame_documents names exactly the document types of the model",
    )
    documents = []
    for row in rows:
        _need(row.get("state") in DOCUMENT_STATES, "before a decision a document is a draft or in review")
        _need(isinstance(row.get("revisions"), int) and row["revisions"] >= 1, "a document has at least one revision")
        _need(bool(row.get("container_code")) and bool(row.get("file_name")), "a document names its container and file")
        documents.append(
            DocumentPlan(
                doc_type=row["doc_type"],
                container_code=str(row["container_code"]),
                title=_text(row.get("title"), locale) or row["doc_type"],
                file_name=str(row["file_name"]),
                revisions=row["revisions"],
                submit=row["state"] == "in_review",
            )
        )
    _need(len({d.container_code for d in documents}) == len(documents), "every document has its own container")

    gate = gov.get("gate")
    _need(isinstance(gate, dict), "the file names the gate of the story")
    first = first_gate(catalogue)
    _need(gate.get("code") in {g.code for g in catalogue.gates}, "the gate is a gate of the model")
    _need(gate["code"] == first, "the story is about the first gate of the model, the only one the seed can reach")
    _need(gate.get("stop_at") in STOP_AT, f"stop_at is one of {', '.join(STOP_AT)}")
    target = gate.get("target_in_days")
    _need(target is None or isinstance(target, int), "target_in_days is a number of days")

    checks_raw = gate.get("checks")
    _need(isinstance(checks_raw, list) and all(isinstance(c, dict) for c in checks_raw), "checks is a list")
    _need(
        sorted(str(c.get("area")) for c in checks_raw) == sorted(areas), "checks names exactly the areas of the model"
    )
    _need(all(c.get("status") in CHECK_STATUSES for c in checks_raw), "a check status is one the owner can confirm")
    checks = tuple(
        CheckPlan(c["area"], c["status"], str(c.get("rag") or ""), _text(c.get("note"), locale)) for c in checks_raw
    )

    decided = gate["stop_at"] == "decided"
    _need(decided or gate.get("decision") is None, "only a decided gate carries a decision")
    decision = _decision(gate.get("decision"), areas, locale) if decided else None
    return PackStory(
        four_eyes=gov["four_eyes"],
        area_owners=dict(owners),
        documents=tuple(documents),
        gate_code=gate["code"],
        target_in_days=target,
        stop_at=gate["stop_at"],
        checks=checks,
        decision=decision,
    )


def first_gate(catalogue: Any) -> str | None:
    """The code of the gate out of the first phase, the one a fresh project stands before."""
    order = {p.code: p.order for p in catalogue.phases}
    gates = sorted(catalogue.gates, key=lambda g: order.get(g.from_phase, 0))
    return gates[0].code if gates else None


# ── what the seed reports ──


def pack_demo_id(data: Any) -> str | None:
    """The ``metadata.demo_id`` of the project a demo file is about, or ``None``."""
    project = data.get("project") if isinstance(data, dict) else None
    demo_id = project.get("demo_template_id") if isinstance(project, dict) else None
    return demo_id if isinstance(demo_id, str) and demo_id else None


def planned_moment(demo_id: str | None, pack_project: str | None) -> str:
    """Where the seed means to leave a project, decided before any story is read.

    The project the pack names is planned as the pack story whether or not its
    file then passes the rules: a file that fails is a fallback, not a plan.
    """
    if demo_id and demo_id == pack_project:
        return PACK
    return PLACEMENT.get(demo_id or "", FIRST_GATE)


def placement(
    project_id: Any,
    demo_id: str | None,
    planned: str,
    reached: str | None,
    reason: str | None = None,
    *,
    skipped: bool = False,
) -> dict[str, Any]:
    """One row of the seed result: where a project was meant to be left and where it was.

    Args:
        project_id: The project.
        demo_id: Its ``metadata.demo_id``, when it has one.
        planned: The moment :func:`planned_moment` gave.
        reached: The story that was written, ``None`` when this run wrote none.
        reason: Why the first story that failed did, one of :data:`FALLBACK_REASONS`.
        skipped: The project carried a model before this run; nothing was tried.

    Returns:
        The row. ``fallback_reason`` is ``None`` only for a project that reached
        its planned moment or was skipped; any other row carries a code.
    """
    missed = not skipped and reached != planned
    return {
        "project_id": str(project_id),
        "demo_id": demo_id,
        "planned": planned,
        "reached": reached,
        "fallback_reason": (reason if reason in FALLBACK_REASONS else "story_error") if missed else None,
        "skipped": skipped,
        "named": planned != FIRST_GATE,
    }


def seed_result(placements: list[dict[str, Any]], pack_demo_file: str = "absent") -> dict[str, Any]:
    """The result of a seed run, one row per project handed in.

    ``ok`` is false when any project missed its planned moment, or when the
    active pack names a demo file nobody could read (``pack_demo_file`` is
    ``unreadable``; no row can show that, the file would have named the project).
    """
    fallbacks = [row for row in placements if row["fallback_reason"]]
    return {
        "projects": sum(1 for row in placements if row["reached"] is not None),
        "placements": placements,
        "fallbacks": fallbacks,
        "pack_demo_file": pack_demo_file,
        "ok": not fallbacks and pack_demo_file != "unreadable",
    }
