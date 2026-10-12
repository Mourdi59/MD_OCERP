# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design management: the owner's design manager steers design from concept to permit.

One project breakdown structure (``projects.ProjectWBS``), design roles and
approval points, a design schedule per phase of the pinned governance phase
model, drawing numbering as catalogue data (kind ``drawing_numbering``), the
drawing register on CDE containers, the distribution matrix that turns a
release into transmittals, internal reviews, expert reports and proofs (kind
``design_reports``) and the permit design package.

It owns no file, revision, transmittal, schedule date or approval engine.
"""


async def on_startup() -> None:
    """Register catalogue kinds, permissions, rules, subscribers, gate evidence and the CDE numbering hook."""
    from app.modules.design_management.catalogue import register_kinds
    from app.modules.design_management.events import register_design_subscribers, register_numbering_hook
    from app.modules.design_management.evidence import register_gate_evidence
    from app.modules.design_management.permissions import register_design_permissions
    from app.modules.design_management.validators import register_design_rules

    register_kinds()
    register_design_permissions()
    register_design_rules()
    register_design_subscribers()
    register_gate_evidence()
    register_numbering_hook()
