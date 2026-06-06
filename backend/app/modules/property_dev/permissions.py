"""‌⁠‍Property Development module permission definitions.

R6 (task #137) extends the original coarse set with fine-grained
permissions for the Lead / Reservation / SalesContract /
PaymentSchedule / Instalment / ContractParty pipeline. The original
permissions are kept verbatim so existing routes don't churn.
"""

from app.core.permissions import Role, permission_registry

PROPERTY_DEV_PERMISSIONS: dict[str, Role] = {
    # ── Foundation (v3018) ──────────────────────────────────────────
    "property_dev.read": Role.VIEWER,
    "property_dev.create": Role.EDITOR,
    "property_dev.update": Role.EDITOR,
    "property_dev.delete": Role.MANAGER,
    "property_dev.reserve_plot": Role.EDITOR,
    "property_dev.contract_buyer": Role.MANAGER,
    "property_dev.lock_selection": Role.MANAGER,
    "property_dev.handover": Role.MANAGER,
    "property_dev.fix_snag": Role.EDITOR,
    "property_dev.process_warranty": Role.EDITOR,
    # ── R6 (task #137) - Lead ───────────────────────────────────────
    "property_dev.lead.create": Role.EDITOR,
    "property_dev.lead.read": Role.VIEWER,
    "property_dev.lead.update": Role.EDITOR,
    "property_dev.lead.delete": Role.MANAGER,
    "property_dev.lead.assign": Role.MANAGER,
    "property_dev.lead.convert": Role.MANAGER,
    # ── R6 (task #137) - Reservation ────────────────────────────────
    "property_dev.reservation.create": Role.EDITOR,
    "property_dev.reservation.read": Role.VIEWER,
    "property_dev.reservation.update": Role.EDITOR,
    "property_dev.reservation.cancel": Role.MANAGER,
    "property_dev.reservation.expire": Role.MANAGER,
    # ── R6 (task #137) - Sales Contract (SPA) ───────────────────────
    "property_dev.spa.draft": Role.EDITOR,
    "property_dev.spa.send": Role.MANAGER,
    "property_dev.spa.sign": Role.MANAGER,
    "property_dev.spa.cancel": Role.MANAGER,
    # ── R6 (task #137) - Payment Schedule ───────────────────────────
    "property_dev.payment_schedule.activate": Role.MANAGER,
    "property_dev.payment_schedule.suspend": Role.MANAGER,
    # ── R6 (task #137) - Instalment ─────────────────────────────────
    "property_dev.instalment.mark_paid": Role.EDITOR,
    "property_dev.instalment.issue_demand": Role.EDITOR,
    "property_dev.instalment.waive": Role.MANAGER,
    # ── R6 (task #137) - Contract Party (multi-buyer junction) ──────
    "property_dev.contract_party.add": Role.EDITOR,
    "property_dev.contract_party.remove": Role.MANAGER,
    "property_dev.contract_party.update_ownership": Role.MANAGER,
    # ── Task #138: Broker / Commission / Escrow / PriceMatrix / Reports ──
    # Brokers + agreements: EDITOR can CRUD master records but only
    # MANAGER+ can verify KYC (legal/compliance step).
    "property_dev.broker.kyc_verify": Role.MANAGER,
    # Commissions: accrual creation is event-driven and bypasses the
    # endpoint gates; the lifecycle (approve + pay) is MANAGER+.
    "property_dev.commission.approve": Role.MANAGER,
    "property_dev.commission.pay": Role.MANAGER,
    # Escrow: balance/list = VIEWER+; reconciliation = MANAGER+ because
    # it touches bank-side ledger evidence.
    "property_dev.escrow.reconcile": Role.MANAGER,
    # PriceMatrix lifecycle changes (activate + bulk-recompute) flip the
    # listed price of every plot; restricted to MANAGER+.
    "property_dev.price_matrix.activate": Role.MANAGER,
    "property_dev.price_matrix.bulk_recompute": Role.MANAGER,
    # Regulator reports get sent to RERA / MAHARERA / Rosfinmonitoring;
    # generation gate stays MANAGER+ to avoid accidental quarterly
    # disclosure from EDITOR-level sales staff.
    "property_dev.regulator_report.generate": Role.MANAGER,
    # ── Bulk admin operations (sales-ops console) ──────────────────────────
    # All bulk endpoints are MANAGER+ because each touches potentially
    # hundreds of rows in a single transaction (status flips that release
    # plots from reservation, expiry extensions that block other buyers,
    # CSV imports that fan out into Lead rows, doc regen that overwrites
    # signed-PDF blobs, and buyer-merge that re-points FK references on
    # reservations / sales_contracts / payments). Atomicity is enforced
    # via SAVEPOINT (see procurement R7 PO → invoice pattern); RBAC
    # gating is the FIRST line of defense before the IDOR per-entity gate.
    "property_dev.bulk.plot_status_change": Role.MANAGER,
    "property_dev.bulk.reservation_extend": Role.MANAGER,
    "property_dev.bulk.document_regenerate": Role.MANAGER,
    "property_dev.bulk.lead_import": Role.MANAGER,
    "property_dev.bulk.buyer_merge": Role.MANAGER,
}


def register_property_dev_permissions() -> None:
    """‌⁠‍Register permissions for the property_dev module."""
    permission_registry.register_module_permissions(
        "property_dev",
        PROPERTY_DEV_PERMISSIONS,
    )
