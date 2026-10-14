# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project economics: business case, cost frame and financing plan.

The owner states what the project costs (a cost frame by classification code of
the project's own standard), what it returns (a business case with key figures)
and where the money comes from (sources and tranches with a coverage check),
proposes the three together, and has the governance gate of the commercial area
approve them. The estimate and the commitments are read from the bill and the
cost spine, never typed in a second time.
"""


async def on_startup() -> None:
    """Register the host subject, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.economics.events import register_economics_subscribers
    from app.modules.economics.evidence import register_gate_evidence
    from app.modules.economics.permissions import register_economics_permissions
    from app.modules.economics.validators import register_economics_rules
    from app.modules.project_governance.public import register_host_subject

    register_host_subject("economics")
    register_economics_permissions()
    register_economics_rules()
    register_economics_subscribers()
    register_gate_evidence()
