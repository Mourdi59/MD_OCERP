# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Staffing: the project staffing plan and the personnel file of each person on it.

The plan (development verb: define) lists positions by role and phase, from
the owner organisation through external consultants to the operator build-up
before commissioning, with knowledge handover between them. It is the content
of the governance frame document ``m05_personnel_frame`` and is approved
through the governance gate only.

The personnel file (execution verb: steer) is the privacy envelope of one
person on the project: which documents the roles need, whether each is valid
on the start day (validity lives in ``credentials``), accommodation (read from
``accommodation``), travel, leave and retention. The person is a
``teams.RosterMember``; this module never creates a second person table.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.staffing.catalogue import register_kinds
    from app.modules.staffing.events import register_staffing_subscribers
    from app.modules.staffing.evidence import register_gate_evidence
    from app.modules.staffing.permissions import register_staffing_permissions
    from app.modules.staffing.validators import register_staffing_rules

    register_kinds()
    register_staffing_permissions()
    register_staffing_rules()
    register_staffing_subscribers()
    register_gate_evidence()
