"""‌⁠‍Integrations module - chat connectors (Teams, Slack, Telegram), webhooks, calendar feeds."""


async def on_startup() -> None:
    """‌⁠‍Module startup hook - register RBAC permissions.

    Invoked by :class:`app.core.module_loader` after the module's models,
    hooks and router are loaded. Registering here (rather than in
    ``main.py``) keeps the permission contract colocated with the module
    that enforces it, exactly like the sibling ``reporting`` /
    ``finance`` modules.
    """
    from app.modules.integrations.permissions import register_integrations_permissions

    register_integrations_permissions()
