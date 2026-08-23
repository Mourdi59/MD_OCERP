# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Interface-register demo seed - a populated coordination register per project.

Opens the Interfaces page on a register a coordinator would recognise: a
couple of dozen handshakes between two work packages, each owned by one party
and accepted by another, running from ``identified`` through ``agreed`` to
``closed``, with a few overdue and one or two in dispute, and the actions that
have to happen before each one can be signed off.

Nothing here invents an organisation. Both sides of every interface are drawn
from the subcontractors the demo already carries (falling back to the contact
book), the work-package names come from those firms' own trade categories, and
the ``owner_subcontractor_id`` soft link points at the very row whose name is
printed - so the text and the link always tell the same story even after the
firm names are rewritten.

The register is internally consistent, because the module's whole point is the
numbers derived from it (:mod:`app.modules.interface_management.register`
computes overdue, agreed percent and per-package health from these rows):

* ``agreed`` carries an agreed date and no closing date;
* ``closed`` carries both, in that order, and has no open actions left;
* ``identified`` / ``open`` / ``in_progress`` / ``disputed`` / ``on_hold``
  carry neither;
* a handful are deliberately past their need-by date and unsettled, so the
  overdue tile is not a zero and the work-package health view has something to
  report.

Dates are anchored to the run date, never hardcoded, so a demo opened a year
from now still shows a register with live deadlines.

Idempotent per project: a project that already carries an interface is left
untouched, so a re-run never doubles the register.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interface_management.models import InterfaceAction, InterfaceRecord
from app.modules.interface_management.register import (
    ActionStatus,
    InterfaceStatus,
    InterfaceType,
    Priority,
    can_be_overdue,
)

logger = logging.getLogger(__name__)

_SEED = 42

# How many interfaces a project's register carries, indexed by the project's
# position in the seeding call rather than drawn from its id, so two demo
# projects opened side by side are never the same size. Past the end of the
# tuple the position wraps and a whole span is added, which keeps the mapping
# injective instead of putting a later project back on an earlier one's count.
_REGISTER_SIZES = (18, 14, 22, 16)
_SIZE_SPAN = max(_REGISTER_SIZES) - min(_REGISTER_SIZES) + 1

# How many parties a register needs before it means anything: an interface is a
# handshake, and a handshake needs two different sides.
_MIN_PARTIES = 2

# The discipline each subcontractor trade answers for. An interface's two
# disciplines have to follow from its two work packages, or the register reads
# as two unrelated columns.
_TRADE_DISCIPLINE: dict[str, str] = {
    "earthworks": "Civil",
    "concrete": "Structural",
    "steel_erection": "Structural",
    "carpentry": "Architectural",
    "roofing": "Architectural",
    "waterproofing": "Architectural",
    "facade": "Facade",
    "drywall": "Architectural",
    "tiling": "Architectural",
    "painting": "Architectural",
    "plumbing": "Plumbing",
    "hvac": "Mechanical",
    "electrical": "Electrical",
    "fire_protection": "Fire protection",
    "elevators": "Vertical transport",
    "scaffolding": "Temporary works",
    "demolition": "Civil",
    "landscaping": "Landscape",
    "asphalt": "Civil",
    "joinery": "Architectural",
}
_DEFAULT_DISCIPLINE = "Architectural"

# One title and one description per interface family, filled with the two work
# packages actually involved. A coordinator reads the title first and has to
# know from it what the handshake is about.
_SUBJECTS: dict[str, tuple[str, str]] = {
    InterfaceType.PHYSICAL.value: (
        "{a} penetrations through {b} elements",
        "{a} services pass through elements built by {b}. Sizes, positions and "
        "sleeve details have to be agreed before the {b} elements are cast or "
        "closed up.",
    ),
    InterfaceType.FUNCTIONAL.value: (
        "{a} supply to {b} equipment",
        "Equipment installed by {b} is fed by {a}. Connection points, capacity "
        "and the control interface have to be agreed so both sides order the "
        "same thing.",
    ),
    InterfaceType.CONTRACTUAL.value: (
        "Scope boundary between {a} and {b}",
        "The scope split between the {a} and {b} packages is not written down "
        "anywhere both sides accept. Agree who supplies, who installs and who "
        "commissions at the boundary.",
    ),
    InterfaceType.SPATIAL.value: (
        "Shared route and access between {a} and {b}",
        "{a} and {b} need the same space and the same access route. Agree the "
        "allocation and the sequence before either sets out on site.",
    ),
    InterfaceType.INFORMATION.value: (
        "{a} to issue coordinated information to {b}",
        "{b} cannot proceed until {a} issues coordinated setting-out and "
        "builder's work information. Agree the content and the issue date.",
    ),
    InterfaceType.SCHEDULE.value: (
        "{b} start depends on {a} completion",
        "{b} cannot start on this area until {a} is complete and handed over. "
        "Agree the handover date and what counts as complete.",
    ),
}

# What each side has to do before the handshake can be signed off. Two open
# actions per unsettled interface reads like a live to-do list; a settled one
# has them all closed out.
_ACTION_TEMPLATES: tuple[str, ...] = (
    "{a} to issue the coordinated drawing for review.",
    "{b} to confirm the interface details are acceptable.",
    "Both parties to walk the location and record the agreed arrangement.",
    "{a} to update the model and reissue for sign-off.",
    "{b} to confirm the agreed date works against its own programme.",
)

# Lifecycle weights. A live register is mostly work in flight with a settled
# tail behind it, not an even split across seven states.
_STATUS_WEIGHTS: tuple[tuple[str, int], ...] = (
    (InterfaceStatus.CLOSED.value, 5),
    (InterfaceStatus.AGREED.value, 3),
    (InterfaceStatus.IN_PROGRESS.value, 5),
    (InterfaceStatus.OPEN.value, 4),
    (InterfaceStatus.IDENTIFIED.value, 3),
    (InterfaceStatus.DISPUTED.value, 1),
    (InterfaceStatus.ON_HOLD.value, 1),
)

# Statuses that make an interface settled: it needs its dates and it must not
# leave an open action behind.
_SETTLED = frozenset({InterfaceStatus.AGREED.value, InterfaceStatus.CLOSED.value})

# The first four positions of every register are reserved rather than drawn.
# Left entirely to the weighted draw, everything the demo screens are built
# around is a lottery a small register loses often enough to matter: about one
# register in eighty came back with nothing overdue at all and the tile then
# photographed as a zero, one in twenty-five hundred had nothing settled, and
# one in three thousand sat in fewer than four statuses. The reserved prefix
# carries both settled statuses and two different unsettled ones, so the agreed
# figure, the overdue tile and the status breakdown all have something behind
# them by construction. Every position past the prefix still draws.
_RESERVED_OVERDUE_INDEX = 1

# The two reserved pools, filtered out of the weights above so the statuses
# stay enumerated in exactly one place. Which statuses can carry an overdue row
# is the register's rule, not ours - asking it is what keeps a status it
# exempts (on_hold) from being handed a past date and counted on as overdue.
_SETTLED_STATUSES: tuple[str, ...] = tuple(status for status, _weight in _STATUS_WEIGHTS if status in _SETTLED)
_OVERDUE_CAPABLE_STATUSES: tuple[str, ...] = tuple(
    status for status, _weight in _STATUS_WEIGHTS if can_be_overdue(status)
)

# Priorities, weighted so critical stays rare enough to mean something.
_PRIORITY_WEIGHTS: tuple[tuple[str, int], ...] = (
    (Priority.CRITICAL.value, 1),
    (Priority.HIGH.value, 3),
    (Priority.MEDIUM.value, 5),
    (Priority.LOW.value, 2),
)


class _Party:
    """One side of a handshake: a firm, its work package and its discipline."""

    __slots__ = ("discipline", "name", "subcontractor_id", "work_package")

    def __init__(
        self,
        name: str,
        work_package: str,
        discipline: str,
        subcontractor_id: uuid.UUID | None,
    ) -> None:
        self.name = name
        self.work_package = work_package
        self.discipline = discipline
        self.subcontractor_id = subcontractor_id


def _is_demo_project(metadata: object) -> bool:
    """Whether a project row's metadata marks it as a demo project.

    Both installers that create demo projects stamp ``demo_id``: the showcase
    templates in ``app/core/demo_projects.py`` and the flagship in
    ``app/scripts/seed_flagship.py``. Nothing else writes that key, so its
    presence is what separates a project we may fill with invented interfaces
    from a project somebody is actually building. Read ``demo_id`` and not
    ``is_demo``: the flagship carries the former and not the latter.
    """
    return isinstance(metadata, dict) and bool(str(metadata.get("demo_id") or "").strip())


def _rng_for(project_id: uuid.UUID) -> random.Random:
    """A deterministic RNG per project, so a re-seed reproduces the register."""
    return random.Random(f"{_SEED}:{project_id}")


def _weighted(rng: random.Random, weights: Sequence[tuple[str, int]]) -> str:
    """Draw one value from ``(value, weight)`` pairs."""
    values = [value for value, _ in weights]
    return rng.choices(values, weights=[weight for _, weight in weights], k=1)[0]


def _reserved_statuses(rng: random.Random) -> tuple[str, ...]:
    """The statuses the reserved prefix carries, in register order.

    Both settled statuses and two different unsettled ones, interleaved so the
    register does not open on a block of closed rows. Which of the two lands
    where is still drawn, so two projects do not read identically; that the
    four are four different statuses is not. Position
    ``_RESERVED_OVERDUE_INDEX`` holds an unsettled one, which is what makes it
    safe to date that row into the past and count on it being overdue.
    """
    settled = rng.sample(_SETTLED_STATUSES, k=2)
    unsettled = rng.sample(_OVERDUE_CAPABLE_STATUSES, k=2)
    # The unsettled pair straddles the reserved overdue position rather than
    # sitting at a hardcoded offset, so that position carries a status the
    # register can call overdue whatever the constant is moved to. Writing the
    # order out by hand instead would leave the guarantee resting on two
    # numbers agreeing, which is the way this seeder went wrong before.
    reserved = [settled[0], settled[1]]
    reserved.insert(_RESERVED_OVERDUE_INDEX, unsettled[0])
    reserved.append(unsettled[1])
    return tuple(reserved)


_ENUM_TOKEN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def _package_label(trade: str) -> str:
    """Turn a trade category key into the work-package name people write.

    Only a key gets recased. A trade category arrives from two places: the
    lowercase snake_case pool above, where "fire_protection" has to become
    "Fire Protection" for anyone to read it, and the ``trade_categories``
    column of a real subcontractor row, which holds whatever text the register
    was set up with. The demo writes a section title into that column, so the
    second kind reaches here as "LV 01 - Baustelleneinrichtung und
    Gemeinkosten", and ``str.title()`` lowercases the tail of every word it
    touches. The register printed "Lv 01".

    An initialism cannot be recovered once it has been folded, and no caser can
    be told which tokens are initialisms, so the rule is not to recase text that
    was already written for a reader. Anything that is not a bare snake_case
    token is passed through as it stands. The casing of the keys is left exactly
    as it was, so the twenty work packages that were already right stay right.
    """
    trade = trade.strip()
    if not _ENUM_TOKEN.match(trade):
        return trade
    return trade.replace("_", " ").title()


async def _subcontractor_parties(session: AsyncSession) -> list[_Party]:
    """Build the party pool from the subcontractors the demo already carries.

    The name is read from the row rather than composed here, so the register
    keeps agreeing with the vendor list even when those firms are renamed.
    """
    try:
        from app.modules.subcontractors.models import Subcontractor

        stmt = (
            select(Subcontractor.id, Subcontractor.legal_name, Subcontractor.trade_categories)
            .where(Subcontractor.is_active.is_(True))
            .order_by(Subcontractor.legal_name)
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        logger.debug("Subcontractor lookup unavailable for the interface register")
        return []

    parties: list[_Party] = []
    for sub_id, legal_name, trades in rows:
        name = str(legal_name or "").strip()
        trade_list = [str(t) for t in (trades or []) if str(t).strip()]
        if not name or not trade_list:
            continue
        trade = trade_list[0]
        parties.append(
            _Party(
                name=name,
                work_package=_package_label(trade),
                discipline=_TRADE_DISCIPLINE.get(trade, _DEFAULT_DISCIPLINE),
                subcontractor_id=sub_id,
            ),
        )
    return parties


async def _contact_parties(session: AsyncSession) -> list[_Party]:
    """Fall back to the contact book when no subcontractor is registered.

    A contact is not a subcontractor row, so the soft link stays ``None``
    rather than pointing at a table the id does not belong to.
    """
    try:
        from app.modules.contacts.models import Contact

        stmt = (
            select(Contact.company_name)
            .where(Contact.company_name.isnot(None))
            .order_by(Contact.company_name)
            .limit(12)
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        logger.debug("Contact lookup unavailable for the interface register")
        return []

    parties: list[_Party] = []
    seen: set[str] = set()
    trades = list(_TRADE_DISCIPLINE)
    for (company,) in rows:
        name = str(company or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        trade = trades[len(parties) % len(trades)]
        parties.append(
            _Party(
                name=name,
                work_package=_package_label(trade),
                discipline=_TRADE_DISCIPLINE[trade],
                subcontractor_id=None,
            ),
        )
    return parties


async def _project_locations(session: AsyncSession, project_id: uuid.UUID) -> list[str]:
    """Return the storey names this project's BIM models actually carry.

    An interface is somewhere. Where that somewhere can be named from the
    project's own model it is; where it cannot, the location column is left
    empty rather than filled with a grid reference no drawing shows.
    """
    try:
        from app.modules.bim_hub.models import BIMElement, BIMModel

        stmt = (
            select(BIMElement.storey)
            .join(BIMModel, BIMElement.model_id == BIMModel.id)
            .where(BIMModel.project_id == project_id, BIMElement.storey.isnot(None))
            .distinct()
            .limit(12)
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        logger.debug("Storey lookup unavailable for project=%s", project_id)
        return []
    return sorted({str(storey).strip() for (storey,) in rows if str(storey or "").strip()})


async def _project_rfi_ids(session: AsyncSession, project_id: uuid.UUID) -> list[str]:
    """Return this project's own RFI ids, for the interfaces raised through one.

    Only ids that already exist are linked, so the seeder never depends on the
    RFI register being written first.
    """
    try:
        from app.modules.rfi.models import RFI

        stmt = select(RFI.id).where(RFI.project_id == project_id).order_by(RFI.id).limit(8)
        rows = (await session.execute(stmt)).scalars().all()
    except Exception:
        logger.debug("RFI lookup unavailable for project=%s", project_id)
        return []
    return [str(rfi_id) for rfi_id in rows]


def _dates_for(
    rng: random.Random,
    status: str,
    *,
    today: date,
    overdue: bool,
) -> tuple[date, date | None, date | None]:
    """Return ``(need_by, agreed, closed)`` consistent with ``status``.

    An interface is agreed before it is closed and neither happens while it is
    still being argued about, so the two settlement dates only exist on the two
    settled statuses and always run in that order.
    """
    if status == InterfaceStatus.CLOSED.value:
        need_by = today - timedelta(days=rng.randint(20, 150))
        agreed = need_by - timedelta(days=rng.randint(0, 12))
        closed = agreed + timedelta(days=rng.randint(1, 15))
        if closed > today:
            closed = today
        return need_by, agreed, closed
    if status == InterfaceStatus.AGREED.value:
        need_by = today + timedelta(days=rng.randint(-30, 45))
        agreed = today - timedelta(days=rng.randint(1, 25))
        return need_by, agreed, None
    if overdue:
        # Unsettled and already past its date - the rows the overdue tile and
        # the work-package health view exist to surface.
        return today - timedelta(days=rng.randint(3, 40)), None, None
    return today + timedelta(days=rng.randint(5, 120)), None, None


def _actions_for(
    rng: random.Random,
    *,
    status: str,
    need_by: date,
    closed_date: date | None,
    owner: _Party,
    accepter: _Party,
    today: date,
) -> list[tuple[str, str, str | None, date | None, date | None]]:
    """Build one interface's actions as ``(description, status, party, due, done)``.

    A settled interface has nothing left open - an interface signed off with
    somebody still owing a drawing is the state this register exists to
    prevent - so its actions are all done, dated before it was settled. An
    unsettled one keeps one or two open against its need-by date.
    """
    count = rng.randint(2, 4)
    picks = rng.sample(_ACTION_TEMPLATES, k=min(count, len(_ACTION_TEMPLATES)))
    settled = status in _SETTLED
    out: list[tuple[str, str, str | None, date | None, date | None]] = []

    for index, template in enumerate(picks):
        description = template.format(a=owner.work_package, b=accepter.work_package)
        party = owner.name if index % 2 == 0 else accepter.name
        due = need_by - timedelta(days=rng.randint(3, 25))
        if settled:
            ceiling = closed_date or today
            completed = min(due + timedelta(days=rng.randint(0, 8)), ceiling)
            out.append((description, ActionStatus.DONE.value, party, due, completed))
            continue
        # Older items on an unsettled interface are already ticked off; the
        # newest one or two are what is actually holding it up.
        if index < len(picks) - 2:
            out.append(
                (
                    description,
                    ActionStatus.DONE.value,
                    party,
                    due,
                    min(due + timedelta(days=rng.randint(0, 6)), today),
                ),
            )
        else:
            out.append((description, ActionStatus.OPEN.value, party, due, None))
    return out


async def _seed_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    parties: Sequence[_Party],
    ordinal: int,
) -> dict[str, int]:
    """Seed one project's register. Returns per-entity counts (zeros when skipped)."""
    empty = {"projects": 0, "interfaces": 0, "actions": 0}

    already = (
        (
            await session.execute(
                select(InterfaceRecord.id).where(InterfaceRecord.project_id == project_id).limit(1),
            )
        )
        .scalars()
        .first()
    )
    if already is not None:
        return empty

    rng = _rng_for(project_id)
    slot = ordinal % len(_REGISTER_SIZES)
    size = _REGISTER_SIZES[slot] + (ordinal // len(_REGISTER_SIZES)) * _SIZE_SPAN
    locations = await _project_locations(session, project_id)
    rfi_ids = await _project_rfi_ids(session, project_id)
    types = [t.value for t in InterfaceType]
    today = datetime.now(UTC).date()
    reserved = _reserved_statuses(rng)

    counts = {"projects": 1, "interfaces": 0, "actions": 0}
    for index in range(size):
        owner, accepter = rng.sample(list(parties), k=2)
        interface_type = types[index % len(types)]
        title_template, description_template = _SUBJECTS[interface_type]
        status = reserved[index] if index < len(reserved) else _weighted(rng, _STATUS_WEIGHTS)
        # Roughly one unsettled interface in four has run past its date, and
        # the reserved position always does. Asking the register which statuses
        # can be overdue rather than reusing _SETTLED matters: a paused
        # (on_hold) row handed a past date is never counted overdue by the
        # report, so treating it as one silently shrank the tile.
        overdue = can_be_overdue(status) and (index == _RESERVED_OVERDUE_INDEX or index % 4 == 1)
        need_by, agreed_date, closed_date = _dates_for(rng, status, today=today, overdue=overdue)

        interface = InterfaceRecord(
            project_id=project_id,
            reference=f"IF-{index + 1:03d}",
            title=title_template.format(a=owner.work_package, b=accepter.work_package),
            description=description_template.format(a=owner.work_package, b=accepter.work_package),
            owner_party=owner.name,
            owner_subcontractor_id=owner.subcontractor_id,
            accepter_party=accepter.name,
            accepter_subcontractor_id=accepter.subcontractor_id,
            discipline_from=owner.discipline,
            discipline_to=accepter.discipline,
            work_package_from=owner.work_package,
            work_package_to=accepter.work_package,
            interface_type=interface_type,
            status=status,
            priority=_weighted(rng, _PRIORITY_WEIGHTS),
            need_by_date=need_by,
            agreed_date=agreed_date,
            closed_date=closed_date,
            rfi_id=rng.choice(rfi_ids) if rfi_ids and index % 5 == 2 else None,
            location=rng.choice(locations) if locations else None,
            sort_order=index,
        )
        session.add(interface)
        await session.flush()
        counts["interfaces"] += 1

        for description, action_status, party, due, completed in _actions_for(
            rng,
            status=status,
            need_by=need_by,
            closed_date=closed_date,
            owner=owner,
            accepter=accepter,
            today=today,
        ):
            session.add(
                InterfaceAction(
                    project_id=project_id,
                    interface_id=interface.id,
                    description=description,
                    action_party=party,
                    due_date=due,
                    status=action_status,
                    completed_date=completed,
                ),
            )
            counts["actions"] += 1
    await session.flush()
    return counts


async def seed_interface_management_demo(
    session: AsyncSession,
    project_ids: Iterable[uuid.UUID],
) -> dict[str, int]:
    """Populate the interface coordination register for the given demo projects.

    Args:
        session: Async DB session. The caller commits.
        project_ids: Candidate projects. Anything that is not a demo project is
            skipped outright; a demo project is skipped when it already carries
            an interface. Every demo project given is seeded - there is no cap.

    Returns:
        Dict with per-entity insert counts across every project seeded. Empty
        counts when the estate has fewer than two parties to put on the two
        sides of a handshake.
    """
    totals = {"projects": 0, "interfaces": 0, "actions": 0}
    ids = list(project_ids)
    if not ids:
        return totals

    from app.modules.projects.models import Project

    # The caller hands us every project in the database, not only demo ones,
    # and the backfill around it re-runs once per app version - so it fires
    # again on every upgrade. That makes "carries no interface yet" the wrong
    # gate on its own: a real customer project that has logged no interfaces is
    # also empty of them, and would receive a register of invented handshakes
    # between firms on their next upgrade. Demo projects are marked, so read
    # the marker. Emptiness stays on top of this as the idempotency guard.
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    demo_ids = {pid for pid, meta in rows if _is_demo_project(meta)}
    # Filtering before the enumerate keeps the ordinal dense, so the register
    # size a project draws never depends on how many projects that are not
    # being seeded happen to sort ahead of it.
    ids = [pid for pid in ids if pid in demo_ids]
    if not ids:
        return totals

    parties = await _subcontractor_parties(session)
    if len(parties) < _MIN_PARTIES:
        parties = await _contact_parties(session)
    if len(parties) < _MIN_PARTIES:
        # Every interface names two sides. Without two firms on file there is
        # nothing honest to put in those columns, so the register stays empty
        # rather than being filled with organisations that do not exist.
        logger.debug("Interface register demo skipped: only %d part(y/ies) on file", len(parties))
        return totals

    for ordinal, project_id in enumerate(ids):
        try:
            # A SAVEPOINT per project, so one project that cannot be seeded
            # costs only its own rows. Catching the exception is not enough on
            # PostgreSQL: a failed statement aborts the whole transaction, and
            # every later project would then fail on a poisoned session rather
            # than on anything wrong with itself.
            async with session.begin_nested():
                counts = await _seed_project(session, project_id, parties, ordinal)
        except Exception:
            logger.warning(
                "Interface register demo seed skipped for project=%s (non-fatal)",
                project_id,
                exc_info=True,
            )
            continue
        for key, value in counts.items():
            totals[key] += value
    return totals
