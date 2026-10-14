# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo transmittals, run by ``app.core.demo_enrichment``.

Unlike the other module seeders this one has no generic story: a transmittal is
a formal record of who sent which documents to whom, and inventing one inside a
project that tells no such story would be a data incident. The rows therefore
come entirely from the story file the active pack names for the project (key
``transmittals``); a project without such a story gets nothing.

Everything goes through :class:`TransmittalService`, so the numbers, the lock on
issue and the acknowledgement rules are the ones a user meets. Dates are offsets
in days from the seed day. A project that already has a transmittal is skipped,
so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transmittals.logic import PURPOSE_CODES

logger = logging.getLogger(__name__)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_transmittals_story(story: dict | None, locale: str) -> list[dict[str, Any]]:
    """The usable transmittals of a story, in order; an entry that is malformed is dropped.

    Entry keys: ``subject``, ``purpose_code`` (one of ``PURPOSE_CODES``), ``cover_note``,
    ``issued_days_ago`` (omit for a draft), ``response_due_in_days`` (days after issue),
    ``recipients`` (``name``, ``action_required``, ``acknowledged_after_days``, ``response``,
    ``responded_after_days``) and ``items`` (``description``, ``notes``). A recipient that
    responds must have acknowledged first.
    """
    from app.modules.project_governance.public import story_text

    raw = story.get("transmittals") if isinstance(story, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        parsed = _parse_entry(entry, locale, story_text)
        if parsed is None:
            logger.info("transmittals demo story: entry %d not usable, skipped", index)
            continue
        out.append(parsed)
    return out


def _parse_entry(entry: object, locale: str, story_text) -> dict[str, Any] | None:
    if not isinstance(entry, dict) or entry.get("purpose_code") not in PURPOSE_CODES:
        return None
    subject = story_text(entry.get("subject"), locale)
    issued = entry.get("issued_days_ago")
    due = entry.get("response_due_in_days")
    if not subject or (issued is not None and (not _is_int(issued) or issued < 0)):
        return None
    if due is not None and (not _is_int(due) or due < 0):
        return None
    recipients, items = entry.get("recipients"), entry.get("items")
    if not isinstance(recipients, list) or not recipients or not isinstance(items, list) or not items:
        return None
    parsed_recipients = []
    for r in recipients:
        if not isinstance(r, dict):
            return None
        name = story_text(r.get("name"), locale)
        ack, resp = r.get("acknowledged_after_days"), r.get("responded_after_days")
        text = story_text(r.get("response"), locale) if r.get("response") is not None else ""
        if not name or (issued is None and (ack is not None or resp is not None)):
            return None
        if ack is not None and (not _is_int(ack) or ack < 0):
            return None
        if resp is not None and (not _is_int(resp) or resp < (ack or 0) or ack is None or not text):
            return None
        parsed_recipients.append(
            {
                "name": name,
                "action_required": story_text(r.get("action_required"), locale) or None,
                "ack": ack,
                "response": text if resp is not None else None,
                "resp": resp,
            }
        )
    if len({r["name"] for r in parsed_recipients}) != len(parsed_recipients):
        return None
    parsed_items = []
    for item in items:
        description = story_text(item.get("description"), locale) if isinstance(item, dict) else ""
        if not description:
            return None
        parsed_items.append({"description": description, "notes": story_text(item.get("notes"), locale) or None})
    return {
        "subject": subject,
        "purpose_code": entry["purpose_code"],
        "cover_note": story_text(entry.get("cover_note"), locale) or None,
        "issued": issued,
        "due": due,
        "recipients": parsed_recipients,
        "items": parsed_items,
    }


async def seed_transmittals_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the transmittals of every demo project in ``project_ids`` whose story names some. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.project_governance.public import demo_module_story
    from app.modules.projects.models import Project
    from app.modules.transmittals.models import Transmittal

    totals = {"projects": 0, "transmittals": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (
        await session.execute(select(Project.id, Project.metadata_, Project.locale).where(Project.id.in_(ids)))
    ).all()
    for pid, meta, locale in rows:
        demo_id = demo_id_of(meta)
        if not demo_id:
            continue
        entries = parse_transmittals_story(demo_module_story(demo_id, "transmittals"), locale or "en")
        if not entries:
            continue
        existing = (await session.execute(select(Transmittal).where(Transmittal.project_id == pid))).scalars().all()
        if any((t.metadata_ or {}).get("is_demo") for t in existing):
            continue
        # A pack applied in the app installs its projects before it is active, so the generic seeder has
        # already written its English transmittals. The story tells this project's instead; the ones a
        # design release issued are not demo filler and stay.
        for generic in existing:
            meta = generic.metadata_ or {}
            if "demo_id" in meta and "design_release_id" not in meta:
                await session.delete(generic)
        await session.flush()
        try:
            async with session.begin_nested():
                written = await _seed_project(session, pid, entries)
        except Exception:
            logger.warning("transmittals demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        totals["transmittals"] += written
    return totals


async def _seed_project(session: AsyncSession, pid: uuid.UUID, entries: list[dict[str, Any]]) -> int:
    from app.modules.projects.models import Project
    from app.modules.transmittals.schemas import TransmittalCreate
    from app.modules.transmittals.service import TransmittalService

    project = await session.get(Project, pid)
    owner = getattr(project, "owner_id", None)
    svc = TransmittalService(session)
    today = datetime.now(UTC).date()

    def day(offset: int) -> date:
        return today - timedelta(days=offset)

    # Oldest first, so the numbers run in the order the story happened.
    ordered = sorted(entries, key=lambda e: -(e["issued"] if e["issued"] is not None else -1))
    for entry in ordered:
        issued = entry["issued"]
        issued_on = day(issued) if issued is not None else None
        due_on = (
            issued_on + timedelta(days=entry["due"]) if issued_on is not None and entry["due"] is not None else None
        )
        created = await svc.create_transmittal(
            TransmittalCreate(
                project_id=pid,
                subject=entry["subject"],
                purpose_code=entry["purpose_code"],
                issued_date=issued_on.isoformat() if issued_on else None,
                response_due_date=due_on.isoformat() if due_on else None,
                cover_note=entry["cover_note"],
                recipients=[
                    {"recipient_name": r["name"], "action_required": r["action_required"]} for r in entry["recipients"]
                ],
                items=[
                    {"item_number": n, "description": i["description"], "notes": i["notes"]}
                    for n, i in enumerate(entry["items"], start=1)
                ],
                metadata={"is_demo": True},
            ),
            user_id=str(owner) if owner else None,
        )
        if issued_on is None:
            continue
        await svc.issue_transmittal(created.id)
        # Issuing stamps the moment of the call; the story says when it really went out.
        await svc.repo.update_fields(created.id, issued_date=issued_on.isoformat())
        by_name = {r.recipient_name: r for r in created.recipients}
        for spec in entry["recipients"]:
            recipient = by_name[spec["name"]]
            if spec["ack"] is not None:
                await svc.acknowledge_receipt(created.id, recipient.id)
                await svc.repo.update_recipient(recipient.id, acknowledged_at=_at(issued_on, spec["ack"]))
            if spec["resp"] is not None:
                await svc.submit_response(created.id, recipient.id, spec["response"])
                await svc.repo.update_recipient(recipient.id, responded_at=_at(issued_on, spec["resp"]))
    return len(ordered)


def _at(issued_on: date, after_days: int) -> datetime:
    """Ten in the morning, ``after_days`` after the issue day, never later than now."""
    moment = datetime.combine(issued_on + timedelta(days=after_days), datetime.min.time(), tzinfo=UTC).replace(hour=10)
    return min(moment, datetime.now(UTC))
