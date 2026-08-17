# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Serialisation to the standard federal weekly payroll form (WH-347).

This is a rendering of :mod:`app.modules.certified_payroll.models`, not a data
model of its own. Nothing is computed here that is not already on the week and
its lines: the form is the same rows in the layout the awarding body reads.

The form's columns, in the order it prints them:

    1. Name and individual identifying number of the worker
    2. Number of withholding exemptions (optional, and frequently left blank)
    3. Work classification
    4. Hours worked on each day of the week, split straight time and overtime
    5. Total hours
    6. Rate of pay, including the fringe benefit rate where paid in cash
    7. Gross amount earned
    8. Deductions, itemised, with a total
    9. Net wages paid for the week

Deduction buckets
=================

``oe_payroll`` groups withholdings into four coarse buckets for display:
``tax``, ``social``, ``pension`` and ``other``. The form asks for a social
security column, a withholding tax column, and a free "other" column that has to
be labelled. The mapping between the two happens here, at the export boundary,
and only here. Adding form-specific values to the shared payroll enum would push
one country's form into a vocabulary every other country's payroll also reads,
so the shared enum is left exactly as it is.

The statement of compliance
===========================

:func:`default_statement_of_compliance` renders the four assertions the weekly
statement makes: that everybody was paid their full weekly wages with no rebate
and no impermissible deduction, that the payroll is correct and complete and its
rates are not below the applicable determination, that apprentices are properly
registered, and the election between paying fringe benefits into approved plans
and paying them in cash.

It is a starting text, not the last word. The wording a contractor submits is
the contractor's responsibility and awarding bodies differ on what they accept,
so the text is stored on the week when it is certified rather than rendered
fresh on every read, and it can be replaced before signing. A statement somebody
signed must read back in three years exactly as they signed it, whatever this
file says by then.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any

from app.modules.certified_payroll.certpay_math import week_days

# How ``oe_payroll``'s coarse deduction buckets land in the form's columns. The
# form names a social security column and a withholding tax column and puts
# everything else under a labelled "other". Pension money is somebody's own
# arrangement rather than either statutory column, so it goes to "other" where
# its label carries the meaning.
DEDUCTION_COLUMN_BY_TYPE: dict[str, str] = {
    "social": "social_security",
    "tax": "withholding_tax",
    "pension": "other",
    "other": "other",
}

# The form's own deduction columns, in print order.
DEDUCTION_COLUMNS: tuple[str, ...] = ("social_security", "withholding_tax", "other")

FRINGE_ELECTION_STATEMENTS: dict[str, str] = {
    "plan": (
        "Fringe benefits are paid to approved plans, funds or programs. In addition to the basic hourly wage "
        "rates paid to each worker listed above, payments of fringe benefits as listed in the contract have "
        "been or will be made to appropriate programs for the benefit of such employees."
    ),
    "cash": (
        "Fringe benefits are paid in cash. Each worker listed above has been paid, as indicated on the "
        "payroll, an amount not less than the sum of the applicable basic hourly wage rate plus the amount "
        "of the required fringe benefits as listed in the contract."
    ),
    "mixed": (
        "Fringe benefits are paid partly to approved plans, funds or programs and partly in cash. For each "
        "worker listed above the total of the payments made to programs and the cash paid in lieu of them is "
        "not less than the required fringe benefit amount listed in the contract, and the exceptions are set "
        "out in the remarks."
    ),
}


def default_statement_of_compliance(
    *,
    signatory_name: str,
    signatory_title: str,
    contractor_name: str,
    project_name: str,
    week_start: str,
    week_ending: str,
    fringe_election: str,
    exception_note: str = "",
) -> str:
    """Render the four assertions of a weekly statement of compliance.

    Every substantive claim is filled from the week being certified rather than
    left as a blank for somebody to complete later, because a statement with a
    blank in it asserts nothing. The fringe election picks one of
    :data:`FRINGE_ELECTION_STATEMENTS`; an unknown election falls back to the
    plan wording and the caller is expected to have validated it first.

    Args:
        signatory_name: Who is certifying the payroll.
        signatory_title: Their position with the contractor.
        contractor_name: The employing contractor or subcontractor.
        project_name: The project the payroll covers.
        week_start: ISO date of the first day of the payroll week.
        week_ending: ISO date of the last day of the payroll week.
        fringe_election: ``plan``, ``cash`` or ``mixed``.
        exception_note: Any exception to the fringe election, in words.

    Returns:
        The statement as a single block of text, ready to store on the week.
    """
    election = FRINGE_ELECTION_STATEMENTS.get(
        str(fringe_election or "").strip().lower(),
        FRINGE_ELECTION_STATEMENTS["plan"],
    )
    who = signatory_name.strip() or "The undersigned"
    role = signatory_title.strip() or "an authorised officer"
    employer = contractor_name.strip() or "the employing contractor"
    project = project_name.strip() or "the project"

    paragraphs = [
        f"I, {who}, {role} of {employer}, do hereby state:",
        (
            f"(1) That I pay or supervise the payment of the persons employed by {employer} on {project}, and "
            f"that during the payroll period commencing on {week_start} and ending on {week_ending} all "
            "persons employed on the project have been paid the full weekly wages earned, that no rebates "
            "have been or will be made either directly or indirectly to or on behalf of the employer from "
            "the full weekly wages earned by any person, and that no deductions have been made either "
            "directly or indirectly from the full wages earned by any person other than permissible "
            "deductions."
        ),
        (
            "(2) That any payrolls otherwise required to be submitted for the above period are correct and "
            "complete, that the wage rates for laborers and mechanics contained therein are not less than "
            "the applicable rates contained in any wage determination incorporated into the contract, and "
            "that the classifications set forth for each laborer and mechanic conform with the work "
            "performed."
        ),
        (
            "(3) That any apprentices employed in the above period are duly registered in a bona fide "
            "apprenticeship program registered with a state apprenticeship agency recognised by the federal "
            "apprenticeship agency, or, where no such recognised agency exists, are registered with the "
            "federal apprenticeship agency."
        ),
        f"(4) {election}",
    ]
    remark = exception_note.strip()
    if remark:
        paragraphs.append(f"Remarks: {remark}")
    return "\n\n".join(paragraphs)


def _decimal(value: Any) -> Decimal:
    """Parse a stored Decimal-as-string figure, treating anything unusable as zero."""
    try:
        parsed = Decimal(str(value if value not in (None, "") else "0").strip())
    except (ArithmeticError, ValueError, TypeError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _plain(value: Decimal) -> str:
    """Render a Decimal without exponent notation."""
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def deduction_columns_for(deductions: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold a line's itemised deductions into the form's three columns.

    Returns the three column totals as strings, the labels that landed in the
    "other" column so the form can name them as it must, and the overall total.
    An empty or unusable list produces well-defined zeros rather than blanks,
    because a blank deduction column on a payroll form reads as "not stated"
    while zero reads as "nothing withheld", and those are different claims.
    """
    totals: dict[str, Decimal] = {column: Decimal("0") for column in DEDUCTION_COLUMNS}
    other_labels: list[str] = []
    for item in deductions or []:
        if not isinstance(item, dict):
            continue
        bucket = str(item.get("type") or item.get("deduction_type") or "other").strip().lower()
        column = DEDUCTION_COLUMN_BY_TYPE.get(bucket, "other")
        amount = _decimal(item.get("amount"))
        totals[column] += amount
        if column == "other":
            label = str(item.get("label") or "").strip()
            if label and label not in other_labels:
                other_labels.append(label)
    total = sum(totals.values(), Decimal("0"))
    rendered = {column: str(totals[column]) for column in DEDUCTION_COLUMNS}
    rendered["other_labels"] = other_labels
    rendered["total"] = str(total)
    return rendered


def render_form(week: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the full weekly form as a structured dict.

    Args:
        week: The certified (or draft) week header as a dict.
        lines: One dict per worker, in the shape the service derives or freezes.

    Returns:
        A dict with a ``header`` block, the ``days`` of the week in print order,
        a ``rows`` list matching the form's columns, a ``totals`` block, and the
        ``statement_of_compliance``. Everything is strings, so the payload can be
        handed to a renderer, a CSV writer or an API response unchanged.
    """
    ending = str(week.get("week_ending") or "")
    try:
        days = week_days(ending)
    except ValueError:
        days = []

    rows: list[dict[str, Any]] = []
    total_hours = Decimal("0")
    total_gross = Decimal("0")
    total_deducted = Decimal("0")
    total_net = Decimal("0")

    for line in lines:
        hours_by_day = line.get("hours_by_day") if isinstance(line.get("hours_by_day"), dict) else {}
        per_day = []
        for day in days:
            entry = hours_by_day.get(day) if isinstance(hours_by_day.get(day), dict) else {}
            per_day.append(
                {
                    "date": day,
                    "straight": str(entry.get("straight") or "0"),
                    "overtime": str(entry.get("overtime") or "0"),
                }
            )
        straight = _decimal(line.get("straight_hours"))
        overtime = _decimal(line.get("overtime_hours"))
        gross = _decimal(line.get("gross_amount"))
        net = _decimal(line.get("net_amount"))
        deductions = line.get("deductions_detail")
        columns = deduction_columns_for(deductions if isinstance(deductions, list) else [])

        total_hours += straight + overtime
        total_gross += gross
        total_net += net
        total_deducted += _decimal(columns["total"])

        rows.append(
            {
                "worker_name": str(line.get("worker_name") or ""),
                "worker_identifier": str(line.get("worker_identifier") or ""),
                "withholding_exemptions": str(line.get("withholding_exemptions") or ""),
                "classification": str(line.get("classification_title") or line.get("classification_code") or ""),
                "hours_by_day": per_day,
                "straight_hours": _plain(straight),
                "overtime_hours": _plain(overtime),
                "total_hours": _plain(straight + overtime),
                # The form's rate column shows the basic wage, and the cash
                # fringe beside it where fringe is paid in cash rather than into
                # a plan. Two figures, never one blended number.
                "basic_rate": str(line.get("paid_basic_rate") or "0"),
                "fringe_rate": str(line.get("paid_fringe_rate") or "0"),
                "fringe_election": str(line.get("fringe_election") or ""),
                "overtime_base_rate": str(line.get("overtime_base_rate") or "0"),
                "overtime_multiplier": str(line.get("overtime_multiplier") or ""),
                "gross_amount": str(gross),
                "deductions": columns,
                "net_amount": str(net),
                "currency": str(line.get("currency") or week.get("currency") or ""),
                # Carried so a reader can see which document fixed this rate
                # without leaving the form.
                "determination_identifier": str(line.get("determination_identifier") or ""),
                "determination_authority": str(line.get("determination_authority") or ""),
            }
        )

    return {
        "form": "WH-347",
        "header": {
            "contractor_name": str(week.get("contractor_name") or ""),
            "contractor_address": str(week.get("contractor_address") or ""),
            "is_subcontractor": bool(week.get("is_subcontractor")),
            "payroll_number": str(week.get("payroll_number") or ""),
            "is_final": bool(week.get("is_final")),
            "week_ending": ending,
            "week_start": days[0] if days else "",
            "project_name": str(week.get("project_name") or ""),
            "project_location": str(week.get("project_location") or ""),
            "contract_number": str(week.get("contract_number") or ""),
            "covered_authorities": week.get("covered_authorities") or [],
            "governing_reason": str(week.get("governing_reason") or ""),
            "currency": str(week.get("currency") or ""),
            "status": str(week.get("status") or ""),
        },
        "days": days,
        "rows": rows,
        "totals": {
            "workers": str(len(rows)),
            "total_hours": _plain(total_hours),
            "gross_amount": str(total_gross),
            "total_deductions": str(total_deducted),
            "net_amount": str(total_net),
        },
        "statement_of_compliance": {
            "text": str(week.get("statement_text") or ""),
            "signatory_name": str(week.get("signatory_name") or ""),
            "signatory_title": str(week.get("signatory_title") or ""),
            "signed_at": week.get("signed_at").isoformat() if hasattr(week.get("signed_at"), "isoformat") else "",
            "fringe_election": str(week.get("fringe_election") or ""),
            "fringe_exception_note": str(week.get("fringe_exception_note") or ""),
            "signed": bool(week.get("signed_at")),
        },
    }


def render_csv(form: dict[str, Any]) -> str:
    """Render a form payload as CSV, one row per worker.

    The per-day hours become two columns per day (straight and overtime) so the
    file is readable by a spreadsheet without anybody having to unpack a nested
    structure. Column headers carry the ISO date, so a reader never has to know
    which day the payroll week began on.
    """
    days: list[str] = list(form.get("days") or [])
    buffer = io.StringIO()
    header = [
        "worker_name",
        "worker_identifier",
        "classification",
        "determination_identifier",
        "determination_authority",
    ]
    for day in days:
        header.extend([f"{day}_straight", f"{day}_overtime"])
    header.extend(
        [
            "straight_hours",
            "overtime_hours",
            "total_hours",
            "basic_rate",
            "fringe_rate",
            "fringe_election",
            "overtime_base_rate",
            "gross_amount",
            "social_security",
            "withholding_tax",
            "other_deductions",
            "other_deduction_labels",
            "total_deductions",
            "net_amount",
            "currency",
        ]
    )
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)

    for row in form.get("rows") or []:
        by_date = {entry["date"]: entry for entry in row.get("hours_by_day") or []}
        out = [
            row.get("worker_name", ""),
            row.get("worker_identifier", ""),
            row.get("classification", ""),
            row.get("determination_identifier", ""),
            row.get("determination_authority", ""),
        ]
        for day in days:
            entry = by_date.get(day) or {}
            out.extend([entry.get("straight", "0"), entry.get("overtime", "0")])
        deductions = row.get("deductions") or {}
        out.extend(
            [
                row.get("straight_hours", "0"),
                row.get("overtime_hours", "0"),
                row.get("total_hours", "0"),
                row.get("basic_rate", "0"),
                row.get("fringe_rate", "0"),
                row.get("fringe_election", ""),
                row.get("overtime_base_rate", "0"),
                row.get("gross_amount", "0"),
                deductions.get("social_security", "0"),
                deductions.get("withholding_tax", "0"),
                deductions.get("other", "0"),
                "; ".join(deductions.get("other_labels") or []),
                deductions.get("total", "0"),
                row.get("net_amount", "0"),
                row.get("currency", ""),
            ]
        )
        writer.writerow(out)
    return buffer.getvalue()


__all__ = [
    "DEDUCTION_COLUMNS",
    "DEDUCTION_COLUMN_BY_TYPE",
    "FRINGE_ELECTION_STATEMENTS",
    "deduction_columns_for",
    "default_statement_of_compliance",
    "render_csv",
    "render_form",
]
