"""Which submission an award refers to.

Two subscribers of ``bid_management.package.awarded`` need the submission the
award was made against: ``procurement`` builds the purchase order lines from it
and ``notifications`` mirrors it into a contract's schedule of values. Until
this module existed each of them decided for itself which row that was, and
they did not agree.

A bidder can hold more than one submission in a package. ``BidSubmission``
constrains ``invitation_id`` to be unique but not ``bidder_id``, nothing in the
schema or in ``create_invitation`` forbids inviting the same company twice, and
``record_submission`` checks only that the bidder and the invitation belong to
the same package. A re-invitation for a revised round produces exactly this
shape through the ordinary API.

The order below is written out rather than left to the shape of a query so that
the next person to add a term puts it somewhere deliberate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bid_management.models import BidSubmission

#: The precedence, most significant first.
#:
#: 1. ``is_valid`` descending - a submission that passed validation at bid
#:    opening outranks one that did not. This preserves the rule procurement
#:    already applied and does not change what ``is_valid`` means for any
#:    existing row.
#: 2. ``created_at`` descending - among equally valid submissions the most
#:    recent one is the award's subject, which is the point of a revised round.
#: 3. ``id`` descending - not meaningful in itself, present so that the order
#:    is total. Two rows written in the same transaction can share a
#:    ``created_at``, and without a final term the winner would depend on
#:    whatever order the database happened to return.
AWARDED_SUBMISSION_PRECEDENCE = ("is_valid", "created_at", "id")


async def select_awarded_submission(
    session: AsyncSession,
    *,
    bidder_id: uuid.UUID,
) -> BidSubmission | None:
    """Return the submission an award against ``bidder_id`` refers to.

    ``None`` when the bidder has no submission at all, which is a legitimate
    state: a package can be awarded from outside the bidding flow.

    The query is scoped by bidder alone. ``Bidder.package_id`` is NOT NULL, so a
    bidder belongs to exactly one package and the bidder already carries the
    scope. Joining ``BidInvitation`` to filter on the package as well would be
    narrower rather than equivalent: it would drop any row whose invitation and
    bidder disagree about the package. ``record_submission`` refuses to create
    such a row, so the set should be empty, but excluding rows that predate that
    guard would silently change which submission an existing award resolves to,
    and that is not this function's decision to make.
    """
    stmt = (
        select(BidSubmission)
        .where(BidSubmission.bidder_id == bidder_id)
        .order_by(
            BidSubmission.is_valid.desc(),
            BidSubmission.created_at.desc(),
            BidSubmission.id.desc(),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()
