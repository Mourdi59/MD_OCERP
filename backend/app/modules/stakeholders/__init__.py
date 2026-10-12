# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Stakeholders, communication, project organisation and mandates.

Two questions every project answers before the development-to-execution gate:
who outside the core team matters, what they want, how we talk to them and
what we promised them; and who inside decides what. People and companies stay
in contacts, users and the team roster; letters, meetings, risks, approvals and
money authority stay in their own modules. This module adds the stakeholder
layer on top: register, append-only assessments, communication plan,
engagement events, commitments, project roles, governance bodies and the
mandate matrix. What is configurable is the catalogue kind
``stakeholder_framework`` in module 1's catalogue store.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers, the gate evidence provider and the daily sweep."""
    from app.modules.stakeholders.catalogue import register_kind
    from app.modules.stakeholders.events import register_stakeholder_subscribers
    from app.modules.stakeholders.evidence import register_gate_evidence
    from app.modules.stakeholders.jobs import register_sweep_process
    from app.modules.stakeholders.permissions import register_stakeholder_permissions
    from app.modules.stakeholders.validators import register_stakeholder_rules

    register_kind()
    register_stakeholder_permissions()
    register_stakeholder_rules()
    register_stakeholder_subscribers()
    register_gate_evidence()
    register_sweep_process()
