"""‌⁠‍Service & Maintenance module.

Service contracts, customer assets, service tickets, work orders, SLA tracking,
PPM (preventive maintenance) schedules, and debrief reports.

Opens OCE to MEP / facility-maintenance service companies - bridges field
engineers, dispatchers, accounting, and customers through one workflow.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register permissions."""
    from app.modules.service.permissions import register_service_permissions

    register_service_permissions()
