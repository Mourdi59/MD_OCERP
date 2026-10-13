# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The people a demo project needs besides its owner.

A demo project is installed with one person on it, its owner. Stories that
show a decision need a second one: under four-eyes whoever owns an area cannot
decide its gate, so a project with nobody but its owner cannot pass a single
gate, and every seeder that tells a story across gates has nothing to tell.

Where the installation carries the product's demo logins (the boot seeder
creates them when the demo is enabled) those play the parts, so the viewer can
sign in as the person who decides. Where it does not, because the operator
declined the demo accounts or a pack was installed on a workspace of real
people, this module creates stand-ins:

* they are tagged ``metadata.demo_cast`` and removed once the last demo
  project is purged (:func:`remove_demo_cast`);
* they cannot sign in. Their password is a random secret nobody is told, and
  they are deliberately NOT among the logins of ``app.core.demo_accounts``:
  that list is the whitelist of the passwordless demo sign-in, and creating
  one of those on an installation that declined them would open a
  password-free manager session to anyone who can reach the port;
* they live on ``example.com``, which the mail guard already refuses
  (``is_reserved_mail_domain``), so a notification to one never leaves.

Every seeder may count on the same three people on a demo project, all of them
on its team before the first module seeder runs:

* the owner (``Project.owner_id``);
* ``cost``, the second person of every four-eyes step. It is the FIRST team
  membership of the project that is not the owner, by ``created_at``, so a
  seeder that looks for "another member" finds this one;
* ``decider``, who decides and owns nothing, the second such membership.

Nothing here raises for a part that cannot be filled: the caller reads which
parts exist and reports the rest.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: The key on ``User.metadata_`` that marks a stand-in this module created.
CAST_TAG = "demo_cast"

#: The project team the cast is put on when it is not on the project yet.
TEAM_NAME = "Governance board"

#: The order the cast joins a project in. ``cost`` first: see the module docstring.
JOIN_ORDER: tuple[str, ...] = ("cost", "decider")


@dataclass(frozen=True)
class CastPart:
    """One part of the cast.

    Attributes:
        word: What the stories call the part.
        demo_login: The product's demo login that plays it where it exists.
        email: The address of the stand-in created where it does not.
        full_name: The stand-in's name: the part, not a person.
        role: The stand-in's role.
    """

    word: str
    demo_login: str
    email: str
    full_name: str
    role: str


#: ``decider`` decides gates and never owns an area. ``cost`` owns the cost and
#: schedule areas and is the second plain member of the project.
CAST: tuple[CastPart, ...] = (
    CastPart("decider", "manager@openconstructionerp.com", "demo-decider@example.com", "Demo decider", "manager"),
    CastPart("cost", "estimator@openconstructionerp.com", "demo-cost-owner@example.com", "Demo cost owner", "editor"),
)


def _is_stand_in(user: Any) -> bool:
    return isinstance(user.metadata_, dict) and bool(user.metadata_.get(CAST_TAG))


async def _by_email(session: AsyncSession, email: str) -> Any | None:
    from app.modules.users.models import User

    return (await session.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()


async def _player(session: AsyncSession, part: CastPart) -> Any | None:
    """Who plays a part today: the active demo login, else the active stand-in."""
    login = await _by_email(session, part.demo_login)
    if login is not None and login.is_active:
        return login
    stand_in = await _by_email(session, part.email)
    if stand_in is not None and stand_in.is_active and _is_stand_in(stand_in):
        return stand_in
    return None


async def find_cast(session: AsyncSession) -> dict[str, uuid.UUID]:
    """The parts that are filled, by word. Reads only.

    Args:
        session: Open session.

    Returns:
        ``{"decider": user id, "cost": user id}`` with a key missing for a part
        nobody plays.
    """
    found: dict[str, uuid.UUID] = {}
    for part in CAST:
        player = await _player(session, part)
        if player is not None:
            found[part.word] = player.id
    return found


async def join_project(session: AsyncSession, project_id: uuid.UUID) -> int:
    """Put the cast on the team of one demo project, in :data:`JOIN_ORDER`. Idempotent.

    Memberships go through ``TeamService`` as the project owner, the way a
    user would add a colleague. A player who is the owner, or already a member
    of any team of the project, is left as found.

    Args:
        session: Open session; the caller commits.
        project_id: A demo project.

    Returns:
        The number of memberships written.
    """
    from app.modules.projects.models import Project
    from app.modules.teams.access import is_project_member
    from app.modules.teams.models import Team
    from app.modules.teams.schemas import AddMemberRequest, TeamCreate
    from app.modules.teams.service import TeamService

    project = await session.get(Project, project_id)
    if project is None or project.owner_id is None:
        return 0
    players = await find_cast(session)
    missing = [
        players[word]
        for word in JOIN_ORDER
        if word in players
        and players[word] != project.owner_id
        and not await is_project_member(session, project_id, players[word])
    ]
    if not missing:
        return 0
    teams = TeamService(session)
    team = (
        await session.execute(select(Team).where(Team.project_id == project_id, Team.name == TEAM_NAME))
    ).scalar_one_or_none()
    if team is None:
        team = await teams.create_team(TeamCreate(project_id=project_id, name=TEAM_NAME), actor_id=project.owner_id)
    for user_id in missing:
        await teams.add_member(team.id, AddMemberRequest(user_id=user_id), actor_id=project.owner_id)
    return len(missing)


async def ensure_demo_cast(session: AsyncSession, project_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
    """Fill every part nobody plays yet with a stand-in and put the cast on the demo projects.

    Idempotent; the caller commits. A stand-in address that already belongs to
    an account this module did not create is left alone, and the part is
    reported as blocked. A project the cast could not join is reported and
    does not stop the others.

    Args:
        session: Open session.
        project_ids: The demo projects whose team the cast joins.

    Returns:
        ``{"present": [...], "created": [...], "blocked": [...], "memberships": n,
        "not_joined": [project ids], "ok": bool}``. The first three list the
        words of the parts; ``ok`` is true when every part is played and every
        project was joined.
    """
    from app.modules.users.models import User
    from app.modules.users.service import hash_password

    result: dict[str, Any] = {"present": [], "created": [], "blocked": []}
    for part in CAST:
        if await _player(session, part) is not None:
            result["present"].append(part.word)
            continue
        taken = await _by_email(session, part.email)
        if taken is not None and not _is_stand_in(taken):
            result["blocked"].append(part.word)
            continue
        if taken is not None:
            # A stand-in of an earlier demo that was switched off: it plays again.
            taken.is_active = True
        else:
            session.add(
                User(
                    id=uuid.uuid4(),
                    email=part.email,
                    hashed_password=hash_password(secrets.token_urlsafe(32)),
                    full_name=part.full_name,
                    role=part.role,
                    locale="en",
                    is_active=True,
                    metadata_={CAST_TAG: part.word},
                )
            )
        await session.flush()
        result["created"].append(part.word)
    result["memberships"] = 0
    result["not_joined"] = []
    for project_id in project_ids or []:
        try:
            async with session.begin_nested():
                result["memberships"] += await join_project(session, project_id)
        except Exception:
            logger.warning("demo cast: could not join project %s", project_id, exc_info=True)
            result["not_joined"].append(str(project_id))
    result["ok"] = not result["blocked"] and not result["not_joined"]
    if result["created"]:
        logger.info("demo cast: stand-ins created for %s", ", ".join(result["created"]))
    return result


async def remove_demo_cast(session: AsyncSession) -> int:
    """Delete the stand-ins once no demo project is left. The caller commits.

    While a demo project exists the stand-ins stay: they are named on its
    decisions and its areas. The product's demo logins are never touched here.

    Args:
        session: Open session.

    Returns:
        The number of stand-ins removed.
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    metadata = (await session.execute(select(Project.metadata_))).scalars().all()
    if any(demo_id_of(m) for m in metadata):
        return 0
    emails = [part.email for part in CAST]
    rows = (await session.execute(select(User).where(func.lower(User.email).in_(emails)))).scalars().all()
    ids = [u.id for u in rows if _is_stand_in(u)]
    if not ids:
        return 0
    await session.execute(delete(User).where(User.id.in_(ids)))
    await session.flush()
    session.expire_all()
    logger.info("demo cast: %d stand-in(s) removed with the last demo project", len(ids))
    return len(ids)
