# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The people who own the areas of a pack demo project.

A demo project is told with the product's two demo logins, so without more every
area would read the same owner. The pack's demo file may list ``people`` for a
project: invented names, each owning one area. This step runs after the module
seeders, so the story itself is still told by the demo logins and only its result
is renamed: the area gets the person as owner, the open conditions of the area
move to them, and the person appears on the project roster under the same name the
staffing story gave them, so one name means one person across the modules.

A person is a user row that nobody can sign in as: inactive, with a password hash of
a random value that is thrown away. It exists because an area owner is a user id and
the roster names people by it. It is created only for a project the active pack's
demo file names with a ``people`` list, never for any other project, and it is
marked ``demo_person`` in its metadata. Idempotent: a person that exists is reused.
"""

from __future__ import annotations

import logging
import re
import secrets
import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Mail domain of a demo person. Reserved for documentation, so no mail ever reaches anybody.
PEOPLE_DOMAIN = "demo-people.example.org"


def person_email(key: str) -> str:
    """The address of a demo person from the ASCII key the demo file gives them."""
    slug = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode("ascii").lower()
    return f"{re.sub(r'[^a-z0-9.]+', '.', slug).strip('.')}@{PEOPLE_DOMAIN}"


def parse_people(entry: dict[str, Any] | None, locale: str) -> list[dict[str, str]]:
    """The usable ``people`` rows of a demo file entry: ``key``, ``name``, ``company``, ``area``.

    A row needs all of ``key``, ``name`` and ``area``; one that lacks any is dropped with an info line, and so is a second
    row for an area already taken, because an area has one owner.
    """
    from app.modules.project_governance.seed_story import text_of

    rows = (entry or {}).get("people")
    out: list[dict[str, str]] = []
    taken: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            logger.info("governance demo people: row %r is not usable, dropped", row)
            continue
        key, area = row.get("key"), row.get("area")
        name = text_of(row.get("name"), locale)
        if not (isinstance(key, str) and key.strip() and isinstance(area, str) and name) or area in taken:
            logger.info("governance demo people: row %r is not usable, dropped", row)
            continue
        taken.add(area)
        out.append({"key": key.strip(), "name": name, "company": text_of(row.get("company"), locale), "area": area})
    return out


async def _person_user(session: AsyncSession, person: dict[str, str], locale: str) -> uuid.UUID:
    """The user row of a demo person, created when it does not exist yet. Nobody can sign in as it."""
    import bcrypt

    from app.modules.users.models import User

    email = person_email(person["key"])
    found = (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    if found is not None:
        return found
    # A real hash of a value nobody holds: the row stays unusable even if it were ever switched on.
    unusable = bcrypt.hashpw(secrets.token_hex(24).encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")
    user = User(
        email=email,
        hashed_password=unusable,
        full_name=person["name"],
        role="viewer",
        locale=locale,
        is_active=False,
        metadata_={"demo_person": True},
    )
    session.add(user)
    await session.flush()
    return user.id


async def _roster_line(
    session: AsyncSession, project_id: uuid.UUID, person: dict[str, str], user_id: uuid.UUID
) -> None:
    """Put the person on the project roster: the line the staffing story wrote under their name, else a new one."""
    from app.modules.teams.models import RosterMember, Team

    taken = (
        await session.execute(
            select(RosterMember.id).where(RosterMember.project_id == project_id, RosterMember.user_id == user_id)
        )
    ).scalar_one_or_none()
    if taken is not None:
        return
    line = (
        await session.execute(
            select(RosterMember)
            .where(
                RosterMember.project_id == project_id,
                RosterMember.display_name == person["name"],
                RosterMember.user_id.is_(None),
                RosterMember.contact_id.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if line is not None:
        line.user_id = user_id
        return
    teams = list((await session.execute(select(Team).where(Team.project_id == project_id))).scalars().all())
    team = next((t for t in teams if t.is_default), teams[0] if teams else None)
    session.add(
        RosterMember(
            project_id=project_id,
            team_id=team.id if team is not None else None,
            user_id=user_id,
            display_name=person["name"],
            company_name=person["company"],
        )
    )


async def _stakeholder_relationship_owners(
    session: AsyncSession, project_id: uuid.UUID, areas: dict[str, Any], people_ids: set[uuid.UUID]
) -> None:
    """Let the person who owns the stakeholder area also own the relationships of the register.

    The stakeholder register is seeded with the demo logins as relationship owners, which shows the
    placeholder names of those accounts on a filmed page. Rows already held by a demo person stay.
    A project whose model hosts no stakeholder area, or an install without the module, is left alone.
    """
    from app.modules.project_governance.public import host_for

    host = await host_for(session, project_id, "stakeholders")
    area = areas.get(host.area_code) if host is not None else None
    if area is None or area.owner_user_id is None:
        return
    try:
        from app.modules.stakeholders.models import Stakeholder
    except ImportError:
        return
    for row in (await session.execute(select(Stakeholder).where(Stakeholder.project_id == project_id))).scalars():
        if row.relationship_owner_user_id is not None and row.relationship_owner_user_id not in people_ids:
            row.relationship_owner_user_id = area.owner_user_id


async def assign_demo_people(session: AsyncSession, project_ids: list[uuid.UUID]) -> dict[str, int]:
    """Give each area of a pack demo project its own named owner. The caller commits. Run AFTER the module seeders.

    Returns:
        ``{"projects": n, "areas": m}``: the projects that carry a ``people`` list and the areas that got an owner.
    """
    from app.modules.project_governance import catalogue_packs, seed_story
    from app.modules.project_governance.models import GovernanceArea, GovernanceCondition
    from app.modules.project_handbook.models import HandbookChapter
    from app.modules.projects.models import Project

    totals = {"projects": 0, "areas": 0}
    _file, data = catalogue_packs.active_pack_demo_reading()
    for project_id in project_ids:
        project = await session.get(Project, project_id)
        meta = getattr(project, "metadata_", None)
        demo_id = meta.get("demo_id") if isinstance(meta, dict) else None
        locale = getattr(project, "locale", None) or "en"
        people = parse_people(seed_story.entry_for(data, demo_id), locale)
        if not people:
            continue
        areas = {
            a.code: a
            for a in (
                await session.execute(
                    select(GovernanceArea).where(
                        GovernanceArea.project_id == project_id, GovernanceArea.retired.is_(False)
                    )
                )
            ).scalars()
        }
        done = 0
        people_ids: set[uuid.UUID] = set()
        for person in people:
            area = areas.get(person["area"])
            if area is None:
                logger.info(
                    "governance demo people: %s names area %s, which the project has not", person["key"], person["area"]
                )
                continue
            user_id = await _person_user(session, person, locale)
            people_ids.add(user_id)
            await _roster_line(session, project_id, person, user_id)
            before = area.owner_user_id
            area.owner_user_id = user_id
            if before is not None and before != user_id:
                # The conditions the area's owner held follow the area; nobody else's are touched.
                for cond in (
                    await session.execute(
                        select(GovernanceCondition).where(
                            GovernanceCondition.project_id == project_id,
                            GovernanceCondition.area_code == area.code,
                            GovernanceCondition.owner_user_id == before,
                        )
                    )
                ).scalars():
                    cond.owner_user_id = user_id
            # The chapters of the area's handbook are written by the same person.
            for chapter in (
                await session.execute(
                    select(HandbookChapter).where(
                        HandbookChapter.project_id == project_id, HandbookChapter.area_code == area.code
                    )
                )
            ).scalars():
                chapter.owner_id = user_id
            done += 1
        if done:
            await _stakeholder_relationship_owners(session, project_id, areas, people_ids)
        await session.flush()
        if done:
            totals["projects"] += 1
            totals["areas"] += done
    return totals
