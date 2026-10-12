# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 20).

The module reports five checks under two subjects. ``stakeholders``: register
present, key stakeholders planned, commitments tracked. ``organisation``:
mandates complete, roles filled. Each subject is reported on the area that
hosts it, with its counts in ``detail``.

Which area that is comes from data: the project's own override in the
settings, else the phase model's ``hosts`` tag read through module 1's port
(see ``hosting``). No area code is matched here. The provider never goes quiet
about a register that exists:

* the model hosts a subject nowhere: one ``unknown`` item for that subject on
  the first area of the model;
* the model hosts it, but the project has no document row for that type yet
  (pinned before the model gained it): one ``unknown`` item on the hosting area.

A project that has not pinned a framework has no register and answers nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import (
    EVIDENCE_STATES,
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)
from app.modules.stakeholders.hosting import ORGANISATION_TAG, STAKEHOLDERS_TAG, SUBJECTS

PROVIDER_NAME = "stakeholders.governance_readiness"
# Every evidence item of this module links to the project's stakeholders screen.
LINK_KIND = "stakeholders"
LINK_ROUTE = "/projects/{project_id}/stakeholders"
CHECK_SUBJECT: dict[str, str] = {
    "register_present": STAKEHOLDERS_TAG,
    "key_stakeholders_planned": STAKEHOLDERS_TAG,
    "mandates_complete": ORGANISATION_TAG,
    "roles_filled": ORGANISATION_TAG,
    "commitments_tracked": STAKEHOLDERS_TAG,
}
CHECKS: tuple[str, ...] = tuple(CHECK_SUBJECT)
# An overdue promise is outstanding but does not block: the state ``warning``, acknowledged by the decider
# at a go. On a governance version without that state the promise stays what it was, a reason why
# ``commitments_tracked`` is not met.
OVERDUE_CODE = "stakeholders:commitment_overdue"


def warning_state_served() -> bool:
    """Whether the governance module in this installation knows the evidence state ``warning``."""
    return "warning" in EVIDENCE_STATES


def commitments_tracked(breached: list[str], overdue: list[str], *, warnings: bool) -> dict[str, Any]:
    """The ``commitments_tracked`` check.

    A breach without a rationale always fails it. An overdue promise fails it
    only while it cannot be reported as a warning of its own.
    """
    failing = breached if warnings else [*breached, *overdue]
    return {
        "status": "not_met" if failing else "met",
        "breached": len(failing),
        "refs": failing,
        "overdue": len(overdue),
        "overdue_refs": overdue,
    }


def overdue_items(overdue: list[dict[str, str]], link: tuple[str, str]) -> list[EvidenceItem]:
    """One ``warning`` item per overdue promise, with a code that stays the same between reads."""
    from app.modules.stakeholders.messages import available_locales, translate

    key = "stakeholders.evidence.commitment_overdue"
    return [
        EvidenceItem(
            code=f"{OVERDUE_CODE}:{c['code']}",
            state="warning",
            label_key=key,
            labels={
                locale: translate(key, locale=locale, code=c["code"], due=c["due_date"])
                for locale in available_locales()
            },
            link=link,
            detail=f"{c['code']} due {c['due_date']}",
        )
        for c in overdue
    ]


# Which export's frame document proves that a subject has a place in the project.
_EXPORT_OF: dict[str, str] = {STAKEHOLDERS_TAG: "register", ORGANISATION_TAG: "organisation"}
NO_HOST_REASON = "no_document_type_hosts_subject"
NO_DOCUMENT_REASON = "frame_document_row_missing"
# Message stem per reason; the subject completes the key.
_REASON_STEM: dict[str, str] = {NO_HOST_REASON: "host", NO_DOCUMENT_REASON: "document"}


def host_code(subject: str, reason: str = NO_HOST_REASON) -> str:
    """Stable evidence code of the item that says why a subject could not be placed."""
    return f"stakeholders:{_REASON_STEM[reason]}:{subject}"


def unknown_item(subject: str, reason: str, link: tuple[str, str]) -> EvidenceItem:
    """The ``unknown`` item for a subject, with a sentence in every shipped locale that says what to do."""
    from app.modules.stakeholders.messages import available_locales, translate

    key = f"stakeholders.evidence.{_REASON_STEM[reason]}_{subject}"
    return EvidenceItem(
        code=host_code(subject, reason),
        state="unknown",
        label_key=key,
        labels={locale: translate(key, locale=locale) for locale in available_locales()},
        link=link,
        detail=reason,
    )


def _detail(check: dict[str, Any]) -> str:
    return ", ".join(
        f"{k}={','.join(v) if isinstance(v, list) else v}" for k, v in sorted(check.items()) if k != "status"
    )


def placement(area_code: str, host: str | None, first_area: str | None) -> str:
    """What the provider answers for one subject on one area: ``items``, ``unplaced`` or ``nothing``.

    ``unplaced`` is the single ``unknown`` item, reported once (on the first
    area) when no area hosts the subject.
    """
    if host is not None:
        return "items" if area_code == host else "nothing"
    return "unplaced" if first_area is not None and area_code == first_area else "nothing"


async def governance_readiness(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.stakeholders import hosting
    from app.modules.stakeholders.service import StakeholderService

    svc = StakeholderService(session)
    settings = await svc.get_settings(project_id)
    if settings is None:
        return []
    catalogue = await hosting.project_catalogue(session, project_id)
    first = hosting.first_area_code(catalogue) if catalogue is not None else None
    link = (LINK_KIND, str(project_id))
    today = datetime.now(UTC).date()
    checks: dict[str, dict[str, Any]] | None = None
    out: list[EvidenceItem] = []
    for subject in SUBJECTS:
        host = await svc.host_area_code(project_id, settings, subject=subject)
        where = placement(area.code, host, first)
        if where == "nothing":
            continue
        reason = NO_HOST_REASON if where == "unplaced" else None
        if reason is None and not settings.owner_area_code:
            if not await svc.frame_documents(project_id, _EXPORT_OF[subject]):
                reason = NO_DOCUMENT_REASON
        if reason is not None:
            out.append(unknown_item(subject, reason, link))
            continue
        if checks is None:
            checks = await svc.readiness(project_id, today=today)
        out.extend(
            EvidenceItem(
                code=f"stakeholders:{code}",
                state=checks[code]["status"],
                label_key=f"stakeholders.evidence.{code}",
                link=link,
                detail=_detail(checks[code]),
            )
            for code in CHECKS
            if CHECK_SUBJECT[code] == subject
        )
        if subject == STAKEHOLDERS_TAG and warning_state_served():
            out.extend(overdue_items(await svc.overdue_commitments(project_id, today=today), link))
    return out


def register_gate_evidence() -> None:
    register_evidence_provider("*", governance_readiness, name=PROVIDER_NAME, blocking=False)
    register_evidence_link(LINK_KIND, LINK_ROUTE)
