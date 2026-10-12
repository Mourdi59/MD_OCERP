# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Quality concept: the development-phase plan execution quality is measured against.

Per project: the standards basis and quality requirements, certification
targets, the proof concept (which tests, protocols and certificates each
designer and contractor delivers, per package and by when), commissioning as
staged levels from delivery limit to proof of operation, the acceptance plan
with the legal effects of each act in its regime, documentation and FM data
requirements, and evidence preservation. Evidence itself stays in its own
modules (construction_control, qms, commissioning, closeout, daily_diary,
requirements, defects_liability) and is linked; this module computes coverage.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers, gate evidence and the commissioning guard."""
    from app.core.commissioning_stage_guard import register_commissioning_stage_guard
    from app.modules.quality_concept.catalogue import register_kinds
    from app.modules.quality_concept.events import register_quality_concept_subscribers
    from app.modules.quality_concept.evidence import register_gate_evidence
    from app.modules.quality_concept.permissions import register_quality_concept_permissions
    from app.modules.quality_concept.service import commissioning_guard
    from app.modules.quality_concept.validators import register_quality_concept_rules

    register_kinds()
    register_quality_concept_permissions()
    register_quality_concept_rules()
    register_quality_concept_subscribers()
    register_gate_evidence()
    register_commissioning_stage_guard(commissioning_guard)
