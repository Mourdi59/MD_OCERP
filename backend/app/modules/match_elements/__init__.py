# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Match Elements module.

Maps elements from BIM/CAD/PDF/photo sources to CWICR cost positions
through interactive group-based matching with multiple matcher methods
(vector + lexical, with LLM rerank planned). The result lands in a
project's BOQ as positions with auto-loaded resource decomposition,
each resource quantity scaled by the group total quantity.

Phase A: BIM source only. DWG/PDF/photo adapters land in later phases
behind the same SourceAdapter interface.

The module loader auto-imports ``router``, ``models``, ``hooks``, ``events``,
``validators`` and ``pipeline_nodes``, but never ``permissions.py``. The only
thing that runs a module's permission registration is this file, through the
``on_startup`` hook the loader calls once the module has loaded.
"""


async def on_startup() -> None:
    """Register this module's permissions once the module is loaded."""
    from app.modules.match_elements.permissions import (
        register_match_elements_permissions,
    )

    register_match_elements_permissions()
