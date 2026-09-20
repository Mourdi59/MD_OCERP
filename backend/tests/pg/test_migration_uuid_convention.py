# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Migrations must not declare new native PostgreSQL UUID columns.

``Base.metadata.create_all`` is the source of truth for our schema, and it
emits ``character varying(36)`` for every identity column: measured across all
598 tables, 597 are ``varchar(36)``, one is ``varchar(64)``, and none are
``uuid``. That is because ``GUID`` in ``app.database`` is a ``TypeDecorator``
whose ``impl`` is ``String(36)`` with no ``load_dialect_impl``, so it renders
the same on every dialect.

A migration that declares ``postgresql.UUID`` therefore describes a column
shape that ``create_all`` never produces. Nothing breaks today, because the
canonical install runs ``create_all`` and stamps the head without walking the
chain, so those declarations are not executed. They are only reachable by
walking the chain from base, and that walk currently fails: a revision creates
a child with ``document_id uuid`` referencing a parent whose ``id`` is
``varchar(36)``, and PostgreSQL refuses the foreign key with
``DatatypeMismatch``.

The decision recorded here is that the divergence is frozen rather than
repaired. Reconciling it would mean rewriting the revisions that already
declare these columns, which is a multi-day project gated on questions nobody
has answered. This guard does the affordable half: it stops the gap growing.
The allowlist below is closed. A new entry is not the fix.

The revisions are read with ``ast`` rather than imported, for the same reasons
as ``test_alembic_single_head``: importing them drags in ``app.database`` and a
PostgreSQL URL, and an unrelated import error anywhere in the 300-plus files
would silently disable the check.

The rule is deliberately coarse: any reference to a native UUID type in a
revision is a violation, whether or not this file can prove it reaches a
column. That is not laziness, it is the lesson from building the precise
version first. No current offender writes the type inline, because the same
revision has to work on SQLite, so the type reaches the column through at
least one indirection::

    guid_type = sa.String(36) if is_sqlite else sa.dialects.postgresql.UUID(as_uuid=True)
    sa.Column("document_id", guid_type, nullable=False)

A detector matching ``sa.Column`` arguments literally sees a bare name and
passes. Resolving assignments fixes that case and still missed
``v3012_equipment``, which returns the type from a helper and receives it as a
function parameter::

    def _guid_type(is_sqlite): return sa.String(36) if is_sqlite else postgresql.UUID()
    def _base_columns(guid_type): return [sa.Column("id", guid_type, primary_key=True)]

Every indirection added to the detector is a new way to fall through it, and a
site the guard cannot resolve counts as clean - which is how a guard ends up
enforcing nothing. Matching the type reference itself has no such gap.

The one exemption is ``existing_type=``. A migration that repairs the
divergence has to name ``UUID`` to say what the column is being converted
*from*, and that is the direction we want, not a new violation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Revision files that already declare a native UUID column, frozen as of the
# decision to stop the divergence growing rather than repair it.
#
# THIS LIST IS CLOSED. If a test failure sent you here, do not add your file to
# it. Use the same type the models use - ``sa.String(36)``, or the ``GUID`` type
# from ``app.database`` - so the column matches what ``create_all`` builds.
#
# Derived by scanning with ``_uuid_columns`` below, not written by hand.
UUID_COLUMN_ALLOWLIST = frozenset(
    {
        "v2934_match_search_log.py",
        "v2938_documents_activity.py",
        "v2939_document_share_links.py",
        "v2941_markup_comments.py",
        "v2942_folder_permissions.py",
        "v2943_compliance_docs.py",
        "v3010_service.py",
        "v3011_subcontractors.py",
        "v3012_equipment.py",
        "v3013_portal.py",
        "v3014_resources.py",
        "v3015_contracts.py",
        "v3016_crm.py",
        "v3017_carbon.py",
        "v3018_property_dev.py",
        "v3019_bid_management.py",
        "v3020_variations.py",
        "v3021_schedule_advanced.py",
        "v3022_hse_advanced.py",
        "v3023_daily_diary.py",
        "v3024_qms.py",
        "v3025_supplier_catalogs.py",
        "v3026_bi_dashboards.py",
        "v3029_qms_calibration_template_hse_extras.py",
        "v3030_module4_extras.py",
        "v3091_service_sla_recurring.py",
        "v3093_subs_prequal_insurance.py",
        "v3094_requirement_deliverables.py",
        "v3096_regional_indices_certainty.py",
        "v3104_propdev_broker_escrow_pricematrix_hierarchy.py",
        "v3106_geo_hub_init.py",
        "v3110_propdev_snag_buyer_cost_photos.py",
        "v3113_propdev_warranty_enrich.py",
        "v3120_accommodation_init.py",
        "v3125_propdev_pricing_engine.py",
        "v3126_propdev_portal_tokens.py",
        "v3200_resource_depth.py",
        "v3214_project_status_history.py",
        "v3217_contracts_depth.py",
        "v3218_carbon_element_link.py",
        "v3219_carbon_whole_life.py",
        "v3220_field_time_timesheets.py",
        "v3221_cost_explorer_reverse_index.py",
        "v3231_prefab_unit_cost_link.py",
        "v3235_design_options.py",
        "v40_ai_agents.py",
        "v40_assembly_templates.py",
        "v40_bim_federations.py",
        "v40_cpm_weekly.py",
        "v41_clash_ai_triage.py",
    }
)

# ``uuid`` is the standard library module; ``uuid.UUID`` is a Python value type
# used in data migrations and says nothing about a column's SQL type.
_STDLIB_UUID_ROOT = "uuid"
_UUID_TYPE_LEAVES = {"UUID", "Uuid"}

# ``existing_type=postgresql.UUID()`` describes the column a migration is
# converting away from. That is the repair direction, not a new violation.
_EXEMPT_KEYWORD = "existing_type"


def _dotted(node: ast.AST) -> str | None:
    """Render an attribute chain as ``a.b.c``, or None if it is not one."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _sqlalchemy_uuid_names(tree: ast.Module) -> set[str]:
    """Bare names that refer to a SQLAlchemy UUID type via a from-import.

    ``from sqlalchemy.dialects.postgresql import UUID`` makes plain ``UUID`` a
    column type, while ``import uuid`` makes plain ``uuid`` a module. Only the
    former is a divergence.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("sqlalchemy"):
            continue
        for alias in node.names:
            if alias.name in _UUID_TYPE_LEAVES:
                names.add(alias.asname or alias.name)
    return names


def _is_uuid_type_ref(node: ast.AST, imported: set[str]) -> bool:
    """Is this expression a reference to a native UUID column type?"""
    if isinstance(node, ast.Name):
        return node.id in imported
    dotted = _dotted(node)
    if dotted is None:
        return False
    parts = dotted.split(".")
    if parts[-1] not in _UUID_TYPE_LEAVES:
        return False
    # ``uuid.UUID`` is the stdlib class, not a column type.
    return parts[0] != _STDLIB_UUID_ROOT


def _exempt_nodes(tree: ast.Module) -> set[int]:
    """Node ids sitting under an ``existing_type=`` keyword, by identity."""
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == _EXEMPT_KEYWORD:
                exempt.update(id(child) for child in ast.walk(keyword.value))
    return exempt


def _uuid_columns(path: Path) -> list[str]:
    """Every native-UUID type reference in one revision, as ``line: source``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = _sqlalchemy_uuid_names(tree)
    exempt = _exempt_nodes(tree)

    hits: list[str] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if id(node) in exempt or not _is_uuid_type_ref(node, imported):
            continue
        # An attribute chain contains its own prefixes; report the outermost only.
        if id(node) in seen:
            continue
        seen.update(id(child) for child in ast.walk(node))
        hits.append(f"line {node.lineno}: {ast.unparse(node)[:90]}")
    return hits


def _scan() -> dict[str, list[str]]:
    """Map every offending revision filename to its UUID column declarations."""
    return {path.name: hits for path in sorted(VERSIONS.glob("*.py")) if (hits := _uuid_columns(path))}


@pytest.fixture(scope="module")
def offenders() -> dict[str, list[str]]:
    return _scan()


def test_the_versions_directory_was_actually_found() -> None:
    """A wrong path would make every assertion below vacuously true."""
    count = len(list(VERSIONS.glob("*.py")))
    assert count > 250, f"only {count} revisions found at {VERSIONS}"


def test_no_new_native_uuid_columns(offenders: dict[str, list[str]]) -> None:
    """The allowlist is closed: no revision outside it may declare a UUID column."""
    new = {name: hits for name, hits in offenders.items() if name not in UUID_COLUMN_ALLOWLIST}
    detail = "\n".join(f"  {name}\n    " + "\n    ".join(hits) for name, hits in sorted(new.items()))
    assert not new, (
        "These revisions declare a native PostgreSQL UUID column:\n"
        f"{detail}\n\n"
        "create_all emits varchar(36) for every identity column and always will, so a "
        "uuid column here describes a shape our schema never has. Walking the chain "
        "from base already fails on exactly this, with DatatypeMismatch on the foreign "
        "key. THE ALLOWLIST IS CLOSED AND ADDING YOUR FILE TO IT IS NOT THE FIX. Use "
        "sa.String(36), or the GUID type from app.database, to match what create_all builds."
    )


def test_allowlist_has_no_stale_entries(offenders: dict[str, list[str]]) -> None:
    """An entry that no longer offends has to go, or the list quietly rots.

    A filename that was renamed or deleted, or a revision someone repaired,
    leaves a permission behind that protects nothing and hides that the frozen
    list has drifted from the tree.
    """
    stale = sorted(UUID_COLUMN_ALLOWLIST - set(offenders))
    assert not stale, (
        "Allowlisted revisions that no longer declare a native UUID column:\n  "
        + "\n  ".join(stale)
        + "\n\nRemove them from UUID_COLUMN_ALLOWLIST. The list may shrink, never grow."
    )
