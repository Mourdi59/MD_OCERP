# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Engineering brief: requirements brief, technical concept, programme and framework schedule.

The brief (development verb: define) is the content of the governance frame document that hosts it. It
owns four things and no more: the approval lifecycle, the technical concept, the area and quantity
programme and the framework schedule. The requirements themselves live in ``requirements`` (one
requirement set per brief); the programme the framework schedule is published into lives in
``schedule``. Approval is the governance gate decision on the hosting area, or a hand approval on a
project that runs without gates.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.engineering_brief.catalogue import register_kinds
    from app.modules.engineering_brief.events import register_engineering_brief_subscribers
    from app.modules.engineering_brief.evidence import register_gate_evidence
    from app.modules.engineering_brief.permissions import register_engineering_brief_permissions
    from app.modules.engineering_brief.validators import register_engineering_brief_rules

    register_kinds()
    register_engineering_brief_permissions()
    register_engineering_brief_rules()
    register_engineering_brief_subscribers()
    register_gate_evidence()
