# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the delivery model (SPEC section 4), free of I/O.

The service feeds plain dicts in and turns findings into refusals or
validation results; the validation rule set and the gate evidence read the
same functions, so a rule has one implementation.

Findings carry a stable ``code`` (also the message key suffix), a severity
(``error`` blocks, ``warning`` informs) and a ``ref`` naming the row.

Every rule is written against form ATTRIBUTES, never form codes, so a tenant
catalogue that adds a form with the same attributes gets the same checks.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.delivery_model.catalogue import (
    SHARED_BASES,
    SHARED_PARTY,
    DeliveryForm,
    DeliveryFormsCatalogue,
    Party,
    RiskCategory,
    share_errors,
)

ERROR = "error"
WARNING = "warning"
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
# Sides (catalogue attribute ``Party.side``) that can carry the availability of an asset in operation.
_OPERATING_SIDES = frozenset({"operator", "contractor"})
_INACTIVE_PACKAGE = frozenset({"cancelled"})
_WORKS_KINDS = frozenset({"construction", "supply_and_install", "design_and_construction"})
_TRADE_KINDS = frozenset({"construction", "supply_and_install"})
_PRICED_KINDS = _WORKS_KINDS | {"project_agreement"}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    ref: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "ref": self.ref, "params": self.params}


def errors(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == ERROR]


# ── comparison and proposal (rule 1) ───────────────────────────────────────


def dec(value: Any) -> Decimal:
    """A decimal from a string or int; floats are refused (money and weights are exact)."""
    if isinstance(value, float):
        raise ValueError("floats are not accepted; send a decimal string")
    out = Decimal(str(value))
    if not out.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return out


def weighted_totals(
    weights: Mapping[str, Decimal], option_ids: Sequence[str], scores: Mapping[tuple[str, str], int]
) -> dict[str, Decimal | None]:
    """Weighted score per option on a 1..5 scale: ``sum(weight * score) / sum(weight)``.

    ``None`` for an option missing any score: a partial total would rank an
    unscored option above a scored one.
    """
    wsum = sum(weights.values(), Decimal("0"))
    out: dict[str, Decimal | None] = {}
    for oid in option_ids:
        acc = Decimal("0")
        complete = True
        for code, w in weights.items():
            score = scores.get((oid, code))
            if score is None:
                complete = False
                break
            acc += w * Decimal(score)
        out[oid] = (acc / wsum).quantize(CENT) if complete and wsum else None
    return out


def proposal_findings(
    option_ids: Sequence[str],
    weights: Mapping[str, Decimal],
    scores: Mapping[tuple[str, str], int],
    rationale: str,
    chosen_option_id: str | None,
) -> list[Finding]:
    """SPEC rule 1: two or more options, each scored on every criterion, weights = 100, a rationale."""
    out: list[Finding] = []
    if len(option_ids) < 2:
        out.append(Finding("single_option_decision", ERROR, "options", {"count": len(option_ids)}))
    total = sum(weights.values(), Decimal("0"))
    if not weights or total != HUNDRED:
        out.append(Finding("weights_not_100", ERROR, "criteria", {"total": str(total)}))
    for oid in option_ids:
        missing = sorted(c for c in weights if not 1 <= int(scores.get((oid, c)) or 0) <= 5)
        if missing:
            out.append(Finding("scores_incomplete", ERROR, oid, {"criteria": missing}))
    if not (rationale or "").strip():
        out.append(Finding("rationale_missing", ERROR, "decision"))
    if chosen_option_id is None or chosen_option_id not in option_ids:
        out.append(Finding("chosen_option_unknown", ERROR, "decision"))
    return out


# ── risk allocation (rules 3 to 6) ─────────────────────────────────────────


def allocation_findings(
    catalogue: DeliveryFormsCatalogue,
    form_code: str | None,
    allocations: Sequence[Mapping[str, Any]],
    *,
    form: DeliveryForm | None = None,
) -> list[Finding]:
    """Rules 3 (every category), 4 (shares), 5 (deviation rationale) and 6 (consistency with the form).

    ``form`` is the form as the project customised it (an option's overrides
    applied); without it the catalogue form of ``form_code`` is read.
    """
    out: list[Finding] = []
    form = form if form is not None else catalogue.form(form_code)
    by_cat = {a["category_code"]: a for a in allocations}
    parties = {p.code for p in catalogue.parties}
    for cat in catalogue.risk_categories:
        a = by_cat.get(cat.code)
        if a is None or (not a.get("party") and not a.get("not_applicable")):
            out.append(Finding("risk_unallocated", ERROR, cat.code))
            continue
        rationale = (a.get("rationale") or "").strip()
        if a.get("not_applicable"):
            if not rationale:
                out.append(Finding("not_applicable_needs_rationale", ERROR, cat.code))
            continue
        party = a["party"]
        if party not in parties:
            out.append(Finding("party_unknown", ERROR, cat.code, {"party": party}))
            continue
        for code in share_errors(party, a.get("shares"), parties):
            out.append(Finding("shared_risk_not_100" if code == "shares_not_100" else code, ERROR, cat.code))
        if party == SHARED_PARTY and a.get("basis") not in SHARED_BASES:
            out.append(Finding("shared_needs_basis", ERROR, cat.code))
        default = catalogue.default_for(form_code, cat.code)
        default_party = default.party if default is not None else None
        deviates = default is not None and (
            default.party != party
            or default.basis != a.get("basis")
            or (party == SHARED_PARTY and _shares(default.shares) != _shares(a.get("shares")))
        )
        if deviates and not rationale:
            out.append(Finding("deviation_needs_rationale", ERROR, cat.code, {"default": default_party}))
        hard = hard_inconsistency(form, cat, catalogue.party(party)) if form else None
        if hard:
            out.append(Finding("allocation_inconsistent_with_form", ERROR, cat.code, {"reason": hard}))
        elif deviates:
            out.append(Finding("allocation_deviates_from_default", WARNING, cat.code, {"default": default_party}))
    return out


def _shares(raw: Mapping[str, Any] | None) -> dict[str, Decimal]:
    return {k: Decimal(str(v)) for k, v in (raw or {}).items()}


def hard_inconsistency(form: DeliveryForm, category: RiskCategory, party: Party | None) -> str | None:
    """SPEC rule 6, the allocations a form cannot carry. Returns a reason code or ``None``.

    Reads what the category concerns and which side the party stands on, both
    catalogue attributes, so a catalogue that renames either keeps the rule.
    """
    side = party.side if party is not None else None
    if category.concerns == "design":
        if form.design_responsibility == "contractor" and side == "owner":
            return "contractor_designs"
        if form.design_responsibility == "owner" and side == "contractor":
            return "owner_designs"
    if category.concerns == "operation" and "operate" in form.scope_extends and side not in _OPERATING_SIDES:
        return "operator_carries_availability"
    return None


# ── packages (rules 7 and 8) ───────────────────────────────────────────────


def _active(packages: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [p for p in packages if p.get("status") not in _INACTIVE_PACKAGE]


def package_findings(
    form: DeliveryForm | None,
    packages: Sequence[Mapping[str, Any]],
    *,
    linked_contract_types: Mapping[str, str] | None = None,
) -> list[Finding]:
    """Rule 7 (package shape fits the form) and rule 8 (price basis, linked contract type)."""
    if form is None:
        return []
    out: list[Finding] = []
    live = _active(packages)
    by_id = {str(p["id"]): p for p in live}

    def bad(ref: str, reason: str) -> None:
        out.append(Finding("packages_inconsistent_with_form", ERROR, ref, {"reason": reason}))

    contractor_designs = form.design_responsibility in ("contractor", "split_at_stage")
    agreement = form.early_involvement == "multi_party" or bool(form.scope_extends)
    if form.design_responsibility == "owner":
        for p in live:
            if p.get("designs") and p.get("builds"):
                bad(p["code"], "owner_designs_no_design_and_build")
    if contractor_designs and form.contractor_role in ("builder",) and not agreement:
        db = [p for p in live if p.get("kind") == "design_and_construction"]
        if len(db) != 1:
            bad("packages", "one_design_and_construction_package")
    if form.contractor_role == "manager_at_risk":
        gmp = {str(p["id"]) for p in live if p.get("price_basis") == "gmp"}
        if not gmp:
            bad("packages", "gmp_package_missing")
        for p in live:
            if p.get("kind") in _TRADE_KINDS and str(p["id"]) not in gmp and str(p.get("parent_id") or "") not in gmp:
                bad(p["code"], "trade_package_under_gmp")
    if form.contractor_role == "manager_agency":
        holder = "owner" if form.owner_construction_contracts == "many" else "manager"
        for p in live:
            if p.get("kind") in _TRADE_KINDS and (p.get("contracting_party") or "owner") != holder:
                bad(p["code"], f"trade_contracts_held_by_{holder}")
    if agreement:
        n = sum(1 for p in live if p.get("kind") == "project_agreement")
        if n != 1:
            bad("packages", "one_project_agreement")
    for p in live:
        parent = p.get("parent_id")
        if parent and str(parent) not in by_id:
            bad(p["code"], "parent_missing")
        elif parent and parent_cycle(str(p["id"]), {k: v.get("parent_id") for k, v in by_id.items()}):
            bad(p["code"], "parent_cycle")
        basis = p.get("price_basis")
        # The form's price basis governs the works; consultants and managers are paid on their own terms.
        works = bool(p.get("builds")) or p.get("kind") in _PRICED_KINDS
        if works and basis and basis not in form.price_bases():
            out.append(Finding("price_basis_inconsistent_with_form", ERROR, p["code"], {"price_basis": basis}))
        ctype = (linked_contract_types or {}).get(str(p["id"]))
        if ctype and form.compatible_contract_types and ctype not in form.compatible_contract_types:
            # Lead decision 1: a contract type that contradicts the form warns; it is existing data.
            out.append(Finding("contract_type_inconsistent_with_form", WARNING, p["code"], {"contract_type": ctype}))
    return out


def parent_cycle(start: str, parents: Mapping[str, Any]) -> bool:
    """Does following ``parents`` (id -> parent id) from ``start`` come back to ``start``?"""
    seen: set[str] = set()
    current = parents.get(start)
    while current:
        current = str(current)
        if current == start:
            return True
        if current in seen:
            return False
        seen.add(current)
        current = parents.get(current)
    return False


# ── owner-furnished items (rules 10 and 11) ────────────────────────────────


def _day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def ofi_findings(
    items: Sequence[Mapping[str, Any]], packages: Sequence[Mapping[str, Any]], *, procurement_released: bool
) -> list[Finding]:
    """Rule 10 (route and installer before procurement is released) and rule 11 (late for the installer)."""
    out: list[Finding] = []
    pk = {str(p["id"]): p for p in _active(packages)}
    for i in items:
        if i.get("status") in ("delivered", "handed_to_installer"):
            continue
        no_route = (i.get("procurement_route") or "none_yet") == "none_yet"
        no_installer = i.get("install_by") == "package" and str(i.get("package_id") or "") not in pk
        if no_route or no_installer:
            out.append(
                Finding(
                    "ofi_without_route",
                    ERROR if procurement_released else WARNING,
                    i["code"],
                    {"route": not no_route, "installer": not no_installer},
                )
            )
        package = pk.get(str(i.get("package_id") or ""))
        arrives = _day(i.get("expected_delivery_date"))
        needed = _day(package.get("need_date")) if package else None
        if arrives and needed and arrives > needed:
            out.append(
                Finding(
                    "ofi_late_for_installer",
                    WARNING,
                    i["code"],
                    {"expected": arrives.isoformat(), "needed": needed.isoformat()},
                )
            )
    return out


# ── contract side (module 2) ───────────────────────────────────────────────

# Groups a project that has released procurement is expected to have settled; a missing one is a warning.
EXPECTED_CONTRACT_GROUPS = ("land_tenure", "utility_contract", "partner_structure")
_SIGNED_STATES = frozenset({"agreed", "signed"})
_LIVE_STATES = frozenset({"draft", "negotiating", "agreed", "signed"})


def contract_item_findings(
    items: Sequence[Mapping[str, Any]],
    kinds: Sequence[Mapping[str, Any]],
    form: DeliveryForm | None,
    *,
    procurement_released: bool,
) -> list[Finding]:
    """Rules of the contract-side items: kind and dates, counterparty once agreed, price basis, partner shares."""
    out: list[Finding] = []
    known = {(k["group"], k["code"]) for k in kinds}
    for i in items:
        ref = str(i["code"])
        if kinds and (i["group_code"], i["kind_code"]) not in known:
            out.append(Finding("contract_item_kind_unknown", ERROR, ref, {"kind": i["kind_code"]}))
        start, end = _day(i.get("start_date")), _day(i.get("end_date"))
        if start and end and end < start:
            out.append(Finding("contract_item_dates_invalid", ERROR, ref, {"start": str(start), "end": str(end)}))
        if i.get("status") in _SIGNED_STATES and not (i.get("counterparty") or "").strip():
            out.append(Finding("contract_item_without_counterparty", ERROR, ref, {"status": i["status"]}))
        basis = i.get("price_basis")
        if form is not None and i["group_code"] == "contract_form" and basis and basis not in form.price_bases():
            out.append(Finding("contract_form_price_basis_inconsistent", WARNING, ref, {"basis": basis}))
    partners = [i for i in items if i["group_code"] == "partner_structure" and i.get("status") in _LIVE_STATES]
    shares = [i for i in partners if i.get("share_percent")]
    if shares:
        total = sum((dec(i["share_percent"]) for i in shares), Decimal("0"))
        if total != HUNDRED:
            out.append(Finding("partner_shares_not_100", ERROR, "partner_structure", {"total": str(total)}))
    if procurement_released:
        present = {i["group_code"] for i in items if i.get("status") in _LIVE_STATES}
        out += [
            Finding("contract_group_missing", WARNING, group, {"group": group})
            for group in EXPECTED_CONTRACT_GROUPS
            if group not in present
        ]
    return out


__all__ = [
    "EXPECTED_CONTRACT_GROUPS",
    "ERROR",
    "WARNING",
    "Finding",
    "allocation_findings",
    "contract_item_findings",
    "dec",
    "errors",
    "hard_inconsistency",
    "ofi_findings",
    "package_findings",
    "parent_cycle",
    "proposal_findings",
    "weighted_totals",
]
