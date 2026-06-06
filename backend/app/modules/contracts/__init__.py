"""‌⁠‍Contracts module - Contract Types Engine.

Multi-type contract engine supporting lump-sum, GMP, cost-plus, T&M,
unit-price, design-build, and combinations. Manages contract values,
schedule of values (SoV), progress claims, retention, gainshare,
liquidated damages, and final accounts.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register permissions."""
    from app.modules.contracts.permissions import register_contracts_permissions

    register_contracts_permissions()
