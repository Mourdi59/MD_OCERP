"""‌⁠‍Finance module.

Provides invoicing, payments, budgets, and Earned Value Management (EVM)
workflows for construction projects.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register permissions and cross-module subscribers."""
    from app.modules.finance.connector_events import (
        register_connector_job_handler,
        register_connector_subscribers,
    )
    from app.modules.finance.connectors.registry import register_builtin_connectors
    from app.modules.finance.events import register_finance_subscribers
    from app.modules.finance.permissions import register_finance_permissions

    register_finance_permissions()
    register_finance_subscribers()
    # TOP-30 #4: ERP / accounting connectors.
    register_builtin_connectors()
    register_connector_subscribers()
    register_connector_job_handler()
