# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project handbook and data room.

The handbook is a set of chapters taken from a catalogue (kind ``handbook_model``; a pack ships the
chapter structure of its framework). A chapter has an owner, free text, a status, a version and an
approval. It does not copy what other modules already keep: the organisation chapter reads
stakeholders and staffing, the schedule chapter reads the engineering brief, at the moment it is shown or
printed. Approving a chapter freezes its text as an immutable version; with four eyes on, the approver
is never the person who submitted it.

The data room materialises the folders of the project's governance phase model into the folder tree of
the documents module, idempotently, and files documents into them by the area that hosts their subject.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules and the gate evidence provider."""
    from app.modules.project_handbook.catalogue import register_kinds
    from app.modules.project_handbook.evidence import register_gate_evidence
    from app.modules.project_handbook.permissions import register_project_handbook_permissions
    from app.modules.project_handbook.validators import register_project_handbook_rules

    register_kinds()
    register_project_handbook_permissions()
    register_project_handbook_rules()
    register_gate_evidence()
