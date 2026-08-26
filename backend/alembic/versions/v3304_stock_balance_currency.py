# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""supplier_catalogs: give stock cost a currency, and classify what is stored.

``StockBalance.unit_cost_avg`` is a weighted average rolled forward by the
goods-receipt path, and it carried no currency. Receiving the same item under
a EUR purchase order and then a USD one averaged the two prices into a number
that is money in neither, and because every issue, reservation and stocktake
copies the balance's average onto its own movement row, one blend spread from
the balance into the audit trail behind it.

This revision adds the missing label and, where the label cannot be supplied,
says so instead of leaving a number that looks computed.

What it adds
------------
``oe_supplier_catalogs_stock_balance``
    ``currency``    ISO code the average is denominated in, NULL unless the
                    balance is single-currency. Declared the same width as
                    ``oe_supplier_catalogs_po.currency``, the column it is
                    copied from, so no existing value can be too long to fit.
    ``cost_state``  "single", "mixed" or "unknown" - see below.
    ``unit_cost_avg`` becomes nullable, so "no single-currency average exists"
                    stops being spelled as the price zero.

``oe_supplier_catalogs_stock_movement``
    ``currency``    ISO code for this row's ``unit_cost``.
    ``unit_cost``   becomes nullable, for the same reason.

Both columns are added nullable and both widenings are NOT NULL to NULLABLE,
so nothing existing is rejected and no row has to be rewritten to fit.

What it classifies, and how it can
----------------------------------
The currency of historical stock is not lost, it is one join away and always
has been. Every inbound movement written by the receipt path records
``reference_type='gr'`` and ``reference_id=str(gr.id)``; every goods receipt
has a non-nullable ``po_id``; every purchase order has a currency. So each
balance is classified by resolving the currencies of its own inbound movements
and looking at the set:

    exactly one currency   ->  "single".  The stored average was correct all
                               along and is kept as it stands, now labelled.
    two or more            ->  "mixed".   The stored number is the blend.
                               It is set to NULL, because it is not a price.
    any unresolvable, or
    no inbound movements   ->  "unknown". Includes rows whose ``reference_id``
                               is NULL or names a receipt or order that is
                               gone, and demo stock seeded before this change.

``reference_id`` is a nullable ``String(36)`` with no foreign key, so the
unresolvable bucket is real rather than theoretical. Its size is printed
rather than assumed, so an operator is told how much of their inventory
valuation this revision could not vouch for instead of being told that all of
it is suspect. The summary separates two stories inside that bucket: a
movement that never carried a reference, and one whose goods receipt has since
been deleted. ``SupplierGoodsReceipt.po_id`` is ON DELETE CASCADE while
``reference_id`` has no foreign key, so deleting a purchase order takes its
receipts with it and orphans the movements silently.

The two matches worth spelling out. A movement stores ``batch_lot`` as NULL
where the balance stores ``""``, so the join normalises both to ``""``. And
only ``movement_type='in'`` rows are consulted, because those are the only
ones that ever set a price; every other type copies one down from the balance
and would otherwise let the balance corroborate itself.

That first match is guarded rather than trusted. A join that stops matching
does not raise: it returns nothing, every balance is classified unresolvable,
every average in the database is withdrawn, and the migration reports success.
So if any inbound movements exist at all and not one balance matched one, the
revision aborts inside its own transaction and changes nothing.

What is not needed here, having been considered and dropped: replaying the
receipts to recompute an average. The stored average is not a function of the
receipts alone - issue and stocktake rewrite ``quantity_on_hand``, which is the
weight the next receipt blends against - so a replay from inbound movements
would not reproduce it. None of that matters to this revision, because
classification reads only the *set* of currencies a balance received. A set has
no order and no weights, and neither branch of the outcome recomputes anything:
a single-currency average was already correct and is kept, and a mixed one is
withdrawn rather than recalculated.

Outbound movements of a single-currency balance
-----------------------------------------------
Issues, reservations and stocktake adjustments never priced themselves; each
copied the balance's average at the moment it was written. If every receipt
into a balance resolved to one currency, then every prefix of those receipts
did too, so the average at any past moment was a blend of that one currency and
the figure copied from it is denominated in it. That is a derivation, not an
estimate: no ordering, no FX rate, no replay. Those rows are labelled.

Without this, the day of the upgrade would split each history in two. A
warehouse that has only ever bought in EUR would show every movement before the
upgrade unlabelled and every movement after it EUR, from a revision whose
purpose is to put a currency on stock cost.

One case is excluded, and it is the premise of that derivation failing rather
than a matter of taste. The argument assumes the balance had already received
something. ``adjust_stocktake`` calls ``get_or_create_balance`` and can write an
adjustment against a balance with no receipts at all - a physical count finding
stock nobody booked in - and that row copied the creation default, which is
denominated in nothing. Such a row is identifiable without an order over the
movements, because the value it copied is exactly zero. So outbound rows with a
zero unit cost are left unlabelled and counted in the summary: a zero there is
either a genuine zero-priced copy or that default, and nothing available
distinguishes them. ``performed_at`` cannot arbitrate, being a nullable
``String(40)`` with no sequence behind it.

How it writes
-------------
Nothing is written until every decision is made. Both passes sort row ids into
buckets, where each bucket is exactly the set of rows that receive one
identical set of column values, and only then does the writing start: one
statement per distinct written value rather than one per row. Movements labelled
from a goods receipt and movements labelled from their balance both write the
same single column with the same kind of value, so they share the per-currency
buckets; balances split into one statement per currency for the single case and
one each for mixed and unknown.

The rule that makes that safe is worth stating, because grouping by the obvious
category breaks it: every grouped statement's WHERE clause must key on
something that uniquely determines every value that statement writes. Grouping
the single balances by ``cost_state`` would collapse rows that differ in the
currency being written and put one balance's currency onto another's.

Both tables are ``growth=tenure`` - see the acknowledgement lines above
``upgrade()`` - so the row count follows how long a deployment has been trading,
and the two costs that creates are separate things addressed separately.

Peak disk is the acknowledgement's job, not the batching's. Postgres keeps every
superseded row version until the transaction commits however the writes are
grouped, so a hundred thousand rows rewritten in three statements needs the same
headroom as a hundred thousand statements. Nothing here reduces that; the ack
exists so somebody asks the size question before this ships, which is what
#126 cost us by not being asked.

Round trips are the batching's job. One statement per row on a table with years
of movements behind it is that many round trips inside a single transaction,
holding its locks for the duration. Grouping makes the statement count a
function of how many distinct currencies a deployment trades in - a handful -
rather than of how long it has been trading.

What it leaves alone
--------------------
A "single" balance keeps its number untouched. Quantities are never read or
written here. And a mixed balance is not repaired by replaying its receipts
into a chosen currency: that would need an FX rate at each receipt date, which
is a decision about how this product values inventory and not something a
schema migration gets to make on an operator's behalf.

Historical movements keep their ``unit_cost`` even when their balance comes out
mixed or unknown. Withdrawing the number on the balance is right, because a
balance is a current valuation and a blend is not a price. A movement is a
record of what the system did at the time, and that figure may already have
been posted onward into project cost. Nulling it would be destroying an audit
row to make a classification tidy, and whether this product may do that is not
a schema migration's call.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3304_stock_balance_currency"
down_revision: Union[str, Sequence[str], None] = "v3303_work_calendar_iso_weekdays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BALANCE = "oe_supplier_catalogs_stock_balance"
_MOVEMENT = "oe_supplier_catalogs_stock_movement"
_GR = "oe_supplier_catalogs_gr"
_PO = "oe_supplier_catalogs_po"

# Kept in step with app/modules/supplier_catalogs/models.py. Repeated as
# literals rather than imported because a migration has to keep meaning what
# it meant on the day it ran, even after the module moves on.
# Cap on ids named in one IN list. Keeps statement count at one per distinct
# written value without handing a driver an unbounded parameter list.
_CHUNK = 1000

_SINGLE = "single"
_MIXED = "mixed"
_UNKNOWN = "unknown"


def _norm_currency(code: object) -> str | None:
    """Return an ISO code in upper case, or None when there is not one.

    The empty string is not a currency. Letting a blank count as a code would
    make two unlabelled orders agree with one another and classify the balance
    as a confident "single" denominated in nothing.
    """
    if code is None:
        return None
    cleaned = str(code).strip().upper()
    return cleaned or None


def _norm_key(value: object) -> str:
    """Normalise a GUID to text so a stored string can match a real id.

    ``reference_id`` holds ``str(gr.id)``, while the driver may hand back the
    receipt's own id as a UUID object or as text depending on dialect.
    """
    return str(value).strip().lower()


def _classify(currencies: list[str | None]) -> tuple[str, str | None]:
    """Decide a balance's cost state from its inbound movements' currencies.

    Returns ``(cost_state, currency)``. ``currency`` is set only for "single".

    Kept a plain function over a list so every case can be tested without a
    database, including the two that are easy to get wrong: an empty list is
    "unknown" rather than "single", and one unresolvable entry alongside a
    hundred good ones is still "unknown", because the average was computed
    over all of them.
    """
    if not currencies:
        return _UNKNOWN, None
    if any(code is None for code in currencies):
        return _UNKNOWN, None
    distinct = set(currencies)
    if len(distinct) == 1:
        return _SINGLE, distinct.pop()
    return _MIXED, None


def _chunks(ids: list) -> list[list]:
    """Split ``ids`` into runs small enough to name in one IN list.

    Deliberately returns chunks rather than running the UPDATE itself. A helper
    that took the SQL as a parameter would hide the table name behind a
    variable, and ``check_migration_data_rewrites.py`` resolves the table by
    reading the statement where it is executed - so the rewrite would stop
    being analysable by the gate that exists to find exactly this kind of
    statement. The SQL stays inline at each call site for that reason.
    """
    return [ids[index : index + _CHUNK] for index in range(0, len(ids), _CHUNK)]


# data-rewrite-ack: table=oe_supplier_catalogs_stock_movement growth=tenure rows=one row per receipt, issue, reservation and stocktake adjustment, appended forever and never deleted, so it tracks operating history exactly as the table in #126 did; the busiest table in this module on any mature install
# data-rewrite-ack: table=oe_supplier_catalogs_stock_balance growth=tenure rows=one row per warehouse, item and batch; bounded would be the comfortable answer and it is not the true one, because a batch-tracked item adds a row per lot received and lots are never merged or removed, so the count follows receipts rather than the catalogue
# boot-repair: gap - labels existing stock balances and movements with a currency derived per row; the heal adds the columns and leaves every existing row unlabelled
def upgrade() -> None:
    # The DDL is inspector-guarded, like the revisions around it, and the
    # classification below is not. That split is the point. The default runtime
    # builds its schema with create_all and stamps afterwards, so on that
    # install these columns already exist and an unguarded add_column raises
    # DuplicateColumn, which aborted the upgrade here and left every revision
    # after it unapplied. But existing columns say nothing about whether the
    # classification ever ran: create_all makes the column, it does not fill
    # it, so an install that got here that way has three empty columns and
    # needs the pass below more than a fresh one does. Skipping the work
    # because the column exists is how a repair goes missing.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if _BALANCE not in tables or _MOVEMENT not in tables:
        return
    balance_columns = {column["name"] for column in inspector.get_columns(_BALANCE)}
    movement_columns = {column["name"] for column in inspector.get_columns(_MOVEMENT)}

    if "currency" not in balance_columns:
        op.add_column(_BALANCE, sa.Column("currency", sa.String(10), nullable=True))
    if "cost_state" not in balance_columns:
        op.add_column(
            _BALANCE,
            sa.Column("cost_state", sa.String(16), nullable=False, server_default=_UNKNOWN),
        )
    if "currency" not in movement_columns:
        op.add_column(_MOVEMENT, sa.Column("currency", sa.String(10), nullable=True))

    # NOT NULL to NULLABLE is the widening direction, so no existing row can
    # fail it, and re-issuing it against a column that is already nullable is a
    # no-op rather than an error, so this one needs no guard.
    with op.batch_alter_table(_BALANCE) as batch:
        batch.alter_column("unit_cost_avg", existing_type=sa.Numeric(18, 4), nullable=True)
    with op.batch_alter_table(_MOVEMENT) as batch:
        batch.alter_column("unit_cost", existing_type=sa.Numeric(18, 4), nullable=True)

    # gr.id -> the currency of the order it was received against.
    gr_currency: dict[str, str | None] = {}
    for gr_id, po_currency in conn.execute(
        sa.text(f"SELECT gr.id, po.currency FROM {_GR} AS gr LEFT JOIN {_PO} AS po ON gr.po_id = po.id")
    ):
        gr_currency[_norm_key(gr_id)] = _norm_currency(po_currency)

    # Nothing is written until every decision is made. Both passes below only
    # sort row ids into buckets, and each bucket is exactly the set of rows
    # that receive one identical set of column values - which is what lets the
    # writes at the end be one statement per distinct value rather than one
    # per row.
    movements_by_currency: dict[str, list[object]] = defaultdict(list)
    per_balance: dict[tuple[str, str, str], list[str | None]] = defaultdict(list)
    outbound: dict[tuple[str, str, str], list[object]] = defaultdict(list)
    orphaned = 0
    ambiguous_out = 0

    rows = conn.execute(
        sa.text(
            f"SELECT id, warehouse_id, catalog_item_id, batch_lot, movement_type, reference_type, reference_id, "
            f"unit_cost FROM {_MOVEMENT}"
        )
    ).fetchall()
    for mv_id, wh_id, item_id, batch_lot, mv_type, ref_type, ref_id, unit_cost in rows:
        currency: str | None = None
        if ref_type == "gr" and ref_id is not None:
            key_ref = _norm_key(ref_id)
            if key_ref not in gr_currency:
                # The movement names a receipt that is no longer there.
                # ``SupplierGoodsReceipt.po_id`` is ON DELETE CASCADE and
                # ``reference_id`` has no foreign key, so deleting a purchase
                # order takes its receipts and silently orphans these rows.
                # That is a different story from "never recorded" and the
                # operator is told the two apart below.
                orphaned += 1
            currency = gr_currency.get(key_ref)

        key = (_norm_key(wh_id), _norm_key(item_id), batch_lot or "")
        if mv_type == "in":
            per_balance[key].append(currency)
            if currency is not None:
                movements_by_currency[currency].append(mv_id)
        elif unit_cost:
            # An outbound row copied the balance's average at the time it was
            # written. If every receipt into that balance is one currency,
            # every prefix of them is too, so this figure is denominated in
            # that currency - no ordering and no rate needed. Held back until
            # the balance below is classified.
            outbound[key].append(mv_id)
        else:
            # A zero has two readings that cannot be told apart without a
            # reliable order over the movements, and there is not one:
            # ``performed_at`` is a nullable String(40) with nothing enforcing
            # it. It is either a genuine zero-priced copy, or the creation
            # default from ``get_or_create_balance`` copied by a stocktake
            # that ran before the balance had received anything - a physical
            # count finding stock nobody booked in. The first is denominated
            # in the balance's currency and the second in nothing, so this row
            # is left unlabelled and counted instead.
            ambiguous_out += 1

    labelled_from_po = sum(len(ids) for ids in movements_by_currency.values())

    counts = {_SINGLE: 0, _MIXED: 0, _UNKNOWN: 0}
    matched = 0
    single_by_currency: dict[str, list[object]] = defaultdict(list)
    withdrawn: dict[str, list[object]] = {_MIXED: [], _UNKNOWN: []}
    for bal_id, wh_id, item_id, batch_lot in conn.execute(
        sa.text(f"SELECT id, warehouse_id, catalog_item_id, batch_lot FROM {_BALANCE}")
    ).fetchall():
        key = (_norm_key(wh_id), _norm_key(item_id), batch_lot or "")
        received = per_balance.get(key, [])
        if received:
            matched += 1
        state, currency = _classify(received)
        counts[state] += 1
        if state == _SINGLE and currency is not None:
            single_by_currency[currency].append(bal_id)
            # The issues, reservations and adjustments this balance already
            # wrote took their unit_cost from an average that was only ever a
            # blend of this one currency, so they carry it too. Both kinds of
            # labelled movement write the same single column with the same
            # value, so they share the per-currency buckets.
            movements_by_currency[currency].extend(outbound.get(key, ()))
        else:
            withdrawn[state].append(bal_id)

    # The join between movements and balances is on three parts, and one of
    # them disagrees about how "no batch" is spelled: the receipt path writes
    # ``""`` to the balance and ``None`` to the movement. Both sides are
    # coalesced above, but a join that stops matching does not raise. It
    # returns nothing, every balance is classified unresolvable, every average
    # in the estate is withdrawn, and the run reports success.
    #
    # So the coalescing is not trusted, it is checked: if any balance received
    # stock at all, at least one balance must have matched an inbound movement.
    # Failing here aborts inside the migration's own transaction and leaves the
    # database as it was, which is the outcome to want. It runs before the
    # writes below so the abort costs nothing.
    total = sum(counts.values())
    if per_balance and matched == 0:
        raise RuntimeError(
            f"v3304 aborted: {len(per_balance)} inbound movement groups exist but none matched "
            f"any of {total} stock balances. The movement-to-balance join is broken, and "
            f"continuing would withdraw every average cost in the database."
        )

    # One statement per distinct written value, not one per row. Each WHERE
    # clause names exactly the rows that take the values in its own SET, so
    # the grouping cannot smear one balance's currency onto another's.
    labelled = 0
    for currency, ids in movements_by_currency.items():
        for chunk in _chunks(ids):
            conn.execute(
                sa.text(f"UPDATE {_MOVEMENT} SET currency = :c WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"c": currency, "ids": chunk},
            )
            labelled += len(chunk)
    for currency, ids in single_by_currency.items():
        for chunk in _chunks(ids):
            conn.execute(
                sa.text(f"UPDATE {_BALANCE} SET cost_state = :s, currency = :c WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"s": _SINGLE, "c": currency, "ids": chunk},
            )
    for state, ids in withdrawn.items():
        # The stored average blends currencies, or was rolled forward from
        # receipts we cannot trace. Either way it is not a price, so it is
        # withdrawn rather than left to be read as one.
        for chunk in _chunks(ids):
            conn.execute(
                sa.text(
                    f"UPDATE {_BALANCE} SET cost_state = :s, currency = NULL, unit_cost_avg = NULL WHERE id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"s": state, "ids": chunk},
            )

    print(
        f"v3304 stock cost currency: {total} balances classified - "
        f"{counts[_SINGLE]} single-currency (average kept), "
        f"{counts[_MIXED]} mixed (average withdrawn), "
        f"{counts[_UNKNOWN]} unknown (average withdrawn); "
        f"{matched} matched an inbound movement; "
        f"{labelled} of {len(rows)} movements labelled "
        f"({labelled_from_po} from their purchase order, "
        f"{labelled - labelled_from_po} from the balance they were drawn against); "
        f"movements naming a deleted goods receipt: {orphaned}; "
        f"outbound movements left unlabelled on a zero unit cost: {ambiguous_out}"
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Restoring NOT NULL needs the NULLs filled first. Zero is what this
    # column meant before the upgrade, including for rows that never had a
    # cost, so going back reinstates that conflation rather than inventing a
    # new one.
    conn.execute(sa.text(f"UPDATE {_BALANCE} SET unit_cost_avg = 0 WHERE unit_cost_avg IS NULL"))
    conn.execute(sa.text(f"UPDATE {_MOVEMENT} SET unit_cost = 0 WHERE unit_cost IS NULL"))

    with op.batch_alter_table(_MOVEMENT) as batch:
        batch.alter_column("unit_cost", existing_type=sa.Numeric(18, 4), nullable=False)
    with op.batch_alter_table(_BALANCE) as batch:
        batch.alter_column("unit_cost_avg", existing_type=sa.Numeric(18, 4), nullable=False)

    op.drop_column(_MOVEMENT, "currency")
    op.drop_column(_BALANCE, "cost_state")
    op.drop_column(_BALANCE, "currency")
