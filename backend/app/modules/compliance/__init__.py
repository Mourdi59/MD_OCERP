# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""‌⁠‍Compliance DSL module - user-authored validation rules.

Wraps :mod:`app.core.validation.dsl` with persistence + a REST surface
so projects can author their own validation rules as YAML/JSON snippets
and have them registered into the global rule registry alongside the
hand-coded built-ins.
"""

from app.modules.compliance.manifest import manifest


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register the rule-builder permissions."""
    from app.modules.compliance.permissions import (
        register_compliance_permissions,
    )

    register_compliance_permissions()


__all__ = ["manifest", "on_startup"]
