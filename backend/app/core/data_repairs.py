# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Boot-path data repairs - the half of a migration the schema heal cannot do.

What this exists for
--------------------
The product does not run ``alembic upgrade``. The schema moves at boot through
:func:`app.core.postgres_migrator.postgres_auto_migrate`, which adds sequences,
columns, indexes and constraints, plus ``Base.metadata.create_all``, which
creates whole missing tables. Between them they cover every *additive schema*
revision and nothing else. A revision whose ``upgrade()`` body rewrites rows -
a backfill, a rename, a de-duplication - passes straight through: its statements
are never executed on any install brought up the normal way, while
``stamp_head_if_unstamped`` records the database at head.

That combination is the defect this module answers. Not "the rewrite did not
run", which would at least be discoverable, but "the rewrite did not run *and*
the version table says it did". Nothing downstream ever looks again.

What this is, and what it deliberately is not
---------------------------------------------
This is a registry of **human-authored** repairs that run on the boot path. Each
entry is code somebody wrote, read and decided to run against customer data.

Modules register their own repairs. There is no list in this file: a module
puts a ``repairs.py`` beside its ``models.py``, builds a :class:`DataRepair` and
hands it to :func:`register_data_repair`, and :func:`discover_data_repairs`
imports the lot on the boot path. A central list would be a single file every
author has to edit, and two authors editing it at once lose each other's entry
in a way ``git status`` cannot show, because the file was already modified. The
entry that goes missing is a repair that then never runs.

Every repair has to say which of two natures it has, and the distinction is not
paperwork. ``always_wrong`` corrects a value that was never right - a
trademarked catalogue name, a missing label - and may overwrite it in place.
``superseded`` corrects a value that was right until a date and wrong after it -
a tax rate the legislature changed - and may **not** overwrite it, because an
invoice issued at the old rate has to keep reading at the old rate. The second
kind declares :class:`SupersededBy`, and :func:`verify_supersede_shape` checks
its actual effect on the table against that declaration, so the difference is
enforced rather than described.

It is **not** a mechanism that replays revision bodies. That was considered and
rejected, and the reasons are worth keeping next to the code so the idea is not
re-proposed as an obvious improvement:

* The desktop bundle ships no migration tree at all (``desktop/pyinstaller.spec``
  bundles ``app``, ``locales`` and the frontend, and neither ``alembic/`` nor
  ``alembic.ini``), so on the largest install route there is nothing to replay.
* The revision tree cannot be run standalone anyway: revisions inspect tables
  that ``create_all`` creates, which ``tests/integration/test_migrations_roundtrip.py``
  documents at the top of its own docstring.
* A rewrite against customer data needs judgement that machinery does not have.
  ``v3271_formwork_debrand`` declines to touch a tenant that already holds the
  replacement row, because deciding which of two rows an existing assignment
  should follow is a call about somebody else's data. A generic replayer would
  have no place to put that decision.

So: revisions stay the record for operators who run alembic by hand, and a
repair that has to reach everybody else is written here as well. The cost is
that such a repair is written twice. The gate at
``scripts/check_data_rewrite_boot_repair.py`` is what makes the second half
non-optional, by refusing a revision that rewrites rows unless its file says
where the boot-path half lives - or says, in words, why it does not need one.

The ledger is a RECORD and never a GATE
---------------------------------------
:class:`DataRepairLedger` records what ran, when, and how many rows moved. It is
never consulted to decide whether a repair should run. Every repair runs on
every boot.

This is the whole point, so it is worth being blunt about it: a table that is
allowed to answer "already done" is ``alembic_version``, and ``alembic_version``
saying "done" over data that was never rewritten is the bug this module exists
because of. Rebuilding that shape one directory over would be an odd way to fix
it. Running every time also means a database restored from a backup taken before
the repair is repaired again, which a run-once ledger would silently skip.

The property that makes this affordable is idempotence, and it is a requirement
on every entry, not a hope: :class:`DataRepair` is where that contract is
written down, and ``tests/pg/test_data_repairs.py`` holds it for the repairs
registered today by running each one twice and asserting the second pass
changes nothing.

Silence
-------
A repair that fails is logged at ERROR with its id and its exception, and the
boot path publishes ``data_repairs_failed`` on ``/api/health`` beside
``schema_heal_failed``. A repair that runs and changes nothing is the ordinary
case and stays at DEBUG; a repair that runs and *changes rows* is logged at
INFO with the count, because on an upgraded install that line is the only
contemporaneous evidence that the customer's data was altered.

Reading the ledger on a live install::

    SELECT repair_id, last_outcome, runs, rows_changed_total, updated_at
      FROM oe_data_repair_ledger ORDER BY repair_id;

That query is the answer to "did this install ever carry the branded rows"
after the fact, and it is the only such answer that exists: there is no
telemetry in this product and no install identifier, so the affected population
cannot be counted centrally and never could be.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import Integer, String, Text, select, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

#: How a single repair ended. ``applied`` changed at least one row, ``clean``
#: ran and found nothing to do, ``failed`` raised. There is no fourth answer:
#: a repair that was not attempted does not appear in the report at all, which
#: is why the report also carries :attr:`DataRepairReport.attempted`.
RepairStatus = Literal["applied", "clean", "failed"]

_LEDGER_TABLE = "oe_data_repair_ledger"


class DataRepairLedger(Base):
    """One row per registered repair, rewritten on every boot that runs it.

    Never read to decide whether a repair runs - see the module docstring. It
    exists so that a question about an install already in the field ("did the
    de-brand ever touch this database, and how many rows did it move?") has an
    answer on the install itself.

    Timestamps come from ``Base``: ``created_at`` is the first boot that
    recorded this repair on this database, and ``updated_at`` is the last one
    that ran it. Two columns of our own saying the same thing would only be two
    more places for the two to disagree.

    ``repair_id`` is unique rather than the primary key, because ``Base``
    already declares a UUID ``id`` on every model and a second ``primary_key``
    here would quietly make the key composite - which is to say, no key at all
    on ``repair_id``, and duplicate rows for one repair the moment two boots
    race. ``tests/pg/test_data_repairs.py`` holds that line against the live
    catalogue rather than against this declaration.

    Every column this module writes carries a ``server_default``. A model-side
    Python default is not enough: ``postgres_auto_migrate`` renders only
    *literal* scalar defaults into its ``ADD COLUMN``, so a NOT NULL column
    whose default is a callable, or is Python-side only, lands nullable with no
    default on every database that gains it through the heal rather than
    through ``create_all``.
    """

    __tablename__ = _LEDGER_TABLE

    repair_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    #: How many boots have run this repair. A count far above 1 while
    #: ``rows_changed_total`` still equals the first run's count is what a
    #: healthy idempotent repair looks like.
    runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rows_changed_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_rows_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_outcome: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'clean'"))
    #: Populated only while ``last_outcome`` is ``failed``, and cleared on the
    #: next run that succeeds, so a stale message can never outlive its cause.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The release that last ran it. An install reporting a repair applied under
    #: a version nobody shipped is a build problem rather than a data problem,
    #: and without this column the two are indistinguishable in a support log.
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


#: What kind of wrongness a repair corrects. The two are not interchangeable
#: and the distinction is the reason this field is required rather than
#: defaulted.
#:
#: ``always_wrong``
#:     The stored value was never correct. A catalogue row seeded with a
#:     trademarked name, a NULL where the column should never have been empty,
#:     a duplicate that a later unique index forbids. Nothing downstream was
#:     ever entitled to rely on it, so overwriting it in place is the whole
#:     repair and there is no date at which the old value was right.
#:
#: ``superseded``
#:     The stored value was correct until a date and became wrong after it. A
#:     tax rate the legislature changed, a statutory retention percentage, an
#:     index base year. **This kind must never be rewritten in place.** An
#:     invoice issued at last year's rate has to keep reading at last year's
#:     rate, and a repair that overwrites the rate changes the value of a
#:     document already sent to a customer. The correct shape is to close the
#:     old row's validity window and insert the new value beside it, which is
#:     what :class:`SupersededBy` declares and what
#:     :func:`verify_supersede_shape` checks.
RepairNature = Literal["always_wrong", "superseded"]


@dataclass(frozen=True)
class SupersededBy:
    """Declares the close-and-add shape for a repair of nature ``superseded``.

    This is not documentation. :func:`verify_supersede_shape` reads these three
    names and checks the repair's actual effect on the table against them, and
    ``tests/pg/test_data_repairs.py`` runs that check over every registered
    repair. A repair that declares itself ``superseded`` and then overwrites a
    value column fails the registry's own contract test.

    The check is structural rather than domain-specific on purpose. Asking each
    consumer for a "what did this resolve to on date D" probe would mean every
    future author has to build a resolver before they can register a repair,
    and most repairs have no resolver to borrow. The shape is enough: if no
    pre-existing row's value columns changed, and the only edit to an existing
    row was closing its open validity window, then no already-issued document
    can have changed value, whatever the domain.

    Attributes:
        effective_from: ISO date on which the new value takes effect. Recorded
            so a support log can answer "from when" without reading the code.
        table: The table the repair rewrites, as it is named in the database.
        closes_column: The column that ends a row's validity window -
            ``effective_to`` for a tax rate. The check permits a pre-existing
            row to change here, and only from empty to set. A row that already
            carried a closing date may not have it moved: that would re-open or
            re-close a window somebody set by hand.
        also_updates: Further columns the repair is allowed to change on a
            pre-existing row. Empty by default, and it should stay empty
            wherever it can: every name added here is a hole in the contract.
            Add one only for a column that is **not part of any issued
            document's value** - a selection hint or a display flag - and write
            the reason at the call site. The rate, the amount, the quantity and
            the date a document was priced on can never go in this list.

            The case that produced it: closing Romania's 19 % row also has to
            move ``is_default`` off it, because a rate whose window has ended
            cannot go on being the one the UI offers first. That flips a column
            on a pre-existing row and is still safe, since no invoice's value
            depends on which rate is offered first. The registry's contract
            test found that edit on its first run, which is the argument for
            declaring the allowance rather than loosening the check.
    """

    effective_from: str
    table: str
    closes_column: str
    also_updates: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataRepair:
    """One repair: an id, the revision it belongs to, and the code that runs it.

    Construct it and hand it to :func:`register_data_repair` from the owning
    module's ``repairs.py``. Do not add entries to this file - see that
    function for why.

    Attributes:
        repair_id: Stable identifier, written into the ledger and named by the
            revision's ``# boot-repair:`` line. Never reuse or rename one: the
            ledger rows already in the field are keyed on it.
        revision: The alembic revision whose data half this is, or ``""`` when
            the repair has no revision behind it. Only ever documentation - the
            runner does not look at the migration tree, which is the point.
        summary: One line, in English, for the boot log and the report.
        run: Coroutine taking an open :class:`~sqlalchemy.ext.asyncio.AsyncSession`
            and returning the number of rows it changed. It must not commit; the
            runner owns the transaction. **It must be idempotent**: it runs on
            every boot, and a second pass over an already-repaired database has
            to return 0 and change nothing.
        nature: ``always_wrong`` or ``superseded``. Required, with no default,
            because the two need opposite handling and a default would silently
            pick one - see :data:`RepairNature`.
        superseded: Required when ``nature`` is ``superseded``, forbidden
            otherwise. Both rules are enforced in ``__post_init__`` so a wrong
            declaration fails at import, not on a customer's data.
    """

    repair_id: str
    revision: str
    summary: str
    run: Callable[[AsyncSession], Awaitable[int]]
    nature: RepairNature
    superseded: SupersededBy | None = None

    def __post_init__(self) -> None:
        """Reject a declaration that cannot mean what it says.

        Raises:
            ValueError: If the nature and the ``superseded`` block disagree, or
                if ``repair_id`` is empty.
        """
        if not self.repair_id:
            raise ValueError("repair_id must not be empty: the ledger is keyed on it")
        if self.nature == "superseded" and self.superseded is None:
            raise ValueError(
                f"data repair {self.repair_id!r} declares nature 'superseded' but no SupersededBy block. "
                "A repair of values that were once correct has to say which table it closes and which "
                "column closes it, or nothing can check that it is not rewriting history."
            )
        if self.nature != "superseded" and self.superseded is not None:
            raise ValueError(
                f"data repair {self.repair_id!r} carries a SupersededBy block but declares nature "
                f"{self.nature!r}. The block is only meaningful for 'superseded'."
            )


@dataclass(frozen=True)
class DataRepairOutcome:
    """What one repair did on this boot."""

    repair_id: str
    status: RepairStatus
    rows_changed: int
    error: str | None = None


@dataclass(frozen=True)
class DataRepairReport:
    """What the whole pass did, in a form the boot path can publish.

    ``ledger_written`` is reported separately from the outcomes on purpose. A
    repair can succeed against a database whose role may write rows but not
    create tables, in which case the data is correct and the *record* of it is
    missing. Those are different failures and collapsing them would let the
    smaller one hide the larger.
    """

    outcomes: tuple[DataRepairOutcome, ...]
    ledger_written: bool

    @property
    def attempted(self) -> int:
        """How many repairs were actually run."""
        return len(self.outcomes)

    @property
    def failed(self) -> tuple[str, ...]:
        """Ids of the repairs that raised."""
        return tuple(o.repair_id for o in self.outcomes if o.status == "failed")

    @property
    def rows_changed(self) -> int:
        """Total rows changed across every repair in this pass."""
        return sum(o.rows_changed for o in self.outcomes)


#: The live registry, keyed by ``repair_id`` and kept in registration order.
#: Private because it is mutable: read it through :func:`registered_data_repairs`,
#: which hands back an immutable snapshot.
_REGISTRY: dict[str, DataRepair] = {}

#: Conventional module file that registers a module's repairs. Imported by
#: :func:`discover_data_repairs`, and scanned statically by
#: ``scripts/check_data_rewrite_boot_repair.py``.
REPAIRS_MODULE_NAME = "repairs"


def register_data_repair(repair: DataRepair) -> DataRepair:
    """Register one repair, from the owning module's ``repairs.py``.

    Why registration rather than a list in this file: a literal registry here
    is a single file that every module author has to edit, so two authors
    working at once overwrite each other. That collision is close to invisible -
    the file is already modified, so ``git status`` shows nothing new, and the
    loser's entry simply is not there. A repair that is not there does not run,
    and not running while everything reports success is precisely the defect
    this whole module exists to answer. So the shared file is the hazard, and
    removing it removes the hazard.

    Registration is deliberately loud about collisions. Two repairs claiming one
    id would share a ledger row and report each other's counts.

    Args:
        repair: The repair to register.

    Returns:
        The same repair, so a module can bind it to a name in one statement.

    Raises:
        ValueError: If ``repair_id`` is already registered by a different repair.
    """
    existing = _REGISTRY.get(repair.repair_id)
    if existing is not None and existing is not repair:
        raise ValueError(
            f"data repair id {repair.repair_id!r} is already registered by revision "
            f"{existing.revision!r}; ids are the ledger's primary key and must be unique"
        )
    _REGISTRY[repair.repair_id] = repair
    return repair


def registered_data_repairs() -> tuple[DataRepair, ...]:
    """Every repair registered so far, in registration order.

    Returns:
        An immutable snapshot. Empty until :func:`discover_data_repairs` has
        run, which is why the runner calls that itself rather than trusting
        something else to have imported the right modules.
    """
    return tuple(_REGISTRY.values())


def discover_data_repairs() -> tuple[DataRepair, ...]:
    """Import every ``app.modules.*.repairs`` module, so its registrations run.

    Discovery is an explicit pass over a conventional filename rather than a
    side effect of some other import. The model-registration loop in
    ``app/main.py`` does import every module package on its way to
    ``models.py``, and repairs would in fact get registered by it today - but
    resting on that would mean a repair stops running the day somebody narrows
    a loop whose stated job is models. The failure would be silent and would
    look exactly like the bug this module was written to remove.

    A module whose ``repairs.py`` raises is reported and skipped rather than
    allowed to stop the boot, on the same reasoning as a failing repair: one
    module must not take the application down. The ERROR names the module,
    and ``tests/unit/test_data_repair_registry.py`` cross-checks the registry
    against what the revisions declare, so a module that quietly fails to
    register is caught by a gate rather than only by a log nobody reads.

    Returns:
        Every repair registered after discovery, in registration order.
    """
    import importlib
    import pkgutil

    import app.modules as modules_pkg

    for found in pkgutil.iter_modules(modules_pkg.__path__):
        if not found.ispkg:
            continue
        dotted = f"app.modules.{found.name}.{REPAIRS_MODULE_NAME}"
        try:
            importlib.import_module(dotted)
        except ModuleNotFoundError as exc:
            # No repairs.py in this module, which is the normal case. Re-raise
            # when the missing import is something *inside* repairs.py, because
            # that is a real broken module rather than an absent one.
            if exc.name != dotted:
                logger.error(
                    "Data repair module %s failed to import (%s: %s); any repair it registers will "
                    "NOT run on this boot.",
                    dotted,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
        except Exception as exc:  # noqa: BLE001 - one bad module must not stop the boot
            logger.error(
                "Data repair module %s failed to import (%s: %s); any repair it registers will NOT run on this boot.",
                dotted,
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    return registered_data_repairs()


def __getattr__(name: str) -> object:
    """Compatibility shim for the old module-level ``DATA_REPAIRS`` tuple.

    The registry used to be a literal tuple in this file. It is now built by
    :func:`register_data_repair` from each module's ``repairs.py``, so the name
    no longer exists as a variable. Callers that still read it - including
    tests written against the old shape - get a snapshot taken after discovery
    rather than an ImportError.

    Prefer :func:`registered_data_repairs` in new code: it says that the value
    is a snapshot of something mutable, which the constant-looking old name
    does not. This shim exists so that replacing the registry did not have to
    mean editing every file that read it in the same change.

    Args:
        name: Attribute being looked up on this module.

    Returns:
        The discovered registry when ``name`` is ``DATA_REPAIRS``.

    Raises:
        AttributeError: For any other name, as normal attribute lookup would.
    """
    if name == "DATA_REPAIRS":
        return discover_data_repairs()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def snapshot_table(session: AsyncSession, table: str) -> dict[str, dict[str, object]]:
    """Read a whole table into ``{primary key: {column: value}}``.

    Used by the registry's contract tests to compare a table before and after a
    repair. Fine for the catalogue-sized tables repairs touch; not intended for
    anything large.

    Args:
        session: Open async session.
        table: Table name.

    Returns:
        One entry per row, keyed by the row's ``id``.
    """
    rows = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().all()  # noqa: S608 - table name is a literal from the registry, never user input
    return {str(row["id"]): dict(row) for row in rows}


def verify_supersede_shape(
    repair: DataRepair,
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
) -> tuple[str, ...]:
    """Check that a ``superseded`` repair closed and added rather than rewrote.

    This is the executable half of the ``superseded`` declaration. Given the
    table before and after the repair, it returns the ways the repair broke the
    close-and-add contract. An empty tuple means it held.

    Three things are checked, and each maps to a way an already-issued document
    could change value:

    * No pre-existing row disappeared. A deleted rate is a document that can no
      longer be priced at all.
    * No pre-existing row changed any column except the declared
      ``closes_column`` and whatever the repair listed in ``also_updates``.
      This is the one that matters: it is what makes it impossible for the
      repair to have altered a rate a document was issued at. Anything in
      ``also_updates`` was signed off at the call site as not being part of an
      issued document's value.
    * The ``closes_column`` only ever went from empty to set. Moving a closing
      date somebody had already set would re-open or re-close a window by hand,
      which is an operator's decision and not a repair's.

    Adding rows is unrestricted, because that is the half of close-and-add that
    is supposed to happen.

    Args:
        repair: The repair under test. Must declare ``nature="superseded"``.
        before: :func:`snapshot_table` output from before the repair ran.
        after: The same table after it ran.

    Returns:
        Human-readable violations, empty when the contract held.

    Raises:
        ValueError: If the repair does not declare a ``SupersededBy`` block.
    """
    if repair.superseded is None:
        raise ValueError(f"{repair.repair_id!r} declares no SupersededBy block, so there is no shape to verify")
    closes = repair.superseded.closes_column
    allowed = frozenset(repair.superseded.also_updates)
    violations: list[str] = []

    for key, old_row in before.items():
        new_row = after.get(key)
        if new_row is None:
            violations.append(f"row {key} was deleted; a superseded repair may only close and add")
            continue
        for column, old_value in old_row.items():
            # updated_at moves whenever the ORM touches the row and says nothing
            # about whether a value the customer can see changed.
            if column == "updated_at":
                continue
            new_value = new_row.get(column)
            if new_value == old_value:
                continue
            if column in allowed:
                continue
            if column != closes:
                violations.append(
                    f"row {key} column {column!r} changed from {old_value!r} to {new_value!r}; "
                    f"a superseded repair may only set {closes!r} on an existing row, because any "
                    "other edit retroactively changes a document already issued at the old value"
                )
            elif old_value is not None:
                violations.append(
                    f"row {key} already carried {closes}={old_value!r} and the repair moved it to "
                    f"{new_value!r}; a closing date somebody already set is an operator decision"
                )

    return tuple(violations)


async def _record(
    session_factory: async_sessionmaker[AsyncSession],
    outcome: DataRepairOutcome,
    app_version: str | None,
) -> bool:
    """Write one outcome into the ledger. Returns False if it could not be written.

    Its own session and its own transaction: a ledger that cannot be written
    must not roll back the repair it was trying to describe.
    """
    async with session_factory() as session:
        row = (
            await session.execute(select(DataRepairLedger).where(DataRepairLedger.repair_id == outcome.repair_id))
        ).scalar_one_or_none()
        if row is None:
            session.add(
                DataRepairLedger(
                    repair_id=outcome.repair_id,
                    runs=1,
                    rows_changed_total=outcome.rows_changed,
                    last_rows_changed=outcome.rows_changed,
                    last_outcome=outcome.status,
                    last_error=outcome.error,
                    app_version=app_version,
                )
            )
        else:
            row.runs = (row.runs or 0) + 1
            row.rows_changed_total = (row.rows_changed_total or 0) + outcome.rows_changed
            row.last_rows_changed = outcome.rows_changed
            row.last_outcome = outcome.status
            # Cleared, not left: a message from a failure three releases ago
            # reads as current the moment somebody greps for it.
            row.last_error = outcome.error
            row.app_version = app_version
        await session.commit()
    return True


async def run_data_repairs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    repairs: tuple[DataRepair, ...] | None = None,
    app_version: str | None = None,
) -> DataRepairReport:
    """Run every registered data repair once, in registry order.

    Each repair gets its own session and its own transaction, so one that raises
    neither rolls back the one before it nor stops the one after it. The ledger
    write happens in a third session for the same reason.

    The ledger is not read. A repair whose ledger row says ``applied`` runs
    again on the next boot exactly as it did on the first, and that is the
    design rather than an oversight - see the module docstring.

    Args:
        session_factory: Async session factory bound to the application engine.
        repairs: Override the registry. Only tests pass this; production runs
            :func:`discover_data_repairs`, which imports every module's
            ``repairs.py`` and then reads what registered.
        app_version: Release string recorded against each ledger row.

    Returns:
        A :class:`DataRepairReport` covering every repair attempted.
    """
    selected = discover_data_repairs() if repairs is None else repairs
    outcomes: list[DataRepairOutcome] = []
    ledger_written = True

    for repair in selected:
        try:
            async with session_factory() as session:
                changed = await repair.run(session)
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - a failed repair must not stop the boot
            outcome = DataRepairOutcome(
                repair_id=repair.repair_id,
                status="failed",
                rows_changed=0,
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.error(
                "Data repair %r FAILED (%s). This repair rewrites rows that the boot-time schema "
                "heal cannot reach, so the data it exists to fix is still wrong on this database. "
                "It is retried on the next start. %s",
                repair.repair_id,
                outcome.error,
                repair.summary,
                exc_info=True,
            )
        else:
            changed = int(changed or 0)
            outcome = DataRepairOutcome(
                repair_id=repair.repair_id,
                status="applied" if changed else "clean",
                rows_changed=changed,
            )
            if changed:
                # The only contemporaneous record that this boot altered rows a
                # user can see. INFO, not DEBUG, and it names the count.
                logger.info("Data repair %r changed %d row(s): %s", repair.repair_id, changed, repair.summary)
            else:
                logger.debug("Data repair %r: nothing to do", repair.repair_id)

        outcomes.append(outcome)

        try:
            await _record(session_factory, outcome, app_version)
        except Exception as exc:  # noqa: BLE001
            ledger_written = False
            logger.error(
                "Data repair ledger write FAILED for %r (%s: %s). The repair itself reported %r; "
                "what is lost is the record of it, so %s cannot answer what this install has run. "
                "On an external database this is usually the same missing DDL rights that stop the "
                "schema heal.",
                repair.repair_id,
                type(exc).__name__,
                exc,
                outcome.status,
                _LEDGER_TABLE,
                exc_info=True,
            )

    return DataRepairReport(outcomes=tuple(outcomes), ledger_written=ledger_written)
