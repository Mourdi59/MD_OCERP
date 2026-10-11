# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Authority permits: the permit roadmap and the consolidated permit-condition register.

Which authority approvals a project needs, who applies when and in what order,
by when each decision must arrive so the schedule holds, what the authority
decided, and every condition those decisions impose, with owner, trigger, due
date and the evidence that discharges it. National procedures and statutory
clocks are catalogue data (kind ``permit_type``); the code is country neutral.

Not to be confused with a site safety "permit to work" (``hse_advanced``) or a
governance gate condition (``project_governance``).
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, gate evidence and subscribers."""
    from app.modules.permits.catalogue import register_kind
    from app.modules.permits.events import register_permit_subscribers
    from app.modules.permits.evidence import register_gate_evidence
    from app.modules.permits.permissions import register_permit_permissions
    from app.modules.permits.validators import register_permit_rules

    register_kind()
    register_permit_permissions()
    register_permit_rules()
    register_gate_evidence()
    register_permit_subscribers()
