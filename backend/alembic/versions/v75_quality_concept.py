# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""quality concept - requirements, certification, proofs, stages, acceptance, preservation.

Thirteen new ``oe_qconcept_*`` tables plus seven nullable link columns on
existing tables (test result calibration, hold gate and NCR package, handover
regime and packages, commissioning system plant item and checklist stage).

MUST be RUN on an existing installation: ``create_all(checkfirst)`` skips a
table that already exists, so the added columns on existing tables only arrive
through this revision. Every step is inspector-guarded, so a database whose new
tables ``create_all`` already built reaches this revision and only adds what is
missing.

Revision ID: v75_quality_concept
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v75_quality_concept"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, type) added to existing tables; all nullable, no default.
_COLUMNS: list[tuple[str, str, sa.types.TypeEngine]] = [
    ("oe_cc_test_result", "calibration_id", sa.String(36)),
    ("oe_cc_hold_gate", "package_ref", sa.String(64)),
    ("oe_cc_handover_package", "regime_code", sa.String(40)),
    ("oe_cc_handover_package", "package_refs", sa.JSON()),
    ("oe_ncr_ncr", "package_ref", sa.String(64)),
    ("oe_commissioning_system", "plant_item_id", sa.String(36)),
    ("oe_commissioning_checklist", "stage_code", sa.String(40)),
]


def _new_tables() -> list[sa.Table]:
    # Parent before child, so foreign keys inside the module resolve in order.
    from app.modules.quality_concept import models

    names = [
        "QualityConcept",
        "QualityConceptRevision",
        "AppliedStandard",
        "CertificationTarget",
        "CreditTarget",
        "ProofRequirement",
        "EvidenceLink",
        "CommissioningStageDef",
        "StageProgress",
        "AcceptanceUnit",
        "AcceptanceEffect",
        "PreservationSurvey",
        "ExpertReportPlan",
    ]
    return [getattr(models, n).__table__ for n in names]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table in _new_tables():
        if table.name not in existing:
            table.create(bind, checkfirst=True)
    for table, column, type_ in _COLUMNS:
        if table not in existing:
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table, column, _type in reversed(_COLUMNS):
        if table in existing and column in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, column)
    for table in reversed(_new_tables()):
        if table.name in existing:
            table.drop(bind, checkfirst=True)
