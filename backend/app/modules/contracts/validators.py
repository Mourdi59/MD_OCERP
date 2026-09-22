# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts validation rules.

Ships five first-class rules registered with the platform rule registry under
the ``contracts`` rule set, of which the first three are:

* ``ContractPartyRolesRule`` (ERROR) - a contract must name the two parties
  that execute it.
* ``ContractPerformanceBondRule`` (WARNING) - a contract whose terms require a
  performance bond should have an active security row of that type.
* ``EOTDaysRule`` (ERROR) - a decided extension-of-time claim must never grant
  more days than were claimed.

The rules run against a plain dict context (no ORM), shaped by the service /
caller as::

    {
        "contract": {"id", "status", "contract_type", "terms": {...}},
        "parties": [{"party_role", "party_type", "display_name", ...}],
        "securities": [{"security_type", "status", ...}],
        "eot_claims": [{"eot_number", "days_claimed", "days_granted", "status"}],
    }

``display_name`` is the name the party would appear under on a signature
block, which is not always the stored one: a party entered as a link to a
contact, a subcontractor or a user carries no stored name at all. The service
resolves that before it builds the context, so a rule reading the field never
has to know which of the two it got.

Keeping the rules pure and dict-driven makes them trivially unit-testable and
satisfies the platform "no module without validation rules" requirement.

A second rule set, ``pay_application``, checks one progress claim as the
payment application it becomes. It runs when a claim is submitted (errors
block) and on ``GET /progress-claims/{id}/validation``, over a context the
service builds in ``ContractsService.claim_rule_context``::

    {
        "claim": {"id", "number", "status", "period_start", "period_end",
                  "claim_date", "period_from", "period_to", "application_date"},
        "previous_claim": {"id", "number", "period_from", "period_to"} | None,
        "lines": [{"contract_line_id", "code", "description", "scheduled_value",
                   "total_completed_stored", ...}],
        "percent_regressed": [{"contract_line_id", "code", "observed_pct",
                               "requested_value", "previous_value"}],
        "currency": "USD",
        "as_of": "2026-03-31" | None,
        "<key>": ...,   # one entry per provider in contracts.claim_context
    }

Dates arrive as ISO strings and amounts as decimal strings, so the context is
plain data. ``as_of`` is the claim's period end: "the clock is data", so a
check about what was valid at the end of the period gives the same answer when
it is re-run a year later. The findings are worded through the module's own
message bundle in the caller's language. Keys past the core ones come from
other modules through :mod:`app.modules.contracts.claim_context`; with none
registered they are absent, and rules that read one treat absence as "nothing
to check".
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.currency_registry import sentence_amount
from app.core.validation.engine import (
    RuleCategory,
    RuleResult,
    Severity,
    ValidationContext,
    ValidationRule,
    rule_registry,
)
from app.modules.contracts.messages import translate
from app.modules.contracts.signing_bridge import SIGNING_PARTY_ROLES

logger = logging.getLogger(__name__)

#: Rule set this module's rules register under.
CONTRACTS_RULE_SET = "contracts"

#: Rule set that checks one progress claim as a payment application. Other
#: modules register rules into it too (subcontractor pay apps rolled into the
#: claim register from the subcontractors module), which is why it is a name
#: callers import rather than a literal each of them spells.
PAY_APPLICATION_RULE_SET = "pay_application"

#: How many parties have to be nameable before a contract can be executed. Two,
#: because a contract is an agreement between two sides and a document only one
#: side has signed is not a contract.
#:
#: Which roles those two sides go by is deliberately *not* stated here. It is
#: :data:`~app.modules.contracts.signing_bridge.SIGNING_PARTY_ROLES`, imported
#: rather than restated, so that "this rule passed" and "there is somebody for
#: the signature block to address" are one fact rather than two lists that
#: happen to agree until one of them is edited.
REQUIRED_SIGNATORY_COUNT = 2


def _data(context: ValidationContext) -> dict[str, Any]:
    return context.data if isinstance(context.data, dict) else {}


def _contract(context: ValidationContext) -> dict[str, Any]:
    contract = _data(context).get("contract")
    return contract if isinstance(contract, dict) else {}


def _rows(context: ValidationContext, key: str) -> list[dict[str, Any]]:
    rows = _data(context).get(key, [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _truthy(value: Any) -> bool:
    """Coerce a JSON-ish flag (bool / "true" / 1 / "yes") to a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "required")
    return False


def _signing_roles(parties: list[dict[str, Any]], *, named: bool) -> set[str]:
    """Signing roles on a party register, counted the way the signature block counts them.

    ``named=True`` returns the roles a signature block could actually address;
    ``named=False`` returns every signing role present, named or not. Roles are
    a set in both cases because ``signatory_map_from_parties`` takes one party
    per role: a second row in a role already taken is dropped, so two
    contractor rows are one signatory and counting rows would overstate the
    register.
    """
    roles: set[str] = set()
    for party in parties:
        role = str(party.get("party_role", "") or "").strip()
        if role not in SIGNING_PARTY_ROLES:
            continue
        if named and not str(party.get("display_name", "") or "").strip():
            continue
        roles.add(role)
    return roles


class ContractPartyRolesRule(ValidationRule):
    """A contract must name the two parties that execute it.

    Two *distinct signing roles*, each carrying a name - not a named employer
    and a named contractor. Which two roles sign depends on the contract: a
    main contract runs employer to contractor, a subcontract runs contractor to
    subcontractor, and the same firm is the buying side of one and the selling
    side of the other. An earlier version of this rule asked for an employer
    and a contractor by name, which is true of a main contract and false of
    every subcontract in the register - the employer is not a party to those
    and deliberately does not appear on them. That rule reported the whole
    subcontract register as incomplete for a party it should never have.

    Distinct roles rather than two rows, because the signature block takes one
    party per role. Two contractor rows and nobody else produce a single
    signatory, which is a contract with itself.

    Applies at every status, including ``draft``. An earlier version applied
    only to a signed contract, on the reasoning that a draft may still be
    assembling its register - but the moment the register has to be complete
    is the moment somebody puts the contract up for signature, and that only
    ever happens on a draft. So the rule that checked the party register could
    never fire while there was still something a person could do about it, and
    the check that actually stopped the press was a hardcoded refusal in the
    service with no rule id, no suggestion and no way to see it coming.

    Reporting an incomplete register on a brand-new draft is not noise: the
    panel this feeds is a completeness traffic light, "incomplete" is the true
    answer for a contract with nobody on it, and the finding carries the
    suggestion that fixes it. Nothing blocks on the finding except the signing
    gate, which is exactly the moment it should.
    """

    rule_id = "contracts.parties_complete"
    name = "Contract names the parties that sign it"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "A contract must name two parties in different signing roles"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        contract = _contract(context)
        # A context with no contract in it is not a contract with no parties.
        # The compliance gate runs the same engine over a schedule of values
        # and passes positions only, so without this guard the rule would
        # report a missing party against a payload that has no register in it.
        if not contract:
            return []
        parties = _rows(context, "parties")
        named = _signing_roles(parties, named=True)
        nameless = _signing_roles(parties, named=False) - named
        passed = len(named) >= REQUIRED_SIGNATORY_COUNT
        if passed:
            message, suggestion = "OK", None
        else:
            message = f"Contract names {len(named)} of the {REQUIRED_SIGNATORY_COUNT} parties that sign it"
            if nameless:
                # The rows are there and the signature block still cannot
                # address them, which reads on screen as a register already
                # full. Say which ones rather than asking for a party that is
                # sitting in front of the reader.
                message += f", and the register carries no name for: {', '.join(sorted(nameless))}"
                suggestion = "Name every party that signs, or link it to a company on the register"
            else:
                roles = ", ".join(SIGNING_PARTY_ROLES)
                suggestion = f"Add both sides to the contract's party register, using the roles that sign: {roles}"
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=passed,
                message=message,
                element_ref=str(contract.get("id", "")),
                suggestion=suggestion,
            )
        ]


class ContractPerformanceBondRule(ValidationRule):
    """A contract that requires a performance bond should hold an active one."""

    rule_id = "contracts.performance_bond_active"
    name = "Required performance bond is active"
    standard = CONTRACTS_RULE_SET
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS
    description = "A contract whose terms require a performance bond should have an active bond"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        contract = _contract(context)
        terms = contract.get("terms") if isinstance(contract.get("terms"), dict) else {}
        securities = _rows(context, "securities")
        # "Required" is signalled either by a terms flag or by a tracked bond
        # row still sitting in the "required" state.
        flagged = _truthy(terms.get("requires_performance_bond"))
        tracked = any(
            s.get("security_type") == "performance_bond" and s.get("status") == "required" for s in securities
        )
        if not (flagged or tracked):
            return []
        has_active = any(
            s.get("security_type") == "performance_bond" and s.get("status") == "active" for s in securities
        )
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=has_active,
                message="OK" if has_active else "Required performance bond is not active",
                element_ref=str(contract.get("id", "")),
                suggestion=(None if has_active else "Record an active performance bond security"),
            )
        ]


class EOTDaysRule(ValidationRule):
    """An EOT claim must never grant more days than were claimed."""

    rule_id = "contracts.eot_days_valid"
    name = "EOT granted days within claimed days"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "An extension-of-time claim cannot grant more days than were claimed"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for claim in _rows(context, "eot_claims"):
            try:
                claimed = int(claim.get("days_claimed", 0) or 0)
                granted = int(claim.get("days_granted", 0) or 0)
            except (TypeError, ValueError):
                # A non-numeric value is itself a data fault; flag it.
                claimed, granted = 0, 1
            passed = granted <= claimed
            number = claim.get("eot_number") or claim.get("id") or "claim"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=("OK" if passed else f"EOT {number} grants {granted} day(s) but only {claimed} claimed"),
                    element_ref=str(claim.get("id", "")),
                    suggestion=None if passed else "Reduce granted days to at most the claimed days",
                )
            )
        return results


class ContractTemplatePinnedRule(ValidationRule):
    """A contract that names a clause template must pin the version it used."""

    rule_id = "contracts.template_version_pinned"
    name = "Clause template reference pins a version"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "A contract drawn from a clause template must record which version of it"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        contract = _contract(context)
        code = contract.get("template_code")
        version = contract.get("template_version")
        # No template at all is a legitimate state: most contracts predate the
        # feature and plenty are written from scratch. The rule is about the
        # pair being half filled, not about having one.
        if not code and version is None:
            return []
        # Version 0 is the built-in standard forms, which carry no versions of
        # their own, so zero is a complete answer and not a missing one.
        passed = bool(code) and version is not None
        if passed:
            message = "OK"
            suggestion = None
        elif code:
            message = f"Contract names clause template '{code}' without a version"
            suggestion = "Re-resolve the template so the version it was drawn from is stored"
        else:
            message = f"Contract carries clause template version {version} with no template code"
            suggestion = "Clear the version, or record the template code it belongs to"
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=passed,
                message=message,
                element_ref=str(contract.get("id", "")),
                suggestion=suggestion,
            )
        ]


class ContractTemplateClausesRule(ValidationRule):
    """A published clause template version must actually hold clauses."""

    rule_id = "contracts.template_has_clauses"
    name = "Published clause template is not empty"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "A published clause template version must hold at least one clause"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for template in _rows(context, "templates"):
            # A draft is allowed to be empty; that is what drafting is. Only a
            # published version makes a promise, because that is the one a
            # contract can name.
            if str(template.get("status", "")) != "published":
                continue
            try:
                count = int(template.get("clause_count", 0) or 0)
            except (TypeError, ValueError):
                count = 0
            passed = count > 0
            label = f"{template.get('code', 'template')} v{template.get('version', '?')}"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=("OK" if passed else f"Published clause template {label} holds no clauses"),
                    element_ref=str(template.get("id", "")),
                    suggestion=(None if passed else "Add clauses to the template, or archive the version"),
                )
            )
        return results


# ── pay_application: one progress claim as a payment application ─────────

#: Below this, two money figures are the same number. The G703 figures the
#: line rule compares are rounded to cents before they reach it.
_MONEY_EPSILON = Decimal("0.01")

#: Two consecutive periods may touch (March 31 then April 1) without a gap.
#: Anything wider leaves days that no claim bills.
_ADJACENT_DAYS = 1

#: The period strings a claim carries and the message key naming each one.
#: Spelled out rather than built from the column name, so every key the rules
#: can ask for is a literal the message coverage test can find.
_PERIOD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("period_start", "period_from", "pay_application.period_unparsed.fields.period_start"),
    ("period_end", "period_to", "pay_application.period_unparsed.fields.period_end"),
    ("claim_date", "application_date", "pay_application.period_unparsed.fields.claim_date"),
)


def _locale(context: ValidationContext) -> str:
    """The caller's locale, defaulting to English."""
    meta = getattr(context, "metadata", None) or {}
    return str(meta.get("locale") or "en")


def _section(context: ValidationContext, key: str) -> dict[str, Any]:
    value = _data(context).get(key)
    return value if isinstance(value, dict) else {}


def _iso_day(value: Any) -> date | None:
    """A context date back to a ``date``; anything unreadable is absent."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _percent(value: Any) -> str:
    """A stored percent as a person writes it: 60 rather than 60.0000."""
    return format(_money(value).normalize(), "f")


def _claim_label(claim: dict[str, Any]) -> str:
    return str(claim.get("number") or claim.get("id") or "")


class _ClaimRule(ValidationRule):
    """Shared result builder for the pay_application rules."""

    standard = PAY_APPLICATION_RULE_SET

    def _result(
        self,
        context: ValidationContext,
        *,
        passed: bool,
        element_ref: str,
        fail_key: str = "",
        suggestion_key: str = "",
        **params: Any,
    ) -> RuleResult:
        locale = _locale(context)
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.name,
            severity=self.severity,
            category=self.category,
            passed=passed,
            message=translate("common.ok", locale=locale) if passed else translate(fail_key, locale=locale, **params),
            element_ref=element_ref,
            suggestion=None if passed else translate(suggestion_key, locale=locale),
            details={} if passed else {k: str(v) for k, v in params.items()},
        )


class ClaimPeriodPresentRule(_ClaimRule):
    """A claim has to say when its period ends.

    The period end is what orders a claim among the contract's claims, and
    that order decides what counts as previously certified. A claim with no
    end sorts after every dated one, which is the least wrong place for it and
    still a guess. Only a blank period end is reported here; a period end that
    was entered and cannot be read is ``period_unparsed``'s finding, so one
    mistake does not show up twice.
    """

    rule_id = "pay_application.period_present"
    name = "Claim period has an end date"
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS
    description = "A progress claim must record the last day of the period it bills"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        if not claim:
            return []
        if claim.get("period_to") is None and str(claim.get("period_end") or "").strip():
            return []
        passed = claim.get("period_to") is not None
        return [
            self._result(
                context,
                passed=passed,
                element_ref=str(claim.get("id", "")),
                fail_key="pay_application.period_present.fail",
                suggestion_key="pay_application.period_present.suggestion",
                claim=_claim_label(claim),
            )
        ]


class ClaimPeriodOrderRule(_ClaimRule):
    """A claim's period cannot end before it begins."""

    rule_id = "pay_application.period_order"
    name = "Claim period starts before it ends"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "A progress claim's period start must not fall after its period end"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        start, end = _iso_day(claim.get("period_from")), _iso_day(claim.get("period_to"))
        if start is None or end is None:
            # Nothing to order. A missing end is period_present's finding.
            return []
        return [
            self._result(
                context,
                passed=start <= end,
                element_ref=str(claim.get("id", "")),
                fail_key="pay_application.period_order.fail",
                suggestion_key="pay_application.period_order.suggestion",
                claim=_claim_label(claim),
                period_from=start.isoformat(),
                period_to=end.isoformat(),
            )
        ]


class ClaimPeriodOverlapRule(_ClaimRule):
    """A claim should not bill days the previous claim already billed.

    "Previous" is the claim immediately before this one in period order that
    was not rejected. A rejected claim billed nothing, so a period that
    overlaps it is not billed twice.
    """

    rule_id = "pay_application.period_overlap"
    name = "Claim period does not overlap the previous claim"
    severity = Severity.WARNING
    category = RuleCategory.CONSISTENCY
    description = "A progress claim's period should start after the previous claim's period ends"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        previous = _section(context, "previous_claim")
        start = _iso_day(claim.get("period_from"))
        previous_end = _iso_day(previous.get("period_to"))
        if start is None or previous_end is None:
            return []
        return [
            self._result(
                context,
                passed=start > previous_end,
                element_ref=str(claim.get("id", "")),
                fail_key="pay_application.period_overlap.fail",
                suggestion_key="pay_application.period_overlap.suggestion",
                claim=_claim_label(claim),
                period_from=start.isoformat(),
                previous=_claim_label(previous),
                previous_to=previous_end.isoformat(),
            )
        ]


class ClaimPeriodGapRule(_ClaimRule):
    """Consecutive claims should leave no days unbilled between them."""

    rule_id = "pay_application.period_gap"
    name = "Claim period follows on from the previous claim"
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS
    description = "A progress claim's period should start the day after the previous claim's period ends"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        previous = _section(context, "previous_claim")
        start = _iso_day(claim.get("period_from"))
        previous_end = _iso_day(previous.get("period_to"))
        if start is None or previous_end is None or start <= previous_end:
            # No pair to compare, or an overlap, which is the other rule's.
            return []
        gap = (start - previous_end).days
        return [
            self._result(
                context,
                passed=gap <= _ADJACENT_DAYS,
                element_ref=str(claim.get("id", "")),
                fail_key="pay_application.period_gap.fail",
                suggestion_key="pay_application.period_gap.suggestion",
                claim=_claim_label(claim),
                period_from=start.isoformat(),
                days=gap - 1,
                previous=_claim_label(previous),
                previous_to=previous_end.isoformat(),
            )
        ]


class ClaimPeriodUnparsedRule(_ClaimRule):
    """A period string was entered and no date can be read from it.

    Every write path takes ``YYYY-MM-DD``, so this fires on data that arrived
    some other way, and the boot repair leaves such a date NULL rather than
    guessing between day-month and month-day orders.
    """

    rule_id = "pay_application.period_unparsed"
    name = "Claim period dates can be read"
    severity = Severity.WARNING
    category = RuleCategory.CONSISTENCY
    description = "Every period date a progress claim records must be a readable date"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        if not claim:
            return []
        locale = _locale(context)
        results: list[RuleResult] = []
        for text_field, date_field, label_key in _PERIOD_FIELDS:
            raw = str(claim.get(text_field) or "").strip()
            if not raw or claim.get(date_field) is not None:
                continue
            results.append(
                self._result(
                    context,
                    passed=False,
                    element_ref=str(claim.get("id", "")),
                    fail_key="pay_application.period_unparsed.fail",
                    suggestion_key="pay_application.period_unparsed.suggestion",
                    claim=_claim_label(claim),
                    field=translate(label_key, locale=locale),
                    value=raw,
                )
            )
        if not results:
            results.append(self._result(context, passed=True, element_ref=str(claim.get("id", ""))))
        return results


class ClaimLineOverbilledRule(_ClaimRule):
    """No line may bill more to date than its scheduled value (G above C).

    G is work completed from previous applications, plus this period, plus
    materials presently stored, exactly as the continuation sheet adds it up.
    A credit line (negative scheduled value) is overbilled when its total
    runs past the credit in the negative direction.
    """

    rule_id = "pay_application.line_overbilled"
    name = "No line is billed beyond its scheduled value"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "Work and stored materials billed to date on a line must not exceed its scheduled value"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        lines = _rows(context, "lines")
        if not lines:
            return []
        currency = str(_data(context).get("currency") or "")
        results: list[RuleResult] = []
        for line in lines:
            scheduled = _money(line.get("scheduled_value"))
            billed = _money(line.get("total_completed_stored"))
            if scheduled >= 0:
                over = billed - scheduled > _MONEY_EPSILON
            else:
                over = scheduled - billed > _MONEY_EPSILON
            if not over:
                continue
            results.append(
                self._result(
                    context,
                    passed=False,
                    element_ref=str(line.get("contract_line_id", "")),
                    fail_key="pay_application.line_overbilled.fail",
                    suggestion_key="pay_application.line_overbilled.suggestion",
                    line=str(line.get("code") or line.get("description") or line.get("contract_line_id") or ""),
                    billed=sentence_amount(billed, currency),
                    scheduled=sentence_amount(scheduled, currency),
                )
            )
        if not results:
            results.append(self._result(context, passed=True, element_ref=str(claim.get("id", ""))))
        return results


class ClaimPercentRegressedRule(_ClaimRule):
    """A line's percent complete to date fell below what was already billed.

    A claim bills percent to date less what the earlier claims billed. When
    the percent comes in lower, the difference would be a credit; the
    generator bills nothing on the line instead and records it, because
    either the new figure is wrong or an earlier claim overstated the work,
    and only a person can say which.
    """

    rule_id = "pay_application.percent_regressed"
    name = "Percent complete does not go backwards"
    severity = Severity.WARNING
    category = RuleCategory.CONSISTENCY
    description = "A line's percent complete to date must not fall below what earlier claims already billed on it"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        claim = _section(context, "claim")
        if not claim:
            return []
        currency = str(_data(context).get("currency") or "")
        results: list[RuleResult] = []
        for entry in _rows(context, "percent_regressed"):
            results.append(
                self._result(
                    context,
                    passed=False,
                    element_ref=str(entry.get("contract_line_id", "")),
                    fail_key="pay_application.percent_regressed.fail",
                    suggestion_key="pay_application.percent_regressed.suggestion",
                    line=str(entry.get("code") or entry.get("contract_line_id") or ""),
                    percent=_percent(entry.get("observed_pct")),
                    requested=sentence_amount(_money(entry.get("requested_value")), currency),
                    previous=sentence_amount(_money(entry.get("previous_value")), currency),
                )
            )
        if not results:
            results.append(self._result(context, passed=True, element_ref=str(claim.get("id", ""))))
        return results


#: The contracts-owned half of the pay_application rule set, in the order a
#: reader meets the findings: the period first, then the lines.
PAY_APPLICATION_RULES: tuple[type[ValidationRule], ...] = (
    ClaimPeriodPresentRule,
    ClaimPeriodOrderRule,
    ClaimPeriodOverlapRule,
    ClaimPeriodGapRule,
    ClaimPeriodUnparsedRule,
    ClaimLineOverbilledRule,
    ClaimPercentRegressedRule,
)


def register_contracts_validation_rules() -> None:
    """Register the contracts rules with the platform rule registry."""
    rule_registry.register(ContractPartyRolesRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(ContractPerformanceBondRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(EOTDaysRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(ContractTemplatePinnedRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(ContractTemplateClausesRule(), [CONTRACTS_RULE_SET])
    for rule_class in PAY_APPLICATION_RULES:
        rule_registry.register(rule_class(), [PAY_APPLICATION_RULE_SET])
    logger.debug("contracts: registered 5 contract rules and %d payment application rules", len(PAY_APPLICATION_RULES))
