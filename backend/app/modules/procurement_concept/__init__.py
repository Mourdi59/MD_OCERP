# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Procurement concept: what is bought, in which packages, by which procedure, from whom, and when.

The package identity is module 3's ``ContractPackage``; this module adds the
procurement attributes 1:1 (``AwardPackage``), checks each procedure against
the dated, sourced thresholds of the pinned catalogue (kind
``procurement_procedures``), runs prequalification and market sounding to a
short list, plans award dates backwards from need dates and lead times, and
registers framework agreements a company calls off. The approved concept is
the content of governance frame document ``m08_procurement_frame``; execution
(bids, award) happens in ``bid_management`` or ``rfq_bidding`` and is read back.
"""


async def on_startup() -> None:
    """Register the catalogue kind, permissions, rules, subscribers and the gate evidence provider."""
    from app.modules.procurement_concept.catalogue import register_kind
    from app.modules.procurement_concept.events import register_procurement_concept_subscribers
    from app.modules.procurement_concept.evidence import register_gate_evidence
    from app.modules.procurement_concept.permissions import register_procurement_concept_permissions
    from app.modules.procurement_concept.validators import register_procurement_concept_rules

    register_kind()
    register_procurement_concept_permissions()
    register_procurement_concept_rules()
    register_procurement_concept_subscribers()
    register_gate_evidence()
