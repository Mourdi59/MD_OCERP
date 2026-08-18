"""What a budget line is expected to finish at, and how far that is from budget.

One function, in one place, because this rule was written three times and only
one of the three was ever corrected. The budget row said "measure the budget
against the outturn we expect, not against what has been spent so far"; the
dashboard total and the Excel export kept subtracting spend. So the same line
reported one number in the table and another in the header, and both of them
overstated the money still available.

The correction that matters most is the one all three shared. Committed money
was not counted anywhere. A line with 48.7 budgeted, 12.4 spent and 33.4 under
signed order reported 36.3 of headroom in green, when what is genuinely free is
15.3. That is not a rounding complaint: it is a cost report inviting somebody
to spend money that is already promised, on the very screen whose job is to
stop them.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["expected_outturn", "budget_variance"]


def expected_outturn(
    *,
    forecast_final: Decimal,
    committed: Decimal,
    actual: Decimal,
) -> Decimal:
    """The best evidence we have of what this line will finish at.

    In order of authority:

    A recorded forecast wins. That column exists so a cost engineer can say
    "33.4 is on order but 6 of it will be released, this finishes at 30", and a
    report that quietly recomputed over the top of a typed number would be a
    worse defect than the one this fixes, because the user would have no way to
    see it happening. A forecast below the commitment is a disagreement worth
    showing, not one to smooth away.

    Absent a forecast - and absent is a real state, not a bug, since the
    change-order and BOQ-generated writers insert zero - the commitment is the
    next best evidence, because money under a signed order is spoken for
    whether or not the invoice has landed. ``committed`` here is gross: nothing
    in the product decrements it as invoices arrive, so it is compared against
    spend rather than added to it. Adding them would double-count every
    invoiced order.

    Spend to date is the floor. It is the only evidence on a line that carries
    neither a forecast nor a commitment, and on a job half built it reports
    every line comfortably under budget, which is the reading this whole
    function exists to stop being the only one.
    """
    if forecast_final > 0:
        return forecast_final
    return committed if committed > actual else actual


def budget_variance(
    *,
    revised_budget: Decimal,
    forecast_final: Decimal,
    committed: Decimal,
    actual: Decimal,
) -> Decimal:
    """How much of the revised budget is still free. Negative means over.

    Positive is money nobody has claimed yet, which is the only reading under
    which the green colour on this column means what a reader takes it to mean.
    """
    return revised_budget - expected_outturn(
        forecast_final=forecast_final,
        committed=committed,
        actual=actual,
    )
