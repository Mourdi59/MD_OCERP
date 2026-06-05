"""Company-type presets for the onboarding wizard and the Modules page.

Each preset is a *role-based starting point*: it declares which optional
modules a given kind of company sees by default.  The user picks a profile
during onboarding (or switches it later on ``/modules``) and the chosen module
set is written to ``module_preferences``, which the sidebar honours - so a
profile genuinely shapes what the app looks like, not just a counter.

Single source of truth
----------------------
The module identifiers here MUST match the frontend onboarding catalogue in
``frontend/src/features/onboarding/modules.ts`` (the ``ALL_MODULES`` keys) and
the ``moduleKey`` the sidebar gates on.  Keep the three in sync: a key that
exists here but nowhere in the sidebar simply has no visible effect; a sidebar
key missing here is never reachable from a profile.

Core modules are always on (platform infrastructure plus the handful of
surfaces every company needs).  Profiles only ever toggle the *functional*
modules, so a profile can never lock a user out of Projects, Settings, etc.
"""

from __future__ import annotations

from typing import Any

# ── Always-on modules ─────────────────────────────────────────────────────────
# Platform infrastructure + the few surfaces every company needs regardless of
# profile. These are never disabled by a profile switch, so the user can always
# reach Projects, Contacts, the dashboard and the admin/setup area.
_CORE_MODULES: list[str] = [
    "projects",
    "contacts",
    "dashboards",
    "project_intelligence",
    "notifications",
    "users",
    "teams",
    "uploads",
    "jobs",
    "search",
    "backup",
    "admin",
    "i18n_foundation",
    "collaboration_locks",
    "architecture_map",
    # Cost reference data is core to a cost-estimation platform: the cost
    # database, the resource catalogue and the assembly library back every
    # estimating workflow, so no company profile may hide them. (The sidebar
    # mirrors this by leaving /costs, /catalog and /assemblies out of its
    # profile-gated route map.)
    "costs",
    "catalog",
    "assemblies",
]

# ── Functional modules, grouped (mirror of modules.ts groups) ───────────────────
# costs / catalog / assemblies are intentionally NOT here: they are core
# (see _CORE_MODULES) so every profile keeps them on.
_ESTIMATION = ["boq", "validation", "cost_match", "match"]
_TAKEOFF = ["takeoff", "dwg_takeoff", "cad"]
_BIM = ["bim_hub", "bim_requirements", "match_elements", "opencde_api"]
_AI = ["ai", "erp_chat", "compliance_ai", "ai_agents"]
_PLANNING = ["schedule", "schedule_advanced", "tasks", "costmodel", "eac"]
_FINANCE = ["finance", "procurement", "tendering", "changeorders"]
_COMMERCIAL = [
    "bid_management",
    "contracts",
    "variations",
    "crm",
    "supplier_catalogs",
    "property_dev",
    "moc",
]
_OPERATIONS = ["service", "equipment", "resources", "daily_diary", "subcontractors", "portal"]
_COMMUNICATION = ["meetings", "rfi", "submittals", "transmittals", "correspondence"]
_DOCUMENTS = ["documents", "cde", "markups"]
_QUALITY = ["inspections", "ncr", "safety", "punchlist", "risk", "hse_advanced"]
_QMS = ["qms", "compliance", "compliance_docs", "requirements"]
_FIELD = ["fieldreports", "collaboration", "field_diary", "payroll"]
_ESG = ["carbon"]
_BI = ["bi_dashboards", "reporting", "project_controls"]
_ENTERPRISE = ["enterprise_workflows", "full_evm", "rfq_bidding", "integrations"]

# Region-specific packs are chosen on the onboarding region step / via partner
# packs, not by a company profile, so they are not part of any profile's set.
_REGIONAL = [
    "dach_pack",
    "uk_pack",
    "us_pack",
    "india_pack",
    "middle_east_pack",
    "latam_pack",
    "asia_pac_pack",
    "russia_pack",
]

# Every functional module, in display order (used by Full Enterprise).
_ALL_FUNCTIONAL: list[str] = [
    *_ESTIMATION,
    *_TAKEOFF,
    *_BIM,
    *_AI,
    *_PLANNING,
    *_FINANCE,
    *_COMMERCIAL,
    *_OPERATIONS,
    *_COMMUNICATION,
    *_DOCUMENTS,
    *_QUALITY,
    *_QMS,
    *_FIELD,
    *_ESG,
    *_BI,
    *_ENTERPRISE,
]

# The complete module registry the onboarding POST iterates over when it writes
# module_preferences. Mirrors the ALL_MODULES keys in modules.ts.
_ALL_MODULES: list[str] = [*_CORE_MODULES, *_ALL_FUNCTIONAL, *_REGIONAL]

# ── Preset definitions ────────────────────────────────────────────────────────


class CompanyPreset:
    """Immutable descriptor for a company-type onboarding preset."""

    __slots__ = ("key", "label", "description", "icon", "enabled_modules", "tags")

    def __init__(
        self,
        key: str,
        label: str,
        description: str,
        icon: str,
        enabled_modules: list[str],
        tags: list[str] | None = None,
    ) -> None:
        self.key = key
        self.label = label
        self.description = description
        self.icon = icon
        # De-duplicate while preserving order; a profile only lists functional
        # modules, core modules are merged in by ``modules_for`` at write time.
        seen: set[str] = set()
        self.enabled_modules = [m for m in enabled_modules if not (m in seen or seen.add(m))]
        self.tags = tags or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "tags": self.tags,
            "enabled_modules": self.enabled_modules,
            "module_count": len(self.enabled_modules),
        }


COMPANY_PRESETS: dict[str, CompanyPreset] = {
    "general_contractor": CompanyPreset(
        key="general_contractor",
        label="General Contractor",
        description="We build projects end to end - estimating, procurement, site management and handover.",
        icon="Building2",
        tags=["BOQ", "Site", "Safety", "Finance"],
        enabled_modules=[
            "boq",
            "costs",
            "assemblies",
            "catalog",
            "validation",
            "takeoff",
            "dwg_takeoff",
            "schedule",
            "tasks",
            "costmodel",
            "finance",
            "procurement",
            "changeorders",
            "contracts",
            "variations",
            "equipment",
            "resources",
            "daily_diary",
            "subcontractors",
            "payroll",
            "field_diary",
            "meetings",
            "rfi",
            "submittals",
            "transmittals",
            "documents",
            "cde",
            "markups",
            "inspections",
            "ncr",
            "safety",
            "punchlist",
            "risk",
            "qms",
            "moc",
            "fieldreports",
            "reporting",
            "project_controls",
        ],
    ),
    "estimator": CompanyPreset(
        key="estimator",
        label="Cost Estimator / Quantity Surveyor",
        description="We price work - quantity takeoff, cost databases, BoQ and tender pricing.",
        icon="Calculator",
        tags=["Takeoff", "Costs", "BOQ", "Tender"],
        enabled_modules=[
            "boq",
            "costs",
            "assemblies",
            "catalog",
            "validation",
            "cost_match",
            "match",
            "takeoff",
            "dwg_takeoff",
            "match_elements",
            "ai",
            "tendering",
            "supplier_catalogs",
            "documents",
            "reporting",
        ],
    ),
    "architecture_engineering": CompanyPreset(
        key="architecture_engineering",
        label="Architecture / Engineering Office",
        description="We design buildings - BIM models, drawings, the CDE and design coordination.",
        icon="Pencil",
        tags=["BIM", "CDE", "Drawings", "RFI"],
        enabled_modules=[
            "bim_hub",
            "bim_requirements",
            "match_elements",
            "opencde_api",
            "takeoff",
            "dwg_takeoff",
            "documents",
            "cde",
            "markups",
            "rfi",
            "submittals",
            "transmittals",
            "correspondence",
            "boq",
            "costs",
            "validation",
            "requirements",
            "compliance_docs",
            "carbon",
            "reporting",
        ],
    ),
    "construction_manager": CompanyPreset(
        key="construction_manager",
        label="Project / Construction Manager",
        description="We run the programme - schedule, cost control, communication and quality oversight.",
        icon="ClipboardList",
        tags=["Schedule", "RFI", "Cost control", "Quality"],
        enabled_modules=[
            "schedule",
            "schedule_advanced",
            "tasks",
            "costmodel",
            "eac",
            "meetings",
            "rfi",
            "submittals",
            "transmittals",
            "correspondence",
            "documents",
            "cde",
            "markups",
            "inspections",
            "ncr",
            "punchlist",
            "risk",
            "qms",
            "moc",
            "finance",
            "procurement",
            "changeorders",
            "contracts",
            "variations",
            "fieldreports",
            "daily_diary",
            "field_diary",
            "payroll",
            "boq",
            "costs",
            "requirements",
            "reporting",
            "bi_dashboards",
            "project_controls",
        ],
    ),
    "real_estate_developer": CompanyPreset(
        key="real_estate_developer",
        label="Real Estate Developer",
        description="We develop and sell property - plots and buyers, budgets, contracts and handover.",
        icon="Home",
        tags=["Property", "Sales", "Finance", "Contracts"],
        enabled_modules=[
            "property_dev",
            "crm",
            "supplier_catalogs",
            "contracts",
            "variations",
            "finance",
            "procurement",
            "changeorders",
            "tendering",
            "bid_management",
            "schedule",
            "tasks",
            "costmodel",
            "boq",
            "costs",
            "documents",
            "cde",
            "portal",
            "meetings",
            "requirements",
            "carbon",
            "reporting",
            "bi_dashboards",
        ],
    ),
    "subcontractor": CompanyPreset(
        key="subcontractor",
        label="Subcontractor / Trade Contractor",
        description="We deliver a trade package - our scope, quantities, schedule and site paperwork.",
        icon="HardHat",
        tags=["Takeoff", "Schedule", "Site", "Safety"],
        enabled_modules=[
            "boq",
            "costs",
            "catalog",
            "validation",
            "takeoff",
            "dwg_takeoff",
            "schedule",
            "tasks",
            "daily_diary",
            "field_diary",
            "payroll",
            "resources",
            "equipment",
            "fieldreports",
            "rfi",
            "submittals",
            "safety",
            "inspections",
            "punchlist",
            "changeorders",
            "variations",
            "documents",
            "markups",
        ],
    ),
    "owner_client": CompanyPreset(
        key="owner_client",
        label="Owner / Client",
        description="We commission and oversee projects - reporting, documents, approvals and compliance.",
        icon="Briefcase",
        tags=["Reporting", "Documents", "Approvals"],
        enabled_modules=[
            "reporting",
            "bi_dashboards",
            "project_controls",
            "documents",
            "cde",
            "meetings",
            "rfi",
            "correspondence",
            "validation",
            "inspections",
            "requirements",
            "compliance",
            "finance",
            "schedule",
            "boq",
            "costs",
            "risk",
        ],
    ),
    "bim_vdc": CompanyPreset(
        key="bim_vdc",
        label="BIM / VDC Coordinator",
        description="We coordinate models - federation, clash detection, model requirements and the CDE.",
        icon="Box",
        tags=["BIM", "Clash", "CDE", "Requirements"],
        enabled_modules=[
            "bim_hub",
            "bim_requirements",
            "match_elements",
            "opencde_api",
            "takeoff",
            "dwg_takeoff",
            "cad",
            "documents",
            "cde",
            "markups",
            "requirements",
            "validation",
            "collaboration",
            "boq",
            "costs",
            "reporting",
        ],
    ),
    "full_enterprise": CompanyPreset(
        key="full_enterprise",
        label="Full Enterprise",
        description="We need the whole platform - every module across the full construction lifecycle.",
        icon="Boxes",
        tags=[],
        enabled_modules=list(_ALL_FUNCTIONAL),
    ),
}


def get_preset(company_type: str) -> CompanyPreset | None:
    """Return a preset by key, or ``None`` if unknown."""
    return COMPANY_PRESETS.get(company_type)


def get_all_presets() -> list[dict[str, Any]]:
    """Return all presets as serialisable dicts (for the GET endpoint)."""
    return [p.to_dict() for p in COMPANY_PRESETS.values()]


def is_core_module(key: str) -> bool:
    """Whether a module key is always-on (never disabled by a profile)."""
    return key in _CORE_MODULES


def modules_for(enabled_modules: list[str]) -> dict[str, bool]:
    """Build the full ``module_preferences`` map for a chosen module set.

    Every known module key is given an explicit ``True``/``False`` so the
    sidebar can hide what the profile leaves out. Core modules are forced on,
    so a profile can never hide Projects, Settings, the admin area, etc.
    """
    chosen = set(enabled_modules)
    prefs: dict[str, bool] = {}
    for key in _ALL_MODULES:
        prefs[key] = True if key in _CORE_MODULES else key in chosen
    return prefs
