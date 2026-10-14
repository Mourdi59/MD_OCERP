# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""HSE frame: the environmental and safety frame of a project (framework module 11).

Per project: the requirements the owner puts on designers and contractors, the
environmental review, the site clearances (ordnance, contamination, ground
heritage), the permit conditions merged into one register as the brief for
execution, energy, climate and sustainability targets, safety and health
coordination with its appointed roles, the health and safety plan and the
security concept. Which duties apply (advance notice, coordinator, plan, file
for later works) follows from the project's facts and the pinned catalogue.

Incidents, permits to work, risk assessments, audits, corrective actions and
inspections stay in safety, hse_advanced, inspections and construction_control;
permit conditions stay in permits. This module links and reads them. Its
approved state is the governance frame document tagged for ``hse`` in the
project's phase model; national figures are catalogue data (kind ``hse_frame``).
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules and gate evidence."""
    from app.modules.hse_frame.catalogue import register_kind
    from app.modules.hse_frame.evidence import register_gate_evidence
    from app.modules.hse_frame.permissions import register_hse_frame_permissions
    from app.modules.hse_frame.validators import register_hse_frame_rules

    register_kind()
    register_hse_frame_permissions()
    register_hse_frame_rules()
    register_gate_evidence()
