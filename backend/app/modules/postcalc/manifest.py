# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Post-calculation module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_postcalc",
    version="1.0.0",
    display_name="Post-calculation",
    description=(
        "Reconciles the estimate against site actuals into planned-vs-actual "
        "labour productivity and material cost: a factor per BoQ line and per "
        "resource category, the material really consumed against what the "
        "estimate allowed, a project rollup, and a ranked list of productivity "
        "factors to feed back into estimating. Reads existing BoQ positions, "
        "field timesheets, progress readings and the site material ledger; a "
        "stateless analysis layer that adds no table."
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    # The estimate side (BoQ positions and their stored resource split) is
    # required. Field-time, progress and the site material ledger supply the
    # actuals; they are optional so the report still renders (estimate-only)
    # when any of them is absent or disabled, saying it does not know rather
    # than reporting a zero.
    depends=["oe_boq"],
    optional_depends=["oe_field_time", "oe_progress", "oe_site_inventory"],
    auto_install=True,
    enabled=True,
)
