# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project delivery model: delivery form decision, risk allocation and package plan.

The owner compares delivery forms (catalogue kind ``delivery_forms``) against
weighted criteria, allocates every risk category to a party with a rationale,
proposes a decision that the governance gate of the contracts area approves,
and plans the contract packages and owner-furnished items that procurement,
design management and equipment procurement read. The package plan is the one
place that says who designs, builds and supplies what.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.delivery_model.catalogue import register_kinds
    from app.modules.delivery_model.events import register_delivery_model_subscribers
    from app.modules.delivery_model.evidence import register_gate_evidence
    from app.modules.delivery_model.permissions import register_delivery_model_permissions
    from app.modules.delivery_model.validators import register_delivery_model_rules

    register_kinds()
    register_delivery_model_permissions()
    register_delivery_model_rules()
    register_delivery_model_subscribers()
    register_gate_evidence()
    # The plant register reads the package plan here; it is optional and may not be installed.
    from app.modules.delivery_model import plant_port

    plant_port.register()
