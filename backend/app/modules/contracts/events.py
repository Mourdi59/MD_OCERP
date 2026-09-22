# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts module domain events.

Most contract lifecycle events are published inline from the service via
``event_bus.publish_detached`` (signed / amended / claim.submitted / etc.).
This module centralises the event-name constants that the Gap I progress
bridge introduces so subscribers and tests reference one canonical string
instead of a magic literal.

Event reference
───────────────
``contracts.claim.populated``
    Emitted after a draft progress claim has its line breakdown
    rebuilt from the latest progress observations and committed
    (``commit_preview_to_claim``). Payload::

        {
            "claim_id": str,
            "contract_id": str,
            "claim_number": str,
            "line_count": int,        # number of claim lines written
            "gross": str,             # Decimal-as-string, claim currency
            "retention": str,
            "net_due": str,
            "currency": str,
            "actor": str | None,
        }

    Finance / dashboard subscribers use it to refresh a claim's billed-to-date
    once it has been auto-populated from the field, without re-querying the
    whole contract. The event is informational only: it does NOT post to the
    cost spine (the certified-claim → actual posting is owned by Gap B/E and
    fires on ``contracts.claim.certified``).
"""

from __future__ import annotations

#: Emitted when a claim's lines are (re)built from progress observations.
CLAIM_POPULATED = "contracts.claim.populated"

#: Emitted when an extension-of-time claim is submitted for review. Payload::
#:
#:     {
#:         "eot_id": str,
#:         "contract_id": str,
#:         "eot_number": str,
#:         "days_claimed": int,
#:         "actor": str | None,
#:     }
EOT_SUBMITTED = "contracts.eot.submitted"

#: Emitted when an extension-of-time claim is decided (granted /
#: partially_granted / rejected). Payload::
#:
#:     {
#:         "eot_id": str,
#:         "contract_id": str,
#:         "eot_number": str,
#:         "status": str,                  # the decision status
#:         "days_claimed": int,
#:         "days_granted": int,
#:         "revised_completion_date": str | None,
#:         "actor": str | None,
#:     }
#:
#: Scheduling / dashboards subscribe to refresh the contract completion date
#: when time is granted. Informational only; it posts nothing to the ledger.
EOT_DECIDED = "contracts.eot.decided"

__all__ = ["CLAIM_POPULATED", "EOT_DECIDED", "EOT_SUBMITTED"]

# ── Cross-module subscriber: VO rollup into contract value ──────────────

import logging

_logger = logging.getLogger(__name__)


async def _on_vo_contract_sum_updated(payload: dict) -> None:
    """Bump Contract.total_value when a VO completes with a cost impact.

    Subscribes to ``variations.contract_sum.updated`` which the variations
    module emits when a VO transitions to ``completed`` with a non-zero
    ``final_cost_impact`` and an ``affected_contract_id`` set.
    """
    from decimal import Decimal

    contract_id = payload.get("contract_id")
    delta_str = payload.get("delta_amount")
    if not contract_id or not delta_str:
        return

    try:
        delta = Decimal(str(delta_str))
    except Exception:
        _logger.warning("VO rollup: bad delta_amount %r for contract %s", delta_str, contract_id)
        return

    if delta == 0:
        return

    import uuid

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.modules.contracts.models import Contract

    try:
        cid = uuid.UUID(str(contract_id))
    except ValueError:
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Contract).where(Contract.id == cid))
        contract = result.scalar_one_or_none()
        if contract is None:
            _logger.warning("VO rollup: contract %s not found", contract_id)
            return

        old_value = contract.total_value or Decimal("0")
        contract.total_value = old_value + delta
        await session.commit()
        _logger.info(
            "VO rollup: contract %s total_value %s -> %s (delta %s)",
            contract_id,
            old_value,
            contract.total_value,
            delta,
        )


def register_contract_event_handlers() -> None:
    """Wire up cross-module event subscriptions for oe_contracts."""
    from app.core.events import event_bus

    event_bus.subscribe_once("variations.contract_sum.updated", _on_vo_contract_sum_updated)
