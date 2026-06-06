"""‌⁠‍RFI module.

Request for Information management - questions from contractors to designers/consultants
with response tracking, cost/schedule impact assessment, and drawing links.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register permissions + approval-routes wiring."""
    from app.modules.rfi.approval_subscribers import register_rfi_approval_subscribers
    from app.modules.rfi.permissions import register_rfi_permissions

    register_rfi_permissions()
    # Feature 06: drive the RFI FSM off terminal approval-routes decisions
    # when a project has a routed sign-off configured.
    register_rfi_approval_subscribers()
