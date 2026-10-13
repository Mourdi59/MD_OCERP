# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``staffing_model``: organisations, roles, document kinds, retention rules, leave types.

Data, not code. Shipped JSON lives in ``catalogues/``; tenant drafts and
published versions live in the shared governance catalogue tables and go
through the one resolver (``project_governance.catalogue_store``). This module
adds the body model, its validator and the registration call.

The role list is shared by every shipped catalogue; the country files differ
only in document facts and retention rules, each with its source and review
status. A credential type named by a document kind must exist in the
credentials registry (``credentials.schemas.CREDENTIAL_TYPES``), so a
catalogue cannot ask for a document the expiry engine cannot hold.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.modules.project_governance.catalogue import ReviewStatus

STAFFING_MODEL_KIND = "staffing_model"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"
I18N_PREFIX = "staffing."

PHASES: tuple[str, ...] = ("development", "execution", "operation")
ORGANISATIONS: tuple[str, ...] = (
    "owner_project_lead",
    "owner_project_controls",
    "owner_site_supervision",
    "owner_development",
    "external_consultant",
    "operator",
    "contractor_key_staff",
)
RETENTION_TRIGGERS: tuple[str, ...] = ("end_of_assignment", "end_of_employment", "document_expiry")
RETENTION_ACTIONS: tuple[str, ...] = ("delete", "anonymise")
LEAVE_TYPES: tuple[str, ...] = ("annual", "public_holiday", "rotation_off", "sick", "training", "unpaid", "other")
# The two document kinds rule 8 adds from the personnel file rather than from the role.
POSTING_KIND = "a1_posting_certificate"
WORK_PERMIT_KIND = "work_permit"
HEALTH_KIND = "occupational_health_certificate"


def platform_credential_types() -> tuple[str, ...]:
    """The one credential-type vocabulary (``credentials.schemas.CREDENTIAL_TYPES``)."""
    from app.modules.credentials.schemas import CREDENTIAL_TYPES

    return tuple(CREDENTIAL_TYPES)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    name_key: str = ""
    labels: dict[str, str] | None = None


class Organisation(_Labelled):
    code: str


class Role(_Labelled):
    code: str
    organisation: str
    phases: tuple[str, ...]
    default_fte: str = "1"
    key_role: bool = False
    # What the phase this key role is needed before must enable, e.g. ``construction_start``. A tag of the
    # governance phase catalogue, resolved to a gate when it is read; never a gate code.
    required_before: str | None = None
    required_document_kinds: tuple[str, ...] = ()
    handover_role: bool = False
    labor_rate_trade: str | None = None


class DocumentKind(_Labelled):
    code: str
    credential_type: str
    special_category: bool = False
    default_notify_days_before: int = 30
    store_number: bool = False
    retention_rule: str


class RetentionRule(_Labelled):
    code: str
    trigger: Literal["end_of_assignment", "end_of_employment", "document_expiry"]
    period_months: int
    # Floor counted from the assignment start ("3 years after hire or 1 year after termination, whichever later").
    min_months_from_start: int = 0
    action: Literal["delete", "anonymise"] = "delete"
    # A statutory duty to keep the record (SPEC rule 15): an erasure request is refused while it runs.
    legal_obligation: bool = False
    basis_text_key: str = ""
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    country: str = ""


class LeaveType(_Labelled):
    code: str


class StaffingModelCatalogue(_Labelled):
    """One catalogue body of kind ``staffing_model``."""

    id: str
    version: int = 1
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    source_url: str = ""
    source_title: str = ""
    jurisdiction_countries: tuple[str, ...] = ()
    organisations: tuple[Organisation, ...]
    roles: tuple[Role, ...]
    document_kinds: tuple[DocumentKind, ...]
    retention_rules: tuple[RetentionRule, ...]
    leave_types: tuple[LeaveType, ...]
    # Retention applied to a file whose documents name no rule (lead decision 9).
    default_retention_rule: str = "neutral_assignment_24m"

    def role(self, code: str | None) -> Role | None:
        return next((r for r in self.roles if r.code == code), None)

    def document_kind(self, code: str | None) -> DocumentKind | None:
        return next((d for d in self.document_kinds if d.code == code), None)

    def retention_rule(self, code: str | None) -> RetentionRule | None:
        return next((r for r in self.retention_rules if r.code == code), None)


def label_of(entry: Any, locale: str, fallback: str = "") -> str:
    """The display text of a catalogue entry: its own text for the locale, else its translated key.

    Tenant catalogues carry plain ``labels``; shipped ones carry an i18n ``name_key``.
    """
    from app.modules.staffing.messages import translate

    if entry is None:
        return fallback
    labels = getattr(entry, "labels", None) or {}
    text = labels.get(locale) or labels.get(locale.split("-")[0]) or labels.get("en")
    if text:
        return text
    key = getattr(entry, "name_key", "")
    return translate(key, locale=locale) if key else (next(iter(labels.values()), "") or fallback)


def _label_errors(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped":
        return [] if name_key.startswith(I18N_PREFIX) else [f"shipped_label_not_i18n_key: {where}"]
    if not name_key and not labels:
        return [f"label_missing: {where}"]
    return []


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: set[str] = set()
    for c in codes:
        if c in seen:
            out.add(c)
        seen.add(c)
    return sorted(out)


def _fte_valid(value: str) -> bool:
    try:
        fte = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return fte.is_finite() and Decimal("0") < fte <= Decimal("1")


def validate_staffing_model(obj: StaffingModelCatalogue, source: str) -> list[str]:
    """Cross-reference rules of a staffing model catalogue; an empty list means valid."""
    errors: list[str] = []
    errors += _label_errors("catalogue", obj.name_key, obj.labels, source)
    credential_types = set(platform_credential_types())
    orgs = [o.code for o in obj.organisations]
    roles = [r.code for r in obj.roles]
    kinds = [d.code for d in obj.document_kinds]
    rules = [r.code for r in obj.retention_rules]
    leaves = [lt.code for lt in obj.leave_types]
    for group, codes in (
        ("organisation", orgs),
        ("role", roles),
        ("document_kind", kinds),
        ("retention_rule", rules),
        ("leave_type", leaves),
    ):
        errors += [f"duplicate_{group}: {c}" for c in _dupes(codes)]
    errors += [f"organisation_unknown: {o}" for o in orgs if o not in ORGANISATIONS]
    errors += [f"leave_type_unknown: {lt}" for lt in leaves if lt not in LEAVE_TYPES]
    if obj.default_retention_rule not in rules:
        errors.append(f"default_retention_rule_unknown: {obj.default_retention_rule}")
    for o in obj.organisations:
        errors += _label_errors(f"organisation:{o.code}", o.name_key, o.labels, source)
    for lt in obj.leave_types:
        errors += _label_errors(f"leave_type:{lt.code}", lt.name_key, lt.labels, source)
    for r in obj.roles:
        errors += _label_errors(f"role:{r.code}", r.name_key, r.labels, source)
        if r.organisation not in orgs:
            errors.append(f"role_organisation_unknown: {r.code}:{r.organisation}")
        if not r.phases:
            errors.append(f"role_without_phase: {r.code}")
        errors += [f"role_phase_unknown: {r.code}:{p}" for p in r.phases if p not in PHASES]
        if not _fte_valid(r.default_fte):
            errors.append(f"role_fte_invalid: {r.code}")
        errors += [f"role_document_kind_unknown: {r.code}:{k}" for k in r.required_document_kinds if k not in kinds]
        if r.key_role and not r.required_before and "operation" not in r.phases:
            errors.append(f"key_role_without_gate: {r.code}")
    for d in obj.document_kinds:
        errors += _label_errors(f"document_kind:{d.code}", d.name_key, d.labels, source)
        if d.credential_type not in credential_types:
            errors.append(f"credential_type_unknown: {d.code}:{d.credential_type}")
        if d.retention_rule not in rules:
            errors.append(f"document_retention_rule_unknown: {d.code}:{d.retention_rule}")
        if d.default_notify_days_before < 0:
            errors.append(f"notify_days_invalid: {d.code}")
    for r in obj.retention_rules:
        errors += _label_errors(f"retention_rule:{r.code}", r.name_key, r.labels, source)
        if r.period_months < 0:
            errors.append(f"retention_period_invalid: {r.code}")
        if not r.source_url and r.review_status is not ReviewStatus.unconfirmed:
            errors.append(f"retention_without_source: {r.code}")
    return errors


def register_kinds() -> None:
    """Register the kind with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=STAFFING_MODEL_KIND,
            model=StaffingModelCatalogue,
            validator=validate_staffing_model,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=("organisations", "roles", "document_kinds", "retention_rules", "leave_types"),
        )
    )
