# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Live sources a handbook chapter reads instead of copying.

A source is a name and one function: ``(session, project_id, locale) -> list[LinkedRow]``. The chapter
catalogue names the sources a chapter reads; the handbook screen and the PDF call them at the moment of
display, so the organisation chapter always shows the stakeholders and positions of the project as they
are now. A module that wants its records in a chapter registers a source with ``register_source`` at
import; the catalogue validator then accepts the name.

A source that cannot answer (its module is not installed, its table is empty) answers an empty list; the
screen then says there is nothing to show instead of failing the chapter.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinkedRow:
    """One record of another module, as a chapter shows it.

    Attributes:
        label: Display text of the record.
        detail: A short second line (role, category, date).
        label_key: An i18n key the client translates instead of ``label`` (catalogue entries of governance).
        group: Optional heading the row belongs to (the module area of a position, say).
    """

    label: str
    detail: str = ""
    label_key: str | None = None
    group: str = ""


Provider = Callable[[AsyncSession, uuid.UUID, str], Awaitable[list[LinkedRow]]]


@dataclass(frozen=True)
class Source:
    """A registered source: its name, the provider and where the full records are kept."""

    name: str
    provider: Provider
    # Client route of the module screen, ``{project_id}`` filled in.
    route: str


_SOURCES: dict[str, Source] = {}


def register_source(name: str, provider: Provider, route: str) -> Source:
    """Add (or replace, idempotently) a source."""
    _SOURCES[name] = Source(name, provider, route)
    return _SOURCES[name]


def known_sources() -> frozenset[str]:
    """Names a chapter may list under ``sources``."""
    return frozenset(_SOURCES)


def get_source(name: str) -> Source | None:
    return _SOURCES.get(name)


async def linked_rows(
    session: AsyncSession, project_id: uuid.UUID, names: tuple[str, ...] | list[str], locale: str
) -> list[dict[str, Any]]:
    """Every named source of a chapter, read now: ``[{source, route, rows: [...]}]``.

    A source that fails is logged and answers empty, so one broken module never takes the chapter down.
    """
    out: list[dict[str, Any]] = []
    for name in names:
        source = _SOURCES.get(name)
        if source is None:
            continue
        try:
            rows = await source.provider(session, project_id, locale)
        except Exception:
            logger.warning("handbook source %s failed for project %s", name, project_id, exc_info=True)
            rows = []
        out.append(
            {
                "source": name,
                "route": source.route.format(project_id=project_id),
                "rows": [
                    {"label": r.label, "detail": r.detail, "label_key": r.label_key, "group": r.group} for r in rows
                ],
            }
        )
    return out


def _text(label: dict[str, Any], locale: str, fallback: str) -> tuple[str, str | None]:
    """``(text, key)`` of a governance label ``{"key", "text"}``: plain text per locale, else the key to translate."""
    texts = label.get("text") or {}
    text = texts.get(locale) or texts.get(locale.split("-")[0]) or texts.get("en")
    if text:
        return text, None
    key = label.get("key")
    if key:
        from app.modules.project_handbook.messages import is_key_present, translate

        local = f"project_handbook.governance.{key.rsplit('.', 1)[-1]}"
        if is_key_present(local):
            return translate(local, locale=locale), key
        return fallback, key
    return fallback, None


async def _stakeholders(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.contacts.models import Contact
    from app.modules.project_handbook.messages import translate
    from app.modules.stakeholders.models import Stakeholder

    stmt = (
        select(Stakeholder, Contact)
        .join(Contact, Contact.id == Stakeholder.contact_id, isouter=True)
        .where(Stakeholder.project_id == project_id, Stakeholder.status == "active")
        .order_by(Stakeholder.code)
    )
    rows: list[LinkedRow] = []
    for stakeholder, contact in (await session.execute(stmt)).all():
        name = stakeholder.display_name
        if not name and contact is not None:
            name = contact.company_name or " ".join(x for x in (contact.first_name, contact.last_name) if x)
        key = f"project_handbook.stakeholder_category.{stakeholder.category}"
        category = translate(key, locale=locale) if _has(key) else stakeholder.category.replace("_", " ")
        rows.append(LinkedRow(label=name or stakeholder.code, detail=category, group=""))
    return rows


def _has(key: str) -> bool:
    from app.modules.project_handbook.messages import is_key_present

    return is_key_present(key)


async def _staffing(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.staffing.messages import is_key_present as has
    from app.modules.staffing.messages import translate
    from app.modules.staffing.models import StaffingPosition

    def word(key: str, fallback: str) -> str:
        return translate(key, locale=locale) if has(key) else fallback.replace("_", " ")

    stmt = (
        select(StaffingPosition)
        .where(StaffingPosition.project_id == project_id)
        .order_by(StaffingPosition.phase, StaffingPosition.sort_order)
    )
    rows: list[LinkedRow] = []
    for p in (await session.execute(stmt)).scalars():
        label = p.custom_label or p.title or word(f"staffing.role.{p.role_code}", p.role_code)
        phase = word(f"staffing.phase.{p.phase}", p.phase)
        status = word(f"staffing.position_status.{p.status}", p.status)
        rows.append(LinkedRow(label=label, detail=f"{phase}, {status}", group=phase))
    return rows


async def _engineering_brief(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.engineering_brief.models import FrameMilestone

    stmt = (
        select(FrameMilestone)
        .where(FrameMilestone.project_id == project_id)
        .order_by(FrameMilestone.planned_date.is_(None), FrameMilestone.planned_date, FrameMilestone.code)
    )
    return [
        LinkedRow(label=m.name, detail=m.planned_date.isoformat() if m.planned_date else "")
        for m in (await session.execute(stmt)).scalars()
    ]


async def _governance_gates(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.project_governance import public as governance
    from app.modules.project_handbook.messages import translate

    rows: list[LinkedRow] = []
    for g in await governance.project_gates(session, project_id):
        text, key = _text(g.label, locale, g.code)
        status = (
            translate(f"project_handbook.gate_status.{g.status}", locale=locale)
            if _has(f"project_handbook.gate_status.{g.status}")
            else g.status
        )
        when = f", {g.target_date.isoformat()}" if g.target_date else ""
        rows.append(LinkedRow(label=text, detail=f"{status}{when}", label_key=key))
    return rows


async def _governance_areas(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.project_governance import public as governance

    rows: list[LinkedRow] = []
    for a in await governance.project_areas(session, project_id):
        if a.status != "applicable":
            continue
        text, key = _text(a.label, locale, a.code)
        rows.append(LinkedRow(label=a.name_override or text, label_key=None if a.name_override else key))
    return rows


async def _data_room(session: AsyncSession, project_id: uuid.UUID, locale: str) -> list[LinkedRow]:
    from app.modules.project_handbook.data_room import area_summary

    rows: list[LinkedRow] = []
    for item in await area_summary(session, project_id):
        text, key = _text(item["label"], locale, item["area_code"])
        rows.append(
            LinkedRow(
                label=item["name_override"] or text,
                detail=f"{item['folders']} / {item['documents']}",
                label_key=None if item["name_override"] else key,
            )
        )
    return rows


register_source("stakeholders", _stakeholders, "/projects/{project_id}/stakeholders")
register_source("staffing", _staffing, "/projects/{project_id}/staffing")
register_source("engineering_brief", _engineering_brief, "/projects/{project_id}/engineering-brief")
register_source("governance_gates", _governance_gates, "/projects/{project_id}/governance")
register_source("governance_areas", _governance_areas, "/projects/{project_id}/governance")
register_source("data_room", _data_room, "/projects/{project_id}/handbook?tab=data_room")
