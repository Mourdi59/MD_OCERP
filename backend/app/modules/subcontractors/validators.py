# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure completeness and arithmetic checks for a subcontract agreement.

Validation is first-class for this module (platform principle #4). A
subcontract agreement leaving ``draft`` for ``active`` is the moment a
subcontractor may start work, raise payment applications against the scope and
accrue retention. Everything downstream reads the agreement rather than
re-deriving it: :meth:`SubcontractorService.sov_summary` divides by the
agreement's ``total_value``, :meth:`accrue_retention` multiplies by its
``retention_percent``, and the payment-application chain settles in its
``currency``. An agreement that goes live with a zero value, a blank currency
or work packages worth more than the contract produces reports nobody can
reconcile, and the error surfaces weeks later inside a payment claim.

Like ``procurement/validators.py`` this module is deliberately
**dependency-free**: standard library plus :class:`~decimal.Decimal`, no ORM,
no FastAPI, no session. The rule classes in ``app.core.validation.rules`` stay
thin wrappers translating a :class:`Finding` into a ``RuleResult``, so the
checks themselves are unit-testable without a database.

Payload shape
-------------
The service flattens an agreement, its work packages and the parts of the
subcontractor row these checks need into one dict. Money arrives as Decimal
strings and dates as ``YYYY-MM-DD`` strings, both parsed here rather than by
the caller.

The clock is data, never ``date.today()``
-----------------------------------------
Every date-relative check reads :data:`AS_OF_KEY` from the payload. The service
fills it with today's date; a test passes it explicitly. A rule that asks the
system clock what day it is cannot be pinned by a test that still passes next
year, so no check in this module calls ``today()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

# The one spelling an amount gets anywhere in this platform. It lives in its own
# module precisely so that this file can keep the standard-library-only contract
# its docstring declares: the same function is what the core validation rules
# call, and a second spelling here would disagree with them on every currency
# that does not have two decimals.
from app.core.currency_registry import sentence_amount

#: Payload key carrying the date the checks should consider "now". The service
#: fills it; tests set it explicitly so date-relative rules stay deterministic.
AS_OF_KEY = "as_of"

#: Amounts closer than this are equal, matching the procurement tolerance.
MONEY_TOLERANCE = Decimal("0.01")

#: Retention above this is a data-entry error rather than retention. The
#: construction norm is 5-10%; past half the contract it is not a holdback.
MAX_SANE_RETENTION_PERCENT = Decimal("50")


@dataclass(frozen=True)
class Finding:
    """One failed check on one element.

    :param element_ref: what the user should look at -- a work-package name or
        the agreement title. Never ``None``: a finding the UI cannot anchor is
        a finding the user cannot act on.
    :param params: placeholders for the translated message, pre-formatted as
        strings so the message layer never formats money or dates itself.
    :param details: machine-readable context for the report payload.
    """

    element_ref: str
    params: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


def parse_money(raw: Any) -> Decimal | None:
    """Parse a Decimal-string amount, or ``None`` when it is not a number.

    Returning ``None`` rather than raising is deliberate: an unparseable amount
    is itself a finding, and the caller decides how to report it.
    """
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _money(raw: Any) -> Decimal:
    """Parse an amount, treating anything unparseable as zero."""
    parsed = parse_money(raw)
    return parsed if parsed is not None else Decimal("0")


def _fmt(value: Decimal) -> str:
    """Render a *percentage* for a user-facing message, two decimals, no exponent.

    Not for money, despite the name it has always had. Money goes through
    :func:`_amount`, which asks the currency how many decimals it keeps and
    writes the code beside the digits. The retention template glues ``%`` onto
    its slot, so an amount rendered through this function would read
    ``50.00 EUR%``, and grouping a percentage gains a reader nothing.
    """
    return f"{value.quantize(Decimal('0.01')):f}"


def _currency(agreement: dict[str, Any]) -> str:
    """The code this agreement states, never a default.

    Blank stays blank: the renderer then groups the digits and writes no code.
    :func:`check_currency_set` is the rule that complains about a missing
    currency, so nothing is lost by declining to guess one here, and a guessed
    code would read as authoritative and be wrong whenever the project is not in
    it.
    """
    return str(agreement.get("currency") or "").strip()


def _amount(value: Decimal, agreement: dict[str, Any]) -> str:
    """Render an amount for a message, in the agreement's own currency."""
    return sentence_amount(value, _currency(agreement))


def parse_date(raw: Any) -> date | None:
    """Parse the leading ``YYYY-MM-DD`` of a date value, or ``None``.

    Anything that is not an ISO date is treated as absent rather than as a
    finding: these checks are about ordering and expiry, not about format, and
    the columns are already typed as ``Date`` at the database level.
    """
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_of(agreement: dict[str, Any]) -> date | None:
    """The date the checks treat as today, or ``None`` when the caller omitted it."""
    return parse_date(agreement.get(AS_OF_KEY))


def _packages(agreement: dict[str, Any]) -> list[dict[str, Any]]:
    packages = agreement.get("work_packages")
    return [p for p in packages if isinstance(p, dict)] if isinstance(packages, list) else []


def _agreement_ref(agreement: dict[str, Any]) -> str:
    return str(agreement.get("title") or agreement.get("id") or "?")


def package_label(index: int, package: dict[str, Any]) -> str:
    """A human work-package label: the 1-based row number plus a trimmed name."""
    name = str(package.get("name") or "").strip()
    if not name:
        return str(index + 1)
    if len(name) > 40:
        name = name[:37] + "..."
    return f"{index + 1} ({name})"


# ── Checks ───────────────────────────────────────────────────────────────────


def check_has_scope(agreement: dict[str, Any]) -> list[Finding]:
    """An agreement going live must break its scope into work packages.

    Without them there is nothing for a payment application to claim against:
    every payment line carries a ``work_package_id``, so an active agreement
    with no packages can only ever be paid against nothing, and the schedule of
    values reports a contract value with no lines under it.
    """
    if _packages(agreement):
        return []
    return [Finding(element_ref=_agreement_ref(agreement), details={"work_package_count": 0})]


def check_package_scope_described(agreement: dict[str, Any]) -> list[Finding]:
    """Each work package should say what the work actually is.

    A named package with no scope text is the classic source of a variation
    argument: both sides agreed on a title and neither wrote down what it
    covers. WARNING rather than ERROR -- the scope often lives in an attached
    specification during the first weeks of a contract.
    """
    findings: list[Finding] = []
    for index, package in enumerate(_packages(agreement)):
        if not str(package.get("scope") or "").strip():
            findings.append(
                Finding(
                    element_ref=package_label(index, package),
                    params={"package": package_label(index, package)},
                    details={"scope": None},
                )
            )
    return findings


def check_value_positive(agreement: dict[str, Any]) -> list[Finding]:
    """The contract value must be greater than zero.

    Retention is a percentage of it and the schedule of values divides by it, so
    a zero-value active agreement makes both meaningless and any percent-complete
    figure derived from it is a division by zero the reporting layer has to hide.
    """
    total = parse_money(agreement.get("total_value"))
    if total is None:
        return [
            Finding(
                element_ref=_agreement_ref(agreement),
                params={"value": "?"},
                details={"reason": "unparseable_total_value"},
            )
        ]
    if total > 0:
        return []
    return [
        Finding(
            element_ref=_agreement_ref(agreement),
            params={"value": _amount(total, agreement)},
            details={"total_value": str(total)},
        )
    ]


def check_packages_within_value(agreement: dict[str, Any]) -> list[Finding]:
    """The work packages must not be worth more than the contract itself.

    Packages priced above ``total_value`` mean the agreement is under-funded on
    the day it goes live: the sum of what the subcontractor may legitimately
    claim already exceeds what was contracted, and the overrun only becomes
    visible once claims start arriving.

    Skipped when there are no packages -- :func:`check_has_scope` already owns
    that case and reporting it twice would double-count one problem.
    """
    packages = _packages(agreement)
    if not packages:
        return []
    planned = sum((_money(p.get("planned_value")) for p in packages), Decimal("0"))
    total = _money(agreement.get("total_value"))
    if planned - total <= MONEY_TOLERANCE:
        return []
    return [
        Finding(
            element_ref=_agreement_ref(agreement),
            params={"planned": _amount(planned, agreement), "total": _amount(total, agreement)},
            details={"planned_value_sum": str(planned), "total_value": str(total)},
        )
    ]


def check_dates_ordered(agreement: dict[str, Any]) -> list[Finding]:
    """The contract cannot end before it starts."""
    start = parse_date(agreement.get("start_date"))
    end = parse_date(agreement.get("end_date"))
    if start is None or end is None or end >= start:
        return []
    return [
        Finding(
            element_ref=_agreement_ref(agreement),
            params={"start": start.isoformat(), "end": end.isoformat()},
            details={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
    ]


def check_currency_set(agreement: dict[str, Any]) -> list[Finding]:
    """The agreement must carry a currency.

    The column's server default is an empty string, so a blank value here means
    nothing ever set it. Every payment application under the agreement inherits
    that currency, and an amount without one cannot be rolled up or paid.
    """
    if str(agreement.get("currency") or "").strip():
        return []
    return [Finding(element_ref=_agreement_ref(agreement), details={"currency": ""})]


def check_retention_within_bounds(agreement: dict[str, Any]) -> list[Finding]:
    """Retention must be a percentage, and a plausible one.

    ``accrue_retention`` multiplies each payment by this number, so a rate typed
    as an amount withholds a fortune from the first claim.
    """
    percent = parse_money(agreement.get("retention_percent"))
    if percent is None:
        return [
            Finding(
                element_ref=_agreement_ref(agreement),
                params={"percent": "?", "max": _fmt(MAX_SANE_RETENTION_PERCENT)},
                details={"reason": "unparseable_percent"},
            )
        ]
    if Decimal("0") <= percent <= MAX_SANE_RETENTION_PERCENT:
        return []
    return [
        Finding(
            element_ref=_agreement_ref(agreement),
            params={"percent": _fmt(percent), "max": _fmt(MAX_SANE_RETENTION_PERCENT)},
            details={"retention_percent": str(percent), "max": str(MAX_SANE_RETENTION_PERCENT)},
        )
    ]


def check_insurance_valid_at_start(agreement: dict[str, Any]) -> list[Finding]:
    """The subcontractor's insurance must still be valid when work starts.

    Letting an uninsured subcontractor on site is the exposure the module's own
    ``flag_expiring_insurance`` sweep exists to prevent, and activation is the
    last moment anyone looks before the work begins.

    Compared against the agreement's ``start_date`` when it has one, otherwise
    against :data:`AS_OF_KEY`. An unknown expiry date produces no finding: the
    column is nullable and a missing certificate is the certificate register's
    problem, not a reason to call a known-good date expired.
    """
    expiry = parse_date(agreement.get("insurance_expiry_date"))
    if expiry is None:
        return []
    reference = parse_date(agreement.get("start_date")) or _as_of(agreement)
    if reference is None or expiry >= reference:
        return []
    return [
        Finding(
            element_ref=_agreement_ref(agreement),
            params={"expiry": expiry.isoformat(), "reference": reference.isoformat()},
            details={
                "insurance_expiry_date": expiry.isoformat(),
                "reference_date": reference.isoformat(),
            },
        )
    ]
