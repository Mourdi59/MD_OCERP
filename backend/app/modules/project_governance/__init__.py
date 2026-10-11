# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project governance: phases, gates and frame documents.

A project runs through a phase model with gates. Management areas each have an
owner and, per gate, required frame documents and a readiness check. A gate
decision is taken by a person the gate's approval route entitles, freezes what
it approved, and may carry conditions. After the gate, the approved frame
documents become binding and change only through a change request.

The phase vocabulary is data (``catalogue.py`` and ``catalogues/*.json``),
mapped to the neutral spine in ``requirements.lifecycle``. ``Project.phase``
is a mirror this module alone writes when a gate passes.
"""


async def on_startup() -> None:
    """Register permissions, validation rules and approval-route subscribers."""
    from app.modules.project_governance.events import register_governance_subscribers
    from app.modules.project_governance.permissions import register_governance_permissions
    from app.modules.project_governance.validators import register_governance_rules

    register_governance_permissions()
    register_governance_rules()
    register_governance_subscribers()
