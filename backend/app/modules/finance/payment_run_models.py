# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Payment run ORM models.

Tables:
    oe_finance_payment_run       - a batch of supplier invoices to pay together
    oe_finance_payment_run_item  - one invoice in a run and the amount to pay on it

A run belongs to one legal entity (or to none, on an installation that has not
set entities up) and one currency, because one bank file pays from one account
in one currency. It spans projects: accounting pays a supplier once for every
project that owes it. The run never moves money itself. Executing it records an
ordinary payment per item, the same row a person recording the payment by hand
would write, and the bank file is what accounting hands to the bank.
"""

import uuid
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_types import MoneyType
from app.database import GUID, Base

#: draft -> approved -> executed; draft or approved -> cancelled.
PAYMENT_RUN_STATUSES = ("draft", "approved", "executed", "cancelled")

#: Runs whose invoices are spoken for: an invoice sits in at most one of these.
ACTIVE_PAYMENT_RUN_STATUSES = ("draft", "approved")


class PaymentRun(Base):
    """A batch of payable invoices to pay on one date from one entity's account."""

    __tablename__ = "oe_finance_payment_run"
    __table_args__ = (
        UniqueConstraint("run_number", name="uq_finance_payment_run_number"),
        Index("ix_finance_payment_run_entity_status", "legal_entity_id", "status"),
    )

    run_number: Mapped[str] = mapped_column(String(32), nullable=False)
    # Plain GUID, no cross-module FK: legal entities is an optional module.
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(10), nullable=False)
    payment_date: Mapped[str] = mapped_column(String(10), nullable=False)
    # Invoices due on or before this date were proposed.
    due_by: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    executed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    items: Mapped[list["PaymentRunItem"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PaymentRunItem.created_at",
    )

    def __repr__(self) -> str:
        return f"<PaymentRun {self.run_number} {self.status} {self.currency_code} on {self.payment_date}>"


class PaymentRunItem(Base):
    """One invoice in a payment run and the amount to pay on it."""

    __tablename__ = "oe_finance_payment_run_item"
    __table_args__ = (
        UniqueConstraint("run_id", "invoice_id", name="uq_finance_payment_run_item_invoice"),
        Index("ix_finance_payment_run_item_invoice", "invoice_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_finance_payment_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_finance_invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    contact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    # What was open on the invoice when it was proposed, for the reader.
    open_at_proposal: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    # The payment that executing the run recorded; NULL until then.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    run: Mapped[PaymentRun] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<PaymentRunItem {self.invoice_id} {self.amount}>"
