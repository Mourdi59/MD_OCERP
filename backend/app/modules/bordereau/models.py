"""Bordereau de prix ORM models.

Tables:
    oe_bordereau_bordereau  — shareable price schedule (one per project scope)
    oe_bordereau_line       — deduplicated price line (single source of truth)
    oe_bordereau_component  — assembly decomposition within a bordereau line
"""

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base


class Bordereau(Base):
    """A shareable, deduplicated price schedule attached to one or more BOQs."""

    __tablename__ = "oe_bordereau_bordereau"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True,
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    lines: Mapped[list["BordereauLine"]] = relationship(
        back_populates="bordereau",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BordereauLine.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Bordereau {self.name} ({self.status})>"


class BordereauLine(Base):
    """A single deduplicated price entry — the canonical source for one unit price."""

    __tablename__ = "oe_bordereau_line"
    __table_args__ = (
        Index(
            "ix_bordereau_line_dedup",
            "bordereau_id",
            "designation_norm",
            "unit",
        ),
        Index(
            "ix_bordereau_line_bordereau_ref",
            "bordereau_id",
            "reference_code",
        ),
    )

    bordereau_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_bordereau_bordereau.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
    )
    designation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    designation_norm: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True,
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit_rate: Mapped[str] = mapped_column(
        String(50), nullable=False, default="0",
    )
    is_assembly: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    bordereau: Mapped[Bordereau] = relationship(back_populates="lines")
    components: Mapped[list["BordereauComponent"]] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BordereauComponent.sort_order",
    )

    def __repr__(self) -> str:
        return f"<BordereauLine {self.designation[:40]} ({self.unit})>"


class BordereauComponent(Base):
    """A resource/cost component within an assembly bordereau line."""

    __tablename__ = "oe_bordereau_component"

    line_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_bordereau_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cost_item_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_costs_item.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    resource_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    factor: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    quantity: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit_cost: Mapped[str] = mapped_column(String(50), nullable=False, default="0")
    total: Mapped[str] = mapped_column(String(50), nullable=False, default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    line: Mapped[BordereauLine] = relationship(back_populates="components")

    def __repr__(self) -> str:
        return f"<BordereauComponent {self.description[:40]} (factor={self.factor})>"
