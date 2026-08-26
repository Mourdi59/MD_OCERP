# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Sub-national jurisdictions that carry their own tax rate.

This is a registry of ISO 3166-2 subdivision codes, not a general ISO 3166-2
table. A country appears here only when the platform needs to tell three
answers apart:

* this subdivision levies its own tax on top of, or instead of, the federal one
* this subdivision levies nothing, and the federal rate really is the whole
  answer
* nobody said which subdivision this is

Without the registry the second and third collapse into each other. Alberta
charges no provincial sales tax, so the correct total there is the federal 5 %
- and 5 % is also what a resolver returns when it was handed a province it has
never heard of, or no province at all. Those must not be the same answer: one
is a rate a quantity surveyor can put in a tender, the other is a question
nobody answered. Membership of this registry is what separates them.

Canada is the only country listed. The United States has the same structure
(a zero-rate federal layer plus state sales taxes) but enumerating fifty states
and their rates is a separate piece of work, so ``US`` is deliberately absent
and a US subdivision therefore resolves as unknown rather than as federal-only.
That is the safe direction: it declines to answer instead of answering 0 %.
"""

from __future__ import annotations

import re

#: ISO 3166-2 shape: the alpha-2 country, a hyphen, then one to three
#: alphanumerics. Used to reject a malformed code before it is looked up, so
#: that "not in the registry" always means "we do not carry this jurisdiction"
#: rather than "you typed it wrong".
SUBDIVISION_CODE_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")

#: The ten provinces and three territories, ISO 3166-2:CA.
CANADA_SUBDIVISIONS: dict[str, str] = {
    "CA-AB": "Alberta",
    "CA-BC": "British Columbia",
    "CA-MB": "Manitoba",
    "CA-NB": "New Brunswick",
    "CA-NL": "Newfoundland and Labrador",
    "CA-NS": "Nova Scotia",
    "CA-NT": "Northwest Territories",
    "CA-NU": "Nunavut",
    "CA-ON": "Ontario",
    "CA-PE": "Prince Edward Island",
    "CA-QC": "Quebec",
    "CA-SK": "Saskatchewan",
    "CA-YT": "Yukon",
}

#: Countries whose subdivisions the platform enumerates, keyed by ISO 3166-1
#: alpha-2. A country absent from this mapping has no known-subdivision set,
#: so any subdivision quoted for it resolves as unknown.
KNOWN_SUBDIVISIONS: dict[str, dict[str, str]] = {
    "CA": CANADA_SUBDIVISIONS,
}


#: Which subdivision each shipped sub-national rate belongs to, keyed on
#: country plus tax code - the only place that identity existed before the
#: ``subdivision_code`` column, as a naming convention nothing enforced.
#:
#: This is a repair table, not a source of truth. It exists because a database
#: seeded before v3307 holds these rows with a NULL subdivision, and on most
#: installs alembic is stamped rather than run, so the revision's own backfill
#: never executes there. :func:`~app.modules.i18n_foundation.seed.
#: backfill_tax_subdivisions` replays it on every boot instead. Bounded at ten
#: entries and only ever written to a row whose subdivision is still NULL, so
#: it can never overwrite an operator's own correction.
SHIPPED_SUBDIVISION_BACKFILL: dict[tuple[str, str], str] = {
    ("CA", "HST_ON"): "CA-ON",
    ("CA", "HST_NS"): "CA-NS",
    ("CA", "HST_NB"): "CA-NB",
    ("CA", "HST_NL"): "CA-NL",
    ("CA", "HST_PE"): "CA-PE",
    ("CA", "QST_QC"): "CA-QC",
    ("CA", "PST_BC"): "CA-BC",
    ("CA", "PST_SK"): "CA-SK",
    ("CA", "RST_MB"): "CA-MB",
    ("US", "CA_SALES"): "US-CA",
}


def normalize_subdivision(code: str | None) -> str | None:
    """Upper-case and trim a subdivision code, mapping blank to ``None``.

    Args:
        code: A subdivision code as it arrived from a client, or ``None``.

    Returns:
        The canonical upper-case form, or ``None`` when nothing was supplied.
        An empty or whitespace-only string is ``None`` rather than ``""``:
        "no subdivision" has exactly one representation, so a row cannot say
        it twice in two different ways.
    """
    if code is None:
        return None
    stripped = code.strip().upper()
    return stripped or None


def is_known_subdivision(country_code: str, subdivision_code: str) -> bool:
    """Whether ``subdivision_code`` is a jurisdiction this platform enumerates.

    Args:
        country_code: ISO 3166-1 alpha-2, any case.
        subdivision_code: ISO 3166-2, any case.

    Returns:
        ``True`` only when the country has a registry AND the code is in it.
        A country with no registry always returns ``False``, which is what
        keeps an unenumerated jurisdiction out of the federal-only answer.
    """
    registry = KNOWN_SUBDIVISIONS.get(country_code.strip().upper())
    if registry is None:
        return False
    return (normalize_subdivision(subdivision_code) or "") in registry


def has_subdivision_axis(country_code: str) -> bool:
    """Whether the platform models sub-national tax rates for this country.

    A country with an axis cannot answer a tax question from the country code
    alone, so the resolver refuses to guess for it.
    """
    return country_code.strip().upper() in KNOWN_SUBDIVISIONS


def subdivision_name(country_code: str, subdivision_code: str) -> str | None:
    """Human-readable name of a registered subdivision, or ``None``.

    The name is English-only and is not a UI string: it exists so a log line
    or an API payload can say "Ontario" next to ``CA-ON``. Anything a user
    reads goes through i18n on the frontend.
    """
    registry = KNOWN_SUBDIVISIONS.get(country_code.strip().upper())
    if registry is None:
        return None
    return registry.get(normalize_subdivision(subdivision_code) or "")
