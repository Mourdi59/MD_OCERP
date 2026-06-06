"""‌⁠‍Carbon & Sustainability module.

Embodied + operational carbon (scope 1/2/3), EPD database, material matching,
targets, and sustainability reporting (GHG Protocol / GRI / ISSB).
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register permissions."""
    from app.modules.carbon.permissions import register_carbon_permissions

    register_carbon_permissions()
