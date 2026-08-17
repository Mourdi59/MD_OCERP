# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Certified payroll module.

Public works in several jurisdictions oblige a contractor to submit a weekly
certified payroll: every worker, the trade classification they worked under, the
hours they worked each day, the rate paid split into basic wage and fringe
benefit, the deductions taken, and a signed statement that the rate paid meets
the wage determination that covers the work. A contractor who cannot produce one
does not get paid.

This module supplies the parts that were missing, and only those. The hours
already live in ``oe_field_time`` and flow into ``oe_payroll``; the pay
arithmetic already lives in ``oe_payroll``. What did not exist was the join from
a worker to a trade classification, the wage determination as a referenced
document, the split of a rate into basic and fringe, and the weekly form with
its statement of compliance.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and validation rules."""
    from app.modules.certified_payroll.permissions import register_certified_payroll_permissions
    from app.modules.certified_payroll.validators import register_certified_payroll_rules

    register_certified_payroll_permissions()
    register_certified_payroll_rules()
