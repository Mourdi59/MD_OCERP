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


@dataclass(frozen=True)
class DimensionReport:
    """One registry's answer about one country."""

    dimension: str
    verdict: str
    detail: str
    #: Countries this registry knows, when it is country-keyed. Empty otherwise.
    population: tuple[str, ...] = ()
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

    def summary(self) -> str:
        """One line, with unresolved kept out of the covered/missing arithmetic."""
        c = self.counts
        return (
            f"{self.country_code}: {c[COVERED]} covered, {c[FALLBACK]} fallback, "
            f"{c[MISSING]} missing, {c[NOT_KEYED]} not country-keyed, "
            f"{c[ABSENT]} absent, {c[UNRESOLVED]} UNRESOLVED"
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
# and parse the file without executing it when the import will not come. The
# report says which one answered, because they are not equally good evidence.
#
# WHERE A SOURCE PARSE IS ALLOWED, AND WHERE IT IS NOT. It answers structural
# questions - does this table have a country axis at all, how many rungs does
# this ladder have - because those are properties of what is written. It must
# never stand in for a behavioural question, because behaviour can sit in
# aliasing layers the table knows nothing about. calendar.schedule_regions is
# the worked example: parsing its table gets nine countries wrong, so that
# probe reports UNRESOLVED rather than accept a proxy it has measured to be bad.
#
# One thing is deliberately NOT caught here: if the import succeeds and the
# symbol is gone, the AttributeError propagates and becomes UNRESOLVED. That is
# a renamed registry, which is a real finding about the tree and must not be
# quietly patched over by reading the old name out of the source.
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


@_probe("calendar.schedule_regions")
def _schedule_calendar(country: str) -> DimensionReport:
    """Ask the resolver, because reading this table gives the wrong answer.

    ``WORK_CALENDARS`` is not keyed by country. Its keys are a mixed vocabulary
    - ISO codes (``US``, ``RU``), a non-ISO abbreviation (``UK``, where ISO says
    ``GB``), regional blocs (``DACH``, ``GULF``) and English country names
    (``CANADA``, ``FRANCE``) - and ``get_work_calendar`` puts two further
    aliasing layers in front of it, a full-label map and a first-token prefix
    map. So membership of the table is not the question a caller asks.

    Measured: reading the table for an ISO code calls ``GB``, ``DE``, ``CN``,
    ``IN``, ``FR``, ``ES``, ``BR``, ``AE`` and ``SA`` uncovered when every one
    of them aliases to a real regional calendar, while getting ``CA`` right for
    the wrong reason. Nine wrong answers stated confidently.

    Hence: no source-parse fallback here. If the resolver cannot be imported
    this probe reports UNRESOLVED, because the table it could still read is a
    known-bad proxy and a wrong answer is worse than a missing one.
    """
    source = "app.modules.schedule.service.get_work_calendar"
    try:
        from app.modules.schedule.service import WORK_CALENDARS, get_work_calendar
    except Exception as exc:  # noqa: BLE001
        return DimensionReport(
            dimension="calendar.schedule_regions",
            verdict=UNRESOLVED,
            detail=(
                f"resolver not importable ({type(exc).__name__}); the table is readable but is a "
                "known-bad proxy for it, so this probe declines to guess"
            ),
            source=source,
        )
    known = tuple(sorted(k for k in WORK_CALENDARS if k != "DEFAULT"))
    # Identity, not equality: "has a row of its own" is a question about which
    # object came back, and the resolver returns the table's own dicts.
    resolved_default = get_work_calendar(country) is WORK_CALENDARS["DEFAULT"]
    if not resolved_default:
        return DimensionReport(
            dimension="calendar.schedule_regions",
            verdict=COVERED,
            detail=f"the resolver returns a regional calendar for this code, among {len(known)} regions",
            population=known,
            source=source,
        )
    return DimensionReport(
        dimension="calendar.schedule_regions",
        verdict=FALLBACK,
        detail=(
            "the resolver falls through to WORK_CALENDARS['DEFAULT'] for this code; the caller gets a "
            f"working week and cannot tell it was not theirs ({len(known)} regions are named, none matches)"
        ),
        population=known,
        source=source,
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
    from app.modules.change_intelligence.time_bar import NOTICE_PERIODS

    standards = tuple(sorted(NOTICE_PERIODS))
    if not standards:
        return DimensionReport(
            dimension="contract.standard_families",
            verdict=UNRESOLVED,
            detail="NOTICE_PERIODS resolved but is empty",
            source="app.modules.change_intelligence.time_bar.NOTICE_PERIODS",
        )
    return DimensionReport(
        dimension="contract.standard_families",
        verdict=NOT_KEYED,
        detail=(
            f"keyed by standard, not by country ({', '.join(standards)}); "
            "no mapping from a country to the standards used there exists"
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
