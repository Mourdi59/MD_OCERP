# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commitment and release matrix with delegation of authority.

The owner decides, item by item, when money may be bound and who may bind it.
An item is a planned or existing commitment; its amounts are always derived
from the documents and budgets that own them. A delegation-of-authority
schedule (catalogue kind ``authority_schedule``) decides which tier of
approver a release needs; the release itself runs through ``approval_routes``.
Abort exposure (catalogue kind ``abort_basis`` plus per-item terms) says what
stopping now would still cost.
"""


async def on_startup() -> None:
    """Register catalogue kinds, permissions, rules, subscribers, the gate evidence provider, the guard and the sweeper."""
    from app.core.commitment_guard import register_change_threshold, register_commitment_guard
    from app.modules.commitment_release.catalogue import register_kinds
    from app.modules.commitment_release.events import register_commitment_subscribers
    from app.modules.commitment_release.evidence import register_gate_evidence
    from app.modules.commitment_release.guard import change_threshold, check_document, enforcement_of
    from app.modules.commitment_release.permissions import register_commitment_permissions
    from app.modules.commitment_release.validators import register_commitment_rules

    register_kinds()
    register_commitment_permissions()
    register_commitment_rules()
    register_commitment_subscribers()
    register_gate_evidence()
    register_commitment_guard(check_document, enforcement_of)
    register_change_threshold(change_threshold)

    from app.core.processes import process_registry
    from app.modules.commitment_release.sweep import register_commitment_sweeper

    register_commitment_sweeper(process_registry)
