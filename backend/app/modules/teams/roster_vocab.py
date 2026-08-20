# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The words a project roster is written in: trades and site roles.

Why closed catalogues
~~~~~~~~~~~~~~~~~~~~~
"Electrician", "Elektriker", "elec" and "E" are one trade to a site manager and
four to a database. A roster whose trade column is free text cannot answer "who
is on site for the electrical works this week", which is the whole reason to
record the trade. Both vocabularies are therefore closed, the write path
rejects anything outside them, and both carry an ``other`` member so a genuinely
unlisted case is recorded as unlisted rather than mistyped into a neighbour.

An empty string is always allowed and means "not stated". That is different from
``other``: nobody has said yet, versus somebody looked and none of these fit.

``label`` is the English source string. The frontend renders
``teams.trade.<key>`` / ``teams.siteRole.<key>`` and falls back to this label,
so API responses, logs and exports stay readable without a translation hop.

Trade keys deliberately match the vocabulary the subcontractor register already
seeds (``app/modules/subcontractors/seed.py``), so a roster line and a
subcontract can be read against each other without a mapping table.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RosterTrade:
    """One trade a person on the roster can work in."""

    key: str
    label: str


@dataclass(frozen=True)
class SiteRole:
    """One role a person can hold on the project.

    ``supervisory`` marks the roles that carry site authority. A project with
    nobody in one of them has a roster that cannot say who is in charge, which
    is what :class:`~app.modules.teams.validators.TeamsRosterSiteLead` reports.
    """

    key: str
    label: str
    supervisory: bool = False


ROSTER_TRADES: tuple[RosterTrade, ...] = (
    RosterTrade("earthworks", "Earthworks"),
    RosterTrade("demolition", "Demolition"),
    RosterTrade("concrete", "Concrete"),
    RosterTrade("steel_erection", "Steel erection"),
    RosterTrade("carpentry", "Carpentry"),
    RosterTrade("masonry", "Masonry"),
    RosterTrade("roofing", "Roofing"),
    RosterTrade("waterproofing", "Waterproofing"),
    RosterTrade("facade", "Facade"),
    RosterTrade("drywall", "Drywall"),
    RosterTrade("joinery", "Joinery"),
    RosterTrade("tiling", "Tiling"),
    RosterTrade("painting", "Painting"),
    RosterTrade("plumbing", "Plumbing"),
    RosterTrade("hvac", "HVAC"),
    RosterTrade("electrical", "Electrical"),
    RosterTrade("fire_protection", "Fire protection"),
    RosterTrade("elevators", "Elevators"),
    RosterTrade("scaffolding", "Scaffolding"),
    RosterTrade("asphalt", "Asphalt and paving"),
    RosterTrade("landscaping", "Landscaping"),
    RosterTrade("commissioning", "Commissioning"),
    RosterTrade("other", "Other trade"),
)

SITE_ROLES: tuple[SiteRole, ...] = (
    SiteRole("project_manager", "Project manager", supervisory=True),
    SiteRole("site_manager", "Site manager", supervisory=True),
    SiteRole("superintendent", "Superintendent", supervisory=True),
    SiteRole("foreman", "Foreman", supervisory=True),
    SiteRole("section_engineer", "Site engineer"),
    SiteRole("quantity_surveyor", "Quantity surveyor"),
    SiteRole("cost_engineer", "Cost engineer"),
    SiteRole("planner", "Planner"),
    SiteRole("procurement", "Procurement"),
    SiteRole("safety_officer", "Health and safety officer"),
    SiteRole("quality_manager", "Quality manager"),
    SiteRole("environmental_officer", "Environmental officer"),
    SiteRole("design_manager", "Design manager"),
    SiteRole("architect", "Architect"),
    SiteRole("structural_engineer", "Structural engineer"),
    SiteRole("mep_engineer", "MEP engineer"),
    SiteRole("bim_coordinator", "BIM coordinator"),
    SiteRole("surveyor", "Setting-out surveyor"),
    SiteRole("operative", "Operative"),
    SiteRole("client_representative", "Client representative"),
    SiteRole("contract_administrator", "Contract administrator"),
    SiteRole("other", "Other role"),
)

_TRADES_BY_KEY: dict[str, RosterTrade] = {t.key: t for t in ROSTER_TRADES}
_SITE_ROLES_BY_KEY: dict[str, SiteRole] = {r.key: r for r in SITE_ROLES}

ROSTER_TRADE_KEYS: frozenset[str] = frozenset(_TRADES_BY_KEY)
SITE_ROLE_KEYS: frozenset[str] = frozenset(_SITE_ROLES_BY_KEY)

#: Where a roster line's person came from.
#:
#: ``user``    - a platform user, so they can sign in and be assigned work.
#: ``contact`` - somebody in the address book: a subcontractor's foreman, a
#:               client representative, an inspector. No login.
#: ``manual``  - typed in, linked to nothing. The induction-list escape hatch.
ROSTER_SOURCES: tuple[str, ...] = ("user", "contact", "manual")


def is_known_trade(key: str) -> bool:
    """True when ``key`` names a trade this platform records (empty is allowed)."""
    return key == "" or key in _TRADES_BY_KEY


def is_known_site_role(key: str) -> bool:
    """True when ``key`` names a site role this platform records (empty is allowed)."""
    return key == "" or key in _SITE_ROLES_BY_KEY


def trade_label(key: str) -> str:
    """The English label for a trade key, or the key itself when unlisted."""
    trade = _TRADES_BY_KEY.get(key)
    return trade.label if trade else key


def site_role_label(key: str) -> str:
    """The English label for a site-role key, or the key itself when unlisted."""
    role = _SITE_ROLES_BY_KEY.get(key)
    return role.label if role else key


def supervisory_site_role_keys() -> frozenset[str]:
    """The site roles that carry authority on site."""
    return frozenset(r.key for r in SITE_ROLES if r.supervisory)
