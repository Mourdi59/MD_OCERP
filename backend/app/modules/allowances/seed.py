# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Allowances demo seed - a populated contingency register per demo project.

Fills the allowances screen with the register an estimator actually keeps: the
provisional sums held for scope that is not yet designed, the prime-cost sums
held for items a supplier will price later, and the design / construction
contingencies carried on top - each with the drawdowns released against it as
the scope firmed up.

Every amount is scaled from the project's OWN estimate (the sum of its BOQ line
item totals), so a warehouse and a hospital do not carry the same provisional
sums and a reader who compares the register against the estimate on the next
screen finds the proportions plausible. Amounts are rounded the way a person
rounds them, which is why the register does not read as generated.

The register is deliberately mixed: some allowances are untouched, some are
partly released, one is settled to the penny (remaining exactly zero), and
exactly one is over-drawn - the advisory state the module treats as first class
and shows with an "Over-drawn" badge. A register in which the badge never fires
teaches half the feature.

Amounts are derived, never hardcoded, so a demo whose BOQ is re-priced keeps a
register in proportion to it.

Acts on the demo estate only, and on all of it. Every project handed in is
considered - there is no "flagship plus a few" cap, which is how a screen ends
up permanently empty on the projects that fell outside it. A project outside the
estate is declined outright rather than merely skipped as already-seeded: see
:func:`_is_demo_project`. On top of that, a project that already carries an
allowance is left untouched, so a re-run never doubles the register.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import cache
from itertools import combinations
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.allowances.models import Allowance
from app.modules.allowances.schemas import AllowanceCreate, DrawdownCreate
from app.modules.allowances.service import AllowanceService

logger = logging.getLogger(__name__)

_SEED = 4110

# The three kinds an estimate carries (mirrors the schema's own vocabulary).
_PROVISIONAL_SUM = "provisional_sum"
_PC_SUM = "pc_sum"
_CONTINGENCY = "contingency"

# How many allowances a project's register holds, indexed by the project's
# position in the seeding call rather than drawn from its id, so two demo
# projects opened side by side are not the same length. Six sizes rather than
# four, every one of them at or below ``_MAX_REGISTER``: an earlier version grew
# the size with each wrap and clamped the result at the ceiling, which meant
# eight of the estate's eleven demo projects asked for the same length. What
# separates two registers of the same length is chosen further down, in
# ``_select_specs``; the length is only what makes the difference obvious.
_REGISTER_SIZES = (13, 10, 15, 11, 14, 12)

# Estimate total assumed for a project whose BOQ carries no parseable money, so
# the register still reads as a register. Scaled per project by the same
# position that sizes it, so the fallback is not identical everywhere either.
_FALLBACK_ESTIMATE = Decimal("2400000")
_FALLBACK_SCALES = (
    Decimal("1"),
    Decimal("2.4"),
    Decimal("0.55"),
    Decimal("4.1"),
    Decimal("1.7"),
    Decimal("0.85"),
)

# Line items scanned when totalling the estimate. The same ceiling the basis of
# estimate uses; a register scaled off the first 20k lines is already in
# proportion, and the cap stops a runaway project from being read into memory.
_POSITION_CAP = 20_000

# Rounding steps a person would use, by magnitude. An allowance of 47,318 is
# not something anyone writes down; 47,000 is.
_ROUNDING_STEPS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("1000000"), Decimal("25000")),
    (Decimal("250000"), Decimal("5000")),
    (Decimal("50000"), Decimal("1000")),
    (Decimal("10000"), Decimal("500")),
    (Decimal("0"), Decimal("100")),
)

# Smallest allowance worth carrying in a register. Below this the scaling has
# produced a figure too small to be a real allowance, so it is lifted.
_MIN_HELD = Decimal("2500")

# How far past its held amount the one over-drawn allowance runs, in percent.
# Kept small: an allowance over-drawn by half was never an allowance.
_OVERDRAW_RANGE = (103, 112)


@dataclass(frozen=True)
class _Spec:
    """One allowance the register may carry.

    ``share_bp`` is the allowance's size in basis points of the project's
    estimate total (100 bp = 1%). ``draws`` are the releases against it, each a
    percentage of the held amount plus the note explaining what firmed up; their
    percentages sum to at most 100, so an allowance can be fully settled but
    never over-drawn by accident. ``eligible_to_overdraw`` marks the specs that
    may carry the project's single deliberate over-draw.
    """

    key: str
    allowance_type: str
    label: str
    share_bp: int
    notes: str
    draws: tuple[tuple[int, str], ...] = ()
    core: bool = False
    eligible_to_overdraw: bool = False


# The register. ``core`` specs are carried by every project (an estimate without
# a design contingency is not an estimate); the rest fill the project's register
# up to its size. Labels describe scope by function only - no supplier, product
# or company is named anywhere.
_CATALOGUE: tuple[_Spec, ...] = (
    # ── Contingencies ──────────────────────────────────────────────────────
    _Spec(
        key="design-contingency",
        allowance_type=_CONTINGENCY,
        label="Design development contingency",
        share_bp=300,
        notes="Carried against design development between this estimate and the tender issue.",
        draws=(
            (18, "Released against the revised foundation layout."),
            (22, "Released against the co-ordinated services routes."),
        ),
        core=True,
    ),
    _Spec(
        key="construction-contingency",
        allowance_type=_CONTINGENCY,
        label="Construction contingency",
        share_bp=250,
        notes="Carried against instructed variations and site conditions during the works.",
        draws=(
            (12, "Released against the first month's instructed variations."),
            (15, "Released against the second month's instructed variations."),
            (9, "Released against additional temporary works."),
        ),
        core=True,
        eligible_to_overdraw=True,
    ),
    _Spec(
        key="client-risk",
        allowance_type=_CONTINGENCY,
        label="Client risk allowance",
        share_bp=150,
        notes="Held by the client outside the construction contingency, released on instruction only.",
    ),
    _Spec(
        key="inflation-risk",
        allowance_type=_CONTINGENCY,
        label="Price escalation allowance",
        share_bp=180,
        notes="Held for movement in material prices beyond the stated base date.",
        draws=((34, "Released against the confirmed structural steel order."),),
    ),
    # ── Provisional sums ───────────────────────────────────────────────────
    _Spec(
        key="drainage-connection",
        allowance_type=_PROVISIONAL_SUM,
        label="Below-ground drainage and utility connections",
        share_bp=90,
        notes="Routes and connection points not confirmed at the time of estimate.",
        draws=(
            (45, "Released to the drainage package after the connection survey."),
            (30, "Released for the diverted incoming water main."),
        ),
        core=True,
        eligible_to_overdraw=True,
    ),
    _Spec(
        key="external-works",
        allowance_type=_PROVISIONAL_SUM,
        label="External works and soft landscaping",
        share_bp=120,
        notes="Landscape design not issued; allowance based on the site area.",
        draws=((40, "Released against the agreed hard landscaping layout."),),
        core=True,
    ),
    _Spec(
        key="builders-work",
        allowance_type=_PROVISIONAL_SUM,
        label="Builder's work in connection with services",
        share_bp=80,
        notes="Holes, chases and bases pending the co-ordinated services drawings.",
        draws=(
            (28, "Released for the plant room bases."),
            (26, "Released for the riser penetrations."),
        ),
    ),
    _Spec(
        key="fire-stopping",
        allowance_type=_PROVISIONAL_SUM,
        label="Fire stopping and compartmentation",
        share_bp=45,
        notes="Extent to be confirmed by the compartmentation survey.",
        draws=((100, "Settled at final account against the completed survey schedule."),),
    ),
    _Spec(
        key="facade-access",
        allowance_type=_PROVISIONAL_SUM,
        label="Facade access and cleaning provision",
        share_bp=70,
        notes="Access strategy under review; allowance covers the anchor system only.",
        eligible_to_overdraw=True,
    ),
    _Spec(
        key="party-structures",
        allowance_type=_PROVISIONAL_SUM,
        label="Temporary works to adjoining structures",
        share_bp=55,
        notes="Held pending the adjoining owner's schedule of condition.",
        draws=((52, "Released against the agreed propping scheme."),),
    ),
    _Spec(
        key="ground-remediation",
        allowance_type=_PROVISIONAL_SUM,
        label="Ground remediation and obstruction removal",
        share_bp=110,
        notes="Held against obstructions recorded in the desk study but not yet proven.",
        draws=((37, "Released for the obstructions found in the north bay."),),
    ),
    _Spec(
        key="acoustic-treatment",
        allowance_type=_PROVISIONAL_SUM,
        label="Acoustic treatment to plant enclosures",
        share_bp=40,
        notes="Specification pending the acoustic consultant's report.",
    ),
    _Spec(
        key="commissioning",
        allowance_type=_PROVISIONAL_SUM,
        label="Commissioning and witness testing",
        share_bp=60,
        notes="Scope of witnessed tests to be agreed with the client's engineer.",
        draws=((23, "Released for the first stage of witnessed testing."),),
    ),
    # ── Prime-cost sums ────────────────────────────────────────────────────
    _Spec(
        key="lift-installation",
        allowance_type=_PC_SUM,
        label="Lift installation supply and commissioning",
        share_bp=160,
        notes="Supplier to be selected; sum covers supply, installation and handover.",
        draws=((100, "Sum settled against the selected supplier's fixed price."),),
    ),
    _Spec(
        key="ironmongery",
        allowance_type=_PC_SUM,
        label="Architectural ironmongery supply",
        share_bp=35,
        notes="Schedule not issued; sum covers supply only, fixing measured elsewhere.",
        # Drawn to the full sum in two releases, so every register carries one
        # allowance that has settled and reads as remaining exactly zero.
        draws=(
            (61, "Drawn against the confirmed door schedule."),
            (39, "Sum settled against the ironmongery package as ordered."),
        ),
        # The core prime-cost sum. Ironmongery rather than the lift: a lift on
        # every register would put one in the single-storey warehouse too, and a
        # line that cannot be built is the first thing a quantity surveyor spots.
        core=True,
    ),
    _Spec(
        key="sanitaryware",
        allowance_type=_PC_SUM,
        label="Sanitaryware and brassware supply",
        share_bp=45,
        notes="Client selection outstanding; sum covers supply only.",
        draws=((44, "Drawn against the sanitaryware selected for the sample room."),),
    ),
    _Spec(
        key="joinery-fitout",
        allowance_type=_PC_SUM,
        label="Fitted joinery and worktop supply",
        share_bp=90,
        notes="Sum covers supply of fitted units; installation measured in the trade.",
        draws=((33, "Drawn against the sample unit approved on site."),),
    ),
    _Spec(
        key="signage-wayfinding",
        allowance_type=_PC_SUM,
        label="Signage and wayfinding supply",
        share_bp=30,
        notes="Wayfinding strategy pending; sum covers supply and fixing brackets.",
    ),
)

_CORE_SPECS = tuple(s for s in _CATALOGUE if s.core)
_OPTIONAL_SPECS = tuple(s for s in _CATALOGUE if not s.core)

# The ceiling on a register, and the reason there is one: a project that asks
# for the whole catalogue stops sampling it, and every project past that point
# would show the same eighteen labels and differ only in the money. Holding
# three back means each project leaves out a different three.
_MAX_REGISTER = len(_CATALOGUE) - 3

# Seed for the order the registers are handed out in. Fixed, so the estate is
# reproducible, and separate from the per-project money seed because it decides
# something else: combinations come out of the enumeration in lexicographic
# order, where neighbours differ by one line, and two demo projects opened one
# after the other have to read as different registers rather than as one
# register with a line swapped.
_ORDER_SEED = 6704

# A stable display order for the register: type first, then the catalogue's own
# order within a type, so a re-seed of one project reproduces the same screen.
_TYPE_ORDER = {_PROVISIONAL_SUM: 0, _PC_SUM: 1, _CONTINGENCY: 2}
_CATALOGUE_ORDER = {spec.key: index for index, spec in enumerate(_CATALOGUE)}


def _is_demo_project(metadata: dict | None) -> bool:
    """Whether a project row belongs to the demo estate.

    The gate this seeder is allowed to act behind, and the reason it is not
    "does the project have allowances yet": the boot backfill runs over every
    project in the database and re-runs on every version upgrade, so on a
    customer installation a real project with no allowances recorded is handed
    here and looks exactly like an unseeded demo one. Inventing a register
    inside it is a data incident, not a cosmetic one.

    ``demo_id`` is the key that covers the whole estate. The ten templates stamp
    it alongside ``is_demo``; the flagship reference project is built from its
    own baked fixture and stamps ``demo_id`` without ``is_demo``, so a gate on
    ``is_demo`` would skip the project users actually land on.

    Read from the fetched value rather than matched in SQL: ``metadata_`` is a
    JSON column, and a containment test against it compiles to a string LIKE on
    PostgreSQL rather than to JSONB containment.
    """
    if not isinstance(metadata, dict):
        return False
    return bool(str(metadata.get("demo_id") or "").strip())


def _rng_for(project_id: uuid.UUID) -> random.Random:
    """A deterministic RNG per project, so a re-seed reproduces the register."""
    return random.Random(f"{_SEED}:{project_id}")


def _to_decimal(value: object) -> Decimal | None:
    """Parse a BOQ money string to a Decimal, or ``None`` when it is not money.

    BOQ money columns are strings by design, so a project can and does carry
    blanks and free text there. An unparseable cell contributes nothing to the
    estimate total rather than taking the whole project's savepoint down.
    """
    if value is None:
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _round_money(value: Decimal) -> Decimal:
    """Round an amount to the step a person would use at that magnitude."""
    step = _ROUNDING_STEPS[-1][1]
    for threshold, candidate in _ROUNDING_STEPS:
        if value >= threshold:
            step = candidate
            break
    rounded = (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    return rounded if rounded >= step else step


async def _estimate_total(session: AsyncSession, project_id: uuid.UUID) -> Decimal:
    """Sum the project's BOQ line item totals, or ``Decimal(0)`` when it has none.

    Money lives in ``Position.total`` as a string by design, so the sum is done
    in Python over the parseable cells rather than in SQL - ``sum()`` over a text
    column is an error on PostgreSQL, not a zero.
    """
    try:
        from app.modules.boq.models import BOQ, Position

        stmt = (
            select(Position.total)
            .join(BOQ, Position.boq_id == BOQ.id)
            .where(BOQ.project_id == project_id, Position.unit != "")
            .limit(_POSITION_CAP)
        )
        rows = (await session.execute(stmt)).scalars().all()
    except Exception:
        logger.debug("BOQ lookup unavailable for project=%s", project_id)
        return Decimal("0")
    total = Decimal("0")
    for raw in rows:
        parsed = _to_decimal(raw)
        if parsed is not None and parsed > 0:
            total += parsed
    return total


@cache
def _optional_registers(count: int) -> tuple[tuple[_Spec, ...], ...]:
    """Every selection of ``count`` optional specs a register is allowed to carry.

    Enumerated rather than sampled. A sample makes a repeat unlikely and the
    registers have to differ, not probably differ: the widest register takes ten
    of the thirteen optional specs, which is 286 registers to draw from, and the
    demo estate asks for a register eleven times.

    Selections in which every optional spec carries releases are dropped here.
    Every core spec is drawn against, so such a register would show nothing
    untouched, which is not what a live register looks like, and the module's
    untouched state would never be on screen. Dropped rather than left to chance
    because the enumeration is walked deterministically: an unwanted combination
    would be a permanent register, not an occasional one.

    Shuffled once, under a fixed seed, so the estate is reproducible and the
    project handed the next index is not handed the previous register with one
    line changed.
    """
    pool = [combo for combo in combinations(_OPTIONAL_SPECS, count) if any(not spec.draws for spec in combo)]
    random.Random(f"{_ORDER_SEED}:{count}").shuffle(pool)
    return tuple(pool)


def _select_specs(ordinal: int, size: int) -> list[_Spec]:
    """Choose the register's allowances: every core spec plus a filled remainder.

    The remainder is the combination sitting at this project's own position, so
    two projects in one seeding call cannot be handed the same register rather
    than being unlikely to be. Two projects of the same size hold different
    positions: sizes cycle over a pool of six, so two projects share a size only
    when their positions differ by a multiple of six, and a combination comes
    round again only after the whole enumeration, which is 286 registers at the
    widest size and over a thousand at every other one.
    """
    chosen = list(_CORE_SPECS)
    count = max(0, min(size - len(chosen), len(_OPTIONAL_SPECS)))
    if count:
        registers = _optional_registers(count)
        chosen.extend(registers[ordinal % len(registers)])
    chosen.sort(key=lambda spec: (_TYPE_ORDER.get(spec.allowance_type, 9), _CATALOGUE_ORDER[spec.key]))
    return chosen


def _held_amount(spec: _Spec, estimate_total: Decimal, rng: random.Random) -> Decimal:
    """Size one allowance from the project's own estimate.

    The catalogue share is jittered by up to 15% either way so two projects of
    the same size do not carry byte-identical registers, then rounded the way a
    person rounds an allowance.
    """
    jitter = Decimal(rng.randint(85, 115)) / Decimal("100")
    raw = estimate_total * Decimal(spec.share_bp) / Decimal("10000") * jitter
    return max(_round_money(raw), _MIN_HELD)


def _drawdown_amounts(held: Decimal, spec: _Spec, overdraw_pct: int | None) -> list[Decimal]:
    """Split an allowance's releases so they total exactly the intended share.

    Every release but the last is the rounded percentage of the held amount; the
    last one absorbs the rounding so the running total lands exactly on
    ``held * total_pct / 100``. That is what makes a settled allowance read as
    remaining exactly zero on the screen instead of remaining 43.
    """
    if not spec.draws:
        return []
    total_pct = Decimal(overdraw_pct) if overdraw_pct is not None else Decimal(sum(pct for pct, _ in spec.draws))
    target = (held * total_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    amounts: list[Decimal] = []
    for pct, _note in spec.draws[:-1]:
        share = (held * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amounts.append(max(share, Decimal("0.01")))
    last = target - sum(amounts, Decimal("0"))
    if last <= 0:
        # Rounding ate the closing release; give it a token amount and let the
        # register carry the rounding rather than write a zero or a negative.
        last = Decimal("0.01")
    amounts.append(last)
    return amounts


def _overdraw_choice(rng: random.Random, specs: Sequence[_Spec]) -> tuple[str | None, int | None]:
    """Pick the one allowance that runs past its held amount, and by how much."""
    eligible = [spec for spec in specs if spec.eligible_to_overdraw and spec.draws]
    if not eligible:
        return None, None
    spec = rng.choice(eligible)
    return spec.key, rng.randint(*_OVERDRAW_RANGE)


async def _seed_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    currency: str,
    owner_id: uuid.UUID,
    ordinal: int,
) -> dict[str, int]:
    """Seed one project's register. Returns per-entity counts (zeros when skipped)."""
    empty = {"projects": 0, "allowances": 0, "drawdowns": 0}

    already = (
        (await session.execute(select(Allowance.id).where(Allowance.project_id == project_id).limit(1)))
        .scalars()
        .first()
    )
    if already is not None:
        return empty

    rng = _rng_for(project_id)
    slot = ordinal % len(_REGISTER_SIZES)
    size = min(_REGISTER_SIZES[slot], _MAX_REGISTER)

    estimate_total = await _estimate_total(session, project_id)
    if estimate_total <= 0:
        estimate_total = _FALLBACK_ESTIMATE * _FALLBACK_SCALES[slot % len(_FALLBACK_SCALES)]

    specs = _select_specs(ordinal, size)
    overdraw_key, overdraw_pct = _overdraw_choice(rng, specs)

    service = AllowanceService(session)
    counts = {"projects": 1, "allowances": 0, "drawdowns": 0}
    created_by = str(owner_id)

    for spec in specs:
        held = _held_amount(spec, estimate_total, rng)
        allowance = await service.create_allowance(
            project_id,
            AllowanceCreate(
                label=spec.label,
                allowance_type=spec.allowance_type,
                held_amount=held,
                currency=currency,
                notes=spec.notes,
            ),
            created_by,
        )
        counts["allowances"] += 1

        pct = overdraw_pct if spec.key == overdraw_key else None
        amounts = _drawdown_amounts(held, spec, pct)
        for amount, (_share, note) in zip(amounts, spec.draws, strict=True):
            await service.add_drawdown(
                allowance.id,
                DrawdownCreate(amount=amount, note=note),
                created_by,
            )
            counts["drawdowns"] += 1

    return counts


async def seed_allowances_demo(
    session: AsyncSession,
    project_ids: Iterable[uuid.UUID],
) -> dict[str, int]:
    """Populate the allowances and contingency register for the demo projects.

    A reader who opens the Allowances screen afterwards sees a register of ten to
    fifteen allowances split across provisional sums, prime-cost sums and
    contingencies, denominated in the project's own currency and sized as a
    plausible share of its estimate. Some are untouched, some are part released,
    at least one is settled to exactly zero remaining, and exactly one carries the
    "Over-drawn" badge - so the per-currency roll-up at the top of the screen has
    something to total and the advisory state is visible rather than theoretical.
    No two projects list the same allowances: every register is a different part
    of the catalogue rather than the whole of it, and which part is decided by
    the project's position in the call rather than drawn at random, so the demo
    estate cannot land on the same register twice.

    Args:
        session: Async DB session. The caller commits.
        project_ids: Projects to consider - every one of them, never a first few.
            A project is seeded only when it belongs to the demo estate and
            carries no allowance yet, so a customer's own project is left alone
            and a re-run never doubles the register.

    Returns:
        Dict with per-entity insert counts across every project seeded.
    """
    totals = {"projects": 0, "allowances": 0, "drawdowns": 0}
    ids = list(project_ids)
    if not ids:
        return totals

    from app.modules.projects.models import Project

    rows = (
        await session.execute(
            select(Project.id, Project.currency, Project.owner_id, Project.metadata_).where(Project.id.in_(ids)),
        )
    ).all()
    known = {pid: (str(ccy or "").strip().upper()[:3], owner, meta) for pid, ccy, owner, meta in rows}

    # Demo projects only. The position that sizes a register counts only those,
    # so the rotation stays dense on an installation that also holds projects of
    # its own rather than skipping sizes wherever a real project was passed over.
    targets: list[tuple[uuid.UUID, str, uuid.UUID]] = []
    for project_id in ids:
        found = known.get(project_id)
        if found is None:
            continue
        currency, owner_id, metadata = found
        if owner_id is None or not _is_demo_project(metadata):
            continue
        targets.append((project_id, currency, owner_id))

    for ordinal, (project_id, currency, owner_id) in enumerate(targets):
        try:
            # A SAVEPOINT per project, so one project that cannot be seeded costs
            # only its own rows. Catching the exception is not enough on
            # PostgreSQL: a failed statement aborts the whole transaction, and
            # every later project would then fail on a poisoned session rather
            # than on anything wrong with itself.
            async with session.begin_nested():
                counts = await _seed_project(session, project_id, currency, owner_id, ordinal)
        except Exception:
            logger.warning("Allowances demo seed skipped for project=%s (non-fatal)", project_id, exc_info=True)
            continue
        for key, value in counts.items():
            totals[key] += value
    return totals


__all__ = ["seed_allowances_demo"]
