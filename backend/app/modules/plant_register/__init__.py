# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plant register: main components, long-lead items and their procurement route.

One project register of the plant the owner must specify, secure and hand
over. Per item: what it must do, how long it takes to get (lead time WITH the
date it was asked and from whom), when it must be ordered (latest order date,
back from the schedule's need date), whether factory capacity is held, who
buys and who installs it, the delivery limits to the user, and the spares and
maintenance concept that goes with it into operation.

This module IS the platform's long-lead list. Long-lead is derived, never
stored. The approved register is the content of the governance frame document
``m04_equipment_frame``; its readiness feeds the gate to execution.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.plant_register.catalogue import register_plant_kind
    from app.modules.plant_register.events import register_plant_subscribers
    from app.modules.plant_register.evidence import register_gate_evidence
    from app.modules.plant_register.permissions import register_plant_permissions
    from app.modules.plant_register.validators import register_plant_rules

    register_plant_kind()
    register_plant_permissions()
    register_plant_rules()
    register_plant_subscribers()
    register_gate_evidence()
