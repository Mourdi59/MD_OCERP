"""Bordereau de prix module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_bordereau",
    version="0.1.0",
    display_name="Bordereau de prix",
    description="Shareable deduplicated price schedule — single source of truth for unit prices across BOQs",
    author="OpenEstimate Core Team",
    category="core",
    depends=["oe_boq"],
    auto_install=True,
    enabled=True,
)
