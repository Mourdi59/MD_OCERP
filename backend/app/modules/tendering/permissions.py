"""‌⁠‍Tendering module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_tendering_permissions() -> None:
    """‌⁠‍Register permissions for the tendering module."""
    permission_registry.register_module_permissions(
        "tendering",
        {
            "tendering.create": Role.EDITOR,
            "tendering.read": Role.VIEWER,
            "tendering.update": Role.EDITOR,
            "tendering.delete": Role.MANAGER,
            # Awarding writes the winning bid's rates back into the BOQ and
            # closes the tender - a contractual decision, so it sits at the
            # MANAGER tier (above ordinary edit) like contracts.sign.
            "tendering.award": Role.MANAGER,
            "tendering.bid.create": Role.EDITOR,
            "tendering.bid.update": Role.EDITOR,
            "tendering.comparison.read": Role.VIEWER,
            # Addenda (mid-tender clarifications) and bid leveling.
            "tendering.addendum.read": Role.VIEWER,
            "tendering.addendum.create": Role.EDITOR,
            "tendering.addendum.publish": Role.EDITOR,
            "tendering.addendum.acknowledge": Role.EDITOR,
            "tendering.leveling.read": Role.VIEWER,
            "tendering.leveling.run": Role.EDITOR,
        },
    )
