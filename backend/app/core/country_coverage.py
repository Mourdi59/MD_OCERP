# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Ask one question of every country-shaped registry in the product.

The product has several registries that vary by country, each invented where it
was needed and each with its own shape: a tuple of dicts with a ``country_code``
field, a dict keyed by region code with a ``DEFAULT`` entry, a dict of functions,
a seeded JSON file. Nothing could answer "is Canada covered", and the answer
turned out to be "it has a working calendar and no payment regime" - which
nobody had noticed, because there was nowhere to look.

**This module centralises the question and not the data.** Every registry stays
where it is and keeps its own shape; a probe here knows how to ask it. Adding a
country is still an edit in the owning module. That is the plugin principle and
this file does not trade it.

Reading a report
----------------

The six verdicts are deliberately not collapsible into "yes / no", because the
useful distinctions are between the shades of no:

``COVERED``      the registry has a row of this country's own.
``FALLBACK``     something resolves for this country, but by default or alias
                 rather than on its own terms. A caller sees an answer and
                 cannot tell it was not written for them.
``MISSING``      the registry is country-keyed, is populated, and this country
                 is not in it.
``NOT_KEYED``    the registry exists and has no country axis at all, so the
                 question cannot be put to it. Wanting a per-country answer here
                 means changing its shape, not adding a row.
``ABSENT``       no such registry exists anywhere in the product.
``UNRESOLVED``   the probe could not answer. An import failed, a symbol moved,
                 or a shape changed.

``UNRESOLVED`` is counted separately from ``MISSING`` everywhere, and that
separation is the point of the file. An instrument that reports what it could
not measure as an absence tells you a comfortable lie: it converts "I do not
know" into "there is nothing there", and the second reads as a finished
question. Unmeasured and fine are different words.

An empty population is treated as ``UNRESOLVED`` rather than as "every country
is missing", for the same reason. A probe that finds nothing at all has almost
certainly broken, and a registry that genuinely emptied is worth the same alarm.
"""

from __future__ import annotations

import ast
import importlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parents[1]

COVERED = "covered"
FALLBACK = "fallback"
MISSING = "missing"
NOT_KEYED = "not_keyed"
ABSENT = "absent"
UNRESOLVED = "unresolved"

#: Verdicts that mean the probe produced an answer about this country.
ANSWERED = (COVERED, FALLBACK, MISSING, NOT_KEYED, ABSENT)

#: What a country's row says when another country is on it too. Unlike the
#: shared spans in app.core.calendar, a shared row here is not a stand-in for an
#: unknown value: DACH and GULF are real regional weeks, written deliberately
#: for every country on them, so the verdict stays COVERED. It is recorded
#: because it is a limit rather than a defect. Per-country divergence has
#: nowhere to go until the row is split, which is how three Gulf states were
#: once given the wrong weekend, and a limit nobody counted is one that gets
#: rediscovered rather than remembered.
SHARED_ROW = "SHARED_ROW"


@dataclass(frozen=True)
class DimensionReport:
    """One registry's answer about one country."""

    dimension: str
    verdict: str
    detail: str
    #: Countries this registry knows, when it is country-keyed. Empty otherwise.
    population: tuple[str, ...] = ()
    #: Other countries that land on this country's row, when the registry has
    #: rows and this one is shared. Empty when the row is this country's alone,
    #: or when the registry has no notion of a row. See SHARED_ROW.
    shares_row_with: tuple[str, ...] = ()
    #: Where the registry lives, so a reader can go and look.
    source: str = ""
    #: How the probe got the value: "import" (the object the product runs on)
    #: or "source" (parsed from the file without executing it). A source parse
    #: is weaker evidence and is labelled so nobody has to guess which it was.
    method: str = "import"

    @property
    def answered(self) -> bool:
        return self.verdict in ANSWERED


@dataclass
class CountryReport:
    """Every registry's answer about one country."""

    country_code: str
    dimensions: list[DimensionReport] = field(default_factory=list)

    def by_verdict(self, verdict: str) -> list[DimensionReport]:
        return [d for d in self.dimensions if d.verdict == verdict]

    @property
    def counts(self) -> dict[str, int]:
        out = dict.fromkeys((*ANSWERED, UNRESOLVED), 0)
        for d in self.dimensions:
            out[d.verdict] = out.get(d.verdict, 0) + 1
        return out

    @property
    def shared_rows(self) -> list[DimensionReport]:
        """Dimensions that answered for this country off a row it does not own."""
        return [d for d in self.dimensions if d.shares_row_with]

    def summary(self) -> str:
        """One line, with unresolved kept out of the covered/missing arithmetic."""
        c = self.counts
        return (
            f"{self.country_code}: {c[COVERED]} covered, {c[FALLBACK]} fallback, "
            f"{c[MISSING]} missing, {c[NOT_KEYED]} not country-keyed, "
            f"{c[ABSENT]} absent, {c[UNRESOLVED]} UNRESOLVED, "
            f"{len(self.shared_rows)} on a shared row"
        )


# --------------------------------------------------------------------------- #
# Probe plumbing
#
# A probe returns a DimensionReport. It never raises: _run wraps it, so a moved
# symbol or a changed shape becomes UNRESOLVED with the reason attached rather
# than an absence or a traceback. That wrapper is the only reason a caller can
# trust the difference between "missing" and "could not tell".
# --------------------------------------------------------------------------- #

Probe = Callable[[str], DimensionReport]

_PROBES: list[tuple[str, Probe]] = []


def _probe(name: str) -> Callable[[Probe], Probe]:
    def register(fn: Probe) -> Probe:
        _PROBES.append((name, fn))
        return fn

    return register


def _run(name: str, fn: Probe, country: str) -> DimensionReport:
    try:
        return fn(country)
    except Exception as exc:  # noqa: BLE001 - any failure is "could not tell", never "absent"
        logger.debug("country-coverage probe %s failed", name, exc_info=True)
        return DimensionReport(
            dimension=name,
            verdict=UNRESOLVED,
            detail=f"probe raised {type(exc).__name__}: {exc}",
        )


# --------------------------------------------------------------------------- #
# Resolving a registry that lives in a module you cannot import
#
# Several of these registries are plain literals sitting in a service module,
# and importing that module pulls in the database configuration. On a developer
# machine with no cluster running, three probes came back UNRESOLVED for that
# reason alone - which is honest but useless, because the registries themselves
# are static and perfectly readable.
#
# So: import first, because that reads the object the product actually runs on,
# and read the file directly when the import will not come - by parse for a
# structural question, or by executing the registry's own definitions alone for
# a behavioural one. The report says which one answered, because an import and
# a read of the file on disk are not equally good evidence.
#
# WHERE A SOURCE READ IS ALLOWED, AND WHERE IT IS NOT. Parsing a table answers
# structural questions - does this table have a country axis at all, how many
# rungs does this ladder have - because those are properties of what is
# written. It must never stand in for a behavioural question by reading a table
# the behaviour does not read directly, because behaviour can sit in aliasing
# layers the table knows nothing about. calendar.schedule_regions is the worked
# example: sixteen of the eighteen countries on its axis are not keys of the
# table at all, so a membership test on the table calls sixteen countries
# uncovered while the resolver returns a real calendar for every one of them.
#
# Executing the resolver itself is a different act and is allowed. When the
# owning module will not import, that probe runs get_work_calendar and the maps
# it reads, alone, out of the same file - the product's own behaviour, run
# rather than guessed at from a neighbouring table. It is still labelled
# "source", because what ran is the file on disk and not the object the live
# process is holding.
#
# WHY A PROBE IS STILL ALLOWED TO REFUSE. If the import succeeds and the symbol
# is gone, the AttributeError propagates and the dimension comes back
# UNRESOLVED. Read that as the instrument working, not as a bug in it. A
# renamed registry is a real finding about the tree, and the second path exists
# to survive a missing database rather than to route around a missing name:
# reaching for it there would turn "this registry moved" into a confident
# answer assembled out of whatever the old name still matched. A probe that
# refuses is a probe reporting that it could not measure, which is the one
# thing this whole file is for.
# --------------------------------------------------------------------------- #


def _source_of(dotted: str) -> Path:
    if not dotted.startswith("app."):
        raise LookupError(f"{dotted} is outside the app package")
    return _APP_ROOT.joinpath(*dotted.split(".")[1:]).with_suffix(".py")


def _module_level_node(dotted: str, symbol: str) -> ast.AST:
    path = _source_of(dotted)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.ClassDef) and node.name == symbol:
            return node
        if any(isinstance(t, ast.Name) and t.id == symbol for t in targets):
            value = getattr(node, "value", None)
            if value is None:
                raise LookupError(f"{symbol} in {dotted} is annotated but never assigned")
            return value
    raise LookupError(f"{symbol} is not defined at module level in {dotted}")


def _bound_names(node: ast.stmt) -> set[str]:
    """Module-level names one statement binds.

    Args:
        node: A statement from a module body.

    Returns:
        The names the statement binds at module level, empty for statements that
        bind nothing.
    """
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign):
        return {node.target.id} if isinstance(node.target, ast.Name) and node.value is not None else set()
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {node.name}
    if isinstance(node, ast.Import | ast.ImportFrom):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    return set()


def _isolated_namespace(dotted: str, wanted: tuple[str, ...]) -> dict[str, object]:
    """Execute the named module-level definitions, and their dependencies, alone.

    For a registry whose owning module cannot be imported - typically because
    importing it builds a database engine - but whose registry and resolver are
    pure module-level code. The closure of module-level names the wanted symbols
    reach is collected, and only those statements are executed, so the import
    that blocks the module never runs unless something wanted needs it.

    This runs the product's own code rather than a parse of a table that code
    reads, which is why a resolver probe is allowed to use it where a table
    parse would be a known-bad proxy. The caller must still label the result
    "source": the file on disk ran, not the live module.

    Args:
        dotted: Dotted path of a module inside the app package.
        wanted: Module-level symbol names the caller needs.

    Returns:
        The namespace the selected statements executed in, holding at least
        every name in ``wanted``.

    Raises:
        LookupError: A wanted name, or a name it reaches, is not bound exactly
            once at module level. Twice means the probe cannot tell which
            binding the module ends up running on, and a stale one read
            silently is the failure this whole file exists to prevent.
    """
    path = _source_of(dotted)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    defining: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        for name in _bound_names(node):
            defining.setdefault(name, []).append(node)

    needed: set[str] = set()
    queue = list(wanted)
    while queue:
        name = queue.pop()
        if name in needed:
            continue
        found = defining.get(name, [])
        if len(found) != 1:
            raise LookupError(f"{name} is bound {len(found)} times at module level in {dotted}, expected once")
        needed.add(name)
        # Every module-level name the statement reads is part of the closure. A
        # function local that happens to share a module-level name pulls that
        # statement in too, which costs one extra definition and no correctness.
        queue.extend(
            sub.id
            for sub in ast.walk(found[0])
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load) and sub.id in defining
        )

    selected = [node for node in tree.body if _bound_names(node) & needed]
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    namespace: dict[str, object] = {"__name__": f"{dotted}:isolated", "__file__": str(path)}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def _annotated_attributes(dotted: str, symbol: str) -> tuple[set[str], str]:
    """Annotated attribute names of a class, by import if possible and by parse if not."""
    try:
        module = importlib.import_module(dotted)
    except Exception as exc:  # noqa: BLE001
        node = _module_level_node(dotted, symbol)
        if not isinstance(node, ast.ClassDef):
            raise LookupError(f"{symbol} in {dotted} is not a class") from exc
        names = {b.target.id for b in node.body if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name)}
        if not names:
            raise LookupError(f"{symbol} in {dotted} has no annotated attributes to read") from exc
        return names, f"source ({type(exc).__name__} on import)"
    return {c.name for c in getattr(module, symbol).__table__.columns}, "import"


def _keyed(
    dimension: str,
    source: str,
    population: set[str] | frozenset[str],
    country: str,
    *,
    fallback_note: str = "",
    method: str = "import",
) -> DimensionReport:
    """Standard verdict for a country-keyed registry.

    An empty population is UNRESOLVED, not "everyone is missing": a probe that
    resolved its symbol and then found nothing in it has more likely lost the
    shape than discovered an empty world.
    """
    members = tuple(sorted(population))
    if not members:
        return DimensionReport(
            dimension=dimension,
            verdict=UNRESOLVED,
            detail="registry resolved but its population is empty; the probe has probably lost the shape",
            source=source,
            method=method,
        )
    if country in population:
        return DimensionReport(
            dimension=dimension,
            verdict=COVERED,
            detail=f"a row of its own, among {len(members)} countries",
            population=members,
            source=source,
            method=method,
        )
    verdict = FALLBACK if fallback_note else MISSING
    detail = fallback_note or f"country-keyed and populated ({len(members)}), and this country is not in it"
    return DimensionReport(
        dimension=dimension,
        verdict=verdict,
        detail=detail,
        population=members,
        source=source,
        method=method,
    )


# --------------------------------------------------------------------------- #
# Calendars: four registries, deliberately probed as four.
#
# These are not one dimension wearing four hats. They were written
# independently, they are read by different callers, and they have disagreed
# with each other in production - a country has been correct in one and aliased
# to another country in a second. Collapsing them into a single "calendar" row
# would hide exactly the disagreement this file exists to surface.
# --------------------------------------------------------------------------- #


@_probe("calendar.holiday_functions")
def _holiday_functions(country: str) -> DimensionReport:
    from app.core.calendar import _HOLIDAY_FUNCS

    return _keyed(
        "calendar.holiday_functions",
        "app.core.calendar._HOLIDAY_FUNCS",
        set(_HOLIDAY_FUNCS),
        country,
    )


@_probe("calendar.working_week")
def _working_week(country: str) -> DimensionReport:
    from app.core.calendar import _WORKING_WEEK

    return _keyed(
        "calendar.working_week",
        "app.core.calendar._WORKING_WEEK",
        set(_WORKING_WEEK),
        country,
    )


_SCHEDULE_SERVICE = "app.modules.schedule.service"

#: What the schedule probe needs out of that module: the table, the resolver
#: standing in front of it, and the ISO axis that says which countries to ask.
_SCHEDULE_WANTED = ("WORK_CALENDARS", "get_work_calendar", "_CALENDAR_BY_COUNTRY")


def _schedule_registry() -> tuple[dict, Callable[[str], dict], dict[str, str], str]:
    """The schedule calendars, their resolver and their country axis, and how they were read.

    Imports the owning module when it will import. When it will not - which off
    a cluster is every developer machine, because importing it reaches
    ``app.database`` and that builds an engine at import time - the module-level
    definitions those three names reach are executed alone out of the same file.

    Returns:
        The calendar table, the resolver, the ISO-code axis, and the method
        string a report should carry.

    Raises:
        AttributeError: The module imported and one of the names is gone.
            Deliberately not caught; see the source-read policy above.
        LookupError: The module would not import and a name is not bound
            exactly once at module level in the file.
    """
    try:
        module = importlib.import_module(_SCHEDULE_SERVICE)
    except Exception as exc:  # noqa: BLE001 - having no cluster is an ordinary state, not a finding
        namespace = _isolated_namespace(_SCHEDULE_SERVICE, _SCHEDULE_WANTED)
        method = f"source ({type(exc).__name__} on import)"
        return (
            namespace["WORK_CALENDARS"],
            namespace["get_work_calendar"],
            namespace["_CALENDAR_BY_COUNTRY"],
            method,
        )
    # Outside the handler on purpose: if the import worked and a name has moved,
    # that AttributeError is the finding and must not reach the fallback.
    return module.WORK_CALENDARS, module.get_work_calendar, module._CALENDAR_BY_COUNTRY, "import"


def _calendar_rows(calendars: dict, resolve: Callable[[str], dict], axis: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """Group the countries on the axis by the calendar the resolver returns for each.

    Grouped by the identity of the object that comes back rather than by the
    axis map's values, because the resolver reads more maps than the axis and
    the resolver is what callers use. Two codes that reach one row by different
    routes are then still counted as one row rather than two.

    Args:
        calendars: The calendar table, whose dicts are the objects compared.
        resolve: The resolver.
        axis: The ISO-code axis. Read only for which countries to ask about,
            which is a structural question and so a fair thing to read it for.

    Returns:
        Row name to the sorted country codes that land on it.
    """
    named = {id(calendar): name for name, calendar in calendars.items()}
    rows: dict[str, list[str]] = {}
    for code in sorted(axis):
        rows.setdefault(named[id(resolve(code))], []).append(code)
    return {name: tuple(codes) for name, codes in rows.items()}


@_probe("calendar.schedule_regions")
def _schedule_calendar(country: str) -> DimensionReport:
    """Ask the resolver, because reading this table gives the wrong answer.

    ``WORK_CALENDARS`` is not keyed by country. Its keys are a mixed vocabulary
    - ISO codes (``US``, ``RU``), a non-ISO abbreviation (``UK``, where ISO says
    ``GB``), regional blocs (``DACH``, ``GULF``) and English country names
    (``CANADA``, ``FRANCE``) - and ``get_work_calendar`` puts three aliasing
    layers in front of it: a whole-label map, and two head maps that cannot
    overlap, one holding ISO country codes and one holding superseded catalogue
    codes that are not and cannot be ISO codes. So membership of the table is
    not the question a caller asks.

    Measured, and stated as a property of the registry rather than of whichever
    countries someone happened to ask about: of the eighteen countries on
    ``_CALENDAR_BY_COUNTRY``, sixteen are not keys of ``WORK_CALENDARS`` at all.
    A membership test on the table calls those sixteen uncovered while the
    resolver returns a real calendar for every one of them. Only ``US`` and
    ``RU`` are spelled the same way in both. Counted over a cohort instead, the
    same fact comes out as five, or ten, or sixteen depending on who was asked,
    which is how a number like this goes stale with nobody having edited it.

    Hence: no reading of the table as a proxy, ever. What the probe does when
    the module will not import is execute the resolver, and the maps it reads,
    alone out of that same file, and put the question to those - the product's
    own behaviour, run rather than guessed at from a neighbouring table, so the
    answer is the one the imported module gives. The report says "source"
    because what ran is the file on disk and not the live module.

    A renamed registry still ends as UNRESOLVED from either direction: the
    attribute lookup in :func:`_schedule_registry` sits outside its handler so
    its AttributeError propagates, and the isolated read raises ``LookupError``
    for a name it cannot find bound exactly once. That is a real finding about
    the tree, and the second path exists to survive a missing database rather
    than to route around a missing name.
    """
    source = "app.modules.schedule.service.get_work_calendar"
    calendars, resolve, axis, method = _schedule_registry()
    known = tuple(sorted(k for k in calendars if k != "DEFAULT"))
    # Identity, not equality: "has a row of its own" is a question about which
    # object came back, and the resolver returns the table's own dicts.
    calendar = resolve(country)
    if calendar is calendars["DEFAULT"]:
        return DimensionReport(
            dimension="calendar.schedule_regions",
            verdict=FALLBACK,
            detail=(
                "the resolver falls through to WORK_CALENDARS['DEFAULT'] for this code; the caller gets a "
                f"working week and cannot tell it was not theirs ({len(known)} regions are named, none matches)"
            ),
            population=known,
            source=source,
            method=method,
        )
    row = next(name for name, cal in calendars.items() if cal is calendar)
    shares = tuple(c for c in _calendar_rows(calendars, resolve, axis).get(row, ()) if c != country)
    detail = f"the resolver returns the {row} calendar for this code, among {len(known)} regions"
    if shares:
        detail += f"; {SHARED_ROW} with {', '.join(shares)}, so the row is not this country's alone"
    return DimensionReport(
        dimension="calendar.schedule_regions",
        verdict=COVERED,
        detail=detail,
        shares_row_with=shares,
        population=known,
        source=source,
        method=method,
    )


@_probe("calendar.seeded_rows")
def _seeded_calendar(country: str) -> DimensionReport:
    path = Path(__file__).resolve().parents[1] / "modules" / "i18n_foundation" / "seed_data" / "work_calendars.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = next(iter(rows.values()))
    known = {str(r.get("country_code")) for r in rows if isinstance(r, dict) and r.get("country_code")}
    return _keyed("calendar.seeded_rows", str(path.name), known, country)


# --------------------------------------------------------------------------- #
# The rest of the dimensions
# --------------------------------------------------------------------------- #


@_probe("payment.prompt_payment_regime")
def _payment_regimes(country: str) -> DimensionReport:
    from app.modules.payment_clock.data import NO_REGIME_HELD, PAYMENT_REGIMES, no_regime_reason

    known = {str(r.get("country_code")) for r in PAYMENT_REGIMES if r.get("country_code")}
    report = _keyed(
        "payment.prompt_payment_regime",
        "app.modules.payment_clock.data.PAYMENT_REGIMES",
        known,
        country,
    )
    if report.verdict != MISSING:
        return report
    # The country is confirmed absent from PAYMENT_REGIMES at this point (the
    # branch above returned already), so no_regime_reason cannot raise here;
    # its raise is reserved for a country that has a row of its own.
    if country in NO_REGIME_HELD:
        return replace(
            report,
            detail=(
                "no row; under active research and held rather than resolved, because a wrong-"
                "instrument search is not evidence of absence "
                "(see app.modules.payment_clock.data.NO_REGIME_HELD)"
            ),
        )
    reason = no_regime_reason(country)
    if reason is not None:
        return replace(
            report,
            detail=(
                f"no row, and a reason is on record: {reason} (see app.modules.payment_clock.data.no_regime_reason)"
            ),
        )
    return report


@_probe("tax.rates")
def _tax_rates(country: str) -> DimensionReport:
    path = Path(__file__).resolve().parents[1] / "modules" / "i18n_foundation" / "seed_data" / "tax_configurations.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = next(iter(rows.values()))
    known = {str(r.get("country_code")) for r in rows if isinstance(r, dict) and r.get("country_code")}
    return _keyed("tax.rates", str(path.name), known, country)


@_probe("contract.standard_families")
def _contract_standards(country: str) -> DimensionReport:
    """Keyed by standard, never by country - the question cannot be put to it.

    A standard belongs to a jurisdiction in the world (CCDC to Canada, VOB/B to
    Germany, AIA to the United States) and nothing in the tree records that. So
    this is not "Canada is missing a row": there is no axis on which Canada
    could have one. Making it per-country is a shape change.
    """
    from app.modules.change_intelligence.time_bar import NOTICE_PERIODS, NOTICE_PERIODS_HELD

    standards = tuple(sorted(NOTICE_PERIODS))
    if not standards:
        return DimensionReport(
            dimension="contract.standard_families",
            verdict=UNRESOLVED,
            detail="NOTICE_PERIODS resolved but is empty",
            source="app.modules.change_intelligence.time_bar.NOTICE_PERIODS",
        )
    # Standards that are recognised but carry no periods are named separately
    # rather than left out. Omitting them would read as "not supported" when
    # the truth is "recognised, periods not sourced yet", and the difference
    # decides whether somebody goes looking for the numbers.
    held = tuple(sorted(NOTICE_PERIODS_HELD))
    held_detail = f"; recognised without registered periods: {', '.join(held)}" if held else ""
    return DimensionReport(
        dimension="contract.standard_families",
        verdict=NOT_KEYED,
        detail=(
            f"keyed by standard, not by country ({', '.join(standards)}); "
            "no mapping from a country to the standards used there exists"
            f"{held_detail}"
        ),
        source="app.modules.change_intelligence.time_bar.NOTICE_PERIODS",
    )


@_probe("compliance.document_vocabulary")
def _compliance_documents(country: str) -> DimensionReport:
    """The credential vocabulary is closed and has no country axis."""
    from app.modules.credentials.schemas import CREDENTIAL_TYPES

    types = tuple(sorted(CREDENTIAL_TYPES))
    if not types:
        return DimensionReport(
            dimension="compliance.document_vocabulary",
            verdict=UNRESOLVED,
            detail="CREDENTIAL_TYPES resolved but is empty",
            source="app.modules.credentials.schemas.CREDENTIAL_TYPES",
        )
    return DimensionReport(
        dimension="compliance.document_vocabulary",
        verdict=NOT_KEYED,
        detail=(
            f"{len(types)} deliberately generic kinds with no country axis; a country-specific "
            "document (a workers-compensation clearance, a statutory declaration) has no way in"
        ),
        source="app.modules.credentials.schemas.CREDENTIAL_TYPES",
    )


@_probe("estimate.class_ladder")
def _estimate_ladder(country: str) -> DimensionReport:
    source = "app.modules.boq.service._AACE_CLASSES"
    node = _module_level_node("app.modules.boq.service", "_AACE_CLASSES")
    size = len(node.keys) if isinstance(node, ast.Dict) else 0
    if not size:
        return DimensionReport(
            dimension="estimate.class_ladder",
            verdict=UNRESOLVED,
            detail="_AACE_CLASSES resolved but is empty or is no longer a dict literal",
            source=source,
            method="source",
        )
    return DimensionReport(
        dimension="estimate.class_ladder",
        verdict=NOT_KEYED,
        detail=(
            f"one hardcoded ladder of {size} integer classes, not pack-resolved; "
            "a lettered national ladder has no representation"
        ),
        source=source,
        method="source",
    )


@_probe("security_of_payment.deadlines")
def _security_of_payment(country: str) -> DimensionReport:
    """No registry at all, which is different from an empty one.

    Declared rather than probed, because there is no symbol to resolve. Liens,
    hypothecs, notice-of-intent deadlines and bid security have no home in the
    tree; the only related data is static reference text served read-only for
    one US state, which is not a computed deadline for any country.
    """
    return DimensionReport(
        dimension="security_of_payment.deadlines",
        verdict=ABSENT,
        detail="no registry exists; nothing computes a lien or hypothec deadline from a construction event",
        source="(none)",
    )


@_probe("labour.rate_regions")
def _labour_regions(country: str) -> DimensionReport:
    """The rate template has no region column, so there is no axis to be on."""
    source = "app.modules.labor_rates.models.LaborRateTemplate"
    columns, method = _annotated_attributes("app.modules.labor_rates.models", "LaborRateTemplate")
    regional = columns & {"region", "province", "jurisdiction", "country_code", "state", "country"}
    if regional:
        # Not a verdict about the country: a regional column means this probe is
        # reading a model it was not written for, and its NOT_KEYED would be a
        # stale answer stated confidently. Say so instead.
        return DimensionReport(
            dimension="labour.rate_regions",
            verdict=UNRESOLVED,
            detail=f"a regional column appeared ({sorted(regional)}); this probe predates it and needs rewriting",
            source=source,
            method=method,
        )
    return DimensionReport(
        dimension="labour.rate_regions",
        verdict=NOT_KEYED,
        detail=(
            f"LaborRateTemplate carries {len(columns)} fields and none of them is a region, province, "
            "jurisdiction or country; there is no axis a country could be a value on"
        ),
        source=source,
        method=method,
    )


@dataclass(frozen=True)
class SharedRowCensus:
    """How a registry's countries split between rows of their own and shared rows.

    A per-country report structurally cannot carry this. Germany's report knows
    Germany is on a row with Austria and Switzerland; it cannot know how much of
    the registry is like that, and a figure that can only be had by reading
    every country's report one at a time is a figure that stops being counted.
    """

    dimension: str
    source: str
    #: How the registry was read, the same way a DimensionReport says it.
    method: str
    #: Row name to the countries on it, for every row more than one reaches.
    shared: dict[str, tuple[str, ...]]
    #: Countries whose row no other country on the axis reaches.
    on_own_row: tuple[str, ...]

    @property
    def on_shared_row(self) -> tuple[str, ...]:
        return tuple(sorted(code for codes in self.shared.values() for code in codes))

    @property
    def on_axis(self) -> int:
        return len(self.on_own_row) + len(self.on_shared_row)

    def summary(self) -> str:
        """One line, in the shape CountryReport.summary uses."""
        rows = "; ".join(f"{name} ({', '.join(codes)})" for name, codes in sorted(self.shared.items()))
        return (
            f"{self.dimension}: {len(self.on_shared_row)} of {self.on_axis} countries on the axis "
            f"are on a row shared with another country - {rows}"
        )


def shared_calendar_rows() -> SharedRowCensus:
    """Count the schedule calendar's shared rows, over its whole axis.

    Only calendar.schedule_regions answers this today. That is a statement about
    what has been measured and not a claim that nothing else groups countries:
    app.core.calendar points several holiday codes at another country's
    function, which is the same shape of question and is counted nowhere yet.
    If a second registry is given this treatment, this is the shape to give it.

    Returns:
        The census, taken over the registry's own axis rather than over any
        cohort, so the figure does not move when the list of countries somebody
        asked about does.

    Raises:
        AttributeError: A name has moved and the module still imports.
        LookupError: The module will not import and a name is not bound exactly
            once at module level.
    """
    calendars, resolve, axis, method = _schedule_registry()
    rows = _calendar_rows(calendars, resolve, axis)
    return SharedRowCensus(
        dimension="calendar.schedule_regions",
        source="app.modules.schedule.service._CALENDAR_BY_COUNTRY",
        method=method,
        shared={name: codes for name, codes in sorted(rows.items()) if len(codes) > 1},
        on_own_row=tuple(sorted(code for codes in rows.values() if len(codes) == 1 for code in codes)),
    )


def dimensions() -> tuple[str, ...]:
    """Every dimension this manifest knows how to ask about."""
    return tuple(name for name, _ in _PROBES)


def country_coverage(country_code: str) -> CountryReport:
    """Every registry's verdict for one ISO country code."""
    code = (country_code or "").strip().upper()
    report = CountryReport(country_code=code)
    for name, fn in _PROBES:
        report.dimensions.append(_run(name, fn, code))
    return report
