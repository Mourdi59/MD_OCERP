"""First tests for the AIA payment application renderer.

This module renders a contract document that goes to an owner and an architect,
and until now it had no test of any kind anywhere in the tree. The defect these
cover is what that allowed to ship: a plain string table cell is drawn directly
rather than parsed as markup, so escaping its value puts the entity on the page.
A party named ``R&D Tower`` printed as ``R&amp;D Tower``, and because the
escaping ran with quote=True, ``O'Brien Construction`` printed as
``O&#x27;Brien Construction``. The apostrophe is the wide case: it needs no
unusual punctuation at all, only a name of a kind this document's market is
full of.

The last test here guards the other direction, because the two cell kinds in
this document want opposite treatment and the obvious repair to one of them
breaks the other.
"""

from __future__ import annotations

import io
from typing import Any

import pypdf
import pytest

import app.modules.contracts.aia_pdf as aia_pdf

# The probe and the suite must agree about which copy of the package they are
# reading. Running a file by path puts the script's own directory on sys.path
# rather than the working directory, which is how an earlier measurement of this
# module was taken against the installed copy under .venv-run instead of the
# tree. pytest resolves the tree, but saying so out loud costs nothing.
assert "site-packages" not in aia_pdf.__file__, aia_pdf.__file__

AMPERSAND_PARTY = "R&D Tower <Ltda>"


def application(**overrides: Any) -> dict[str, Any]:
    """A payment application with every field the renderer reads."""
    app: dict[str, Any] = {
        "application_number": "APP-014",
        "claim_date": "2026-04-15",
        "period_end": "2026-04-30",
        "currency": "USD",
        "certification": {
            "architect_certified_by": "Ortega Architects",
            "architect_certified_at": "2026-05-01",
            "owner_certified_by": "Harbour Estates",
            "owner_certified_at": "2026-05-02",
            "certified_amount": "1000.00",
        },
        "summary": {
            "contract_sum_to_date": "1000.00",
            "total_completed_stored": "1000.00",
            "balance_to_finish": "0.00",
            "retainage": "0.00",
        },
        "lines": [
            {
                "item_number": "01",
                "description": "Substructure",
                "scheduled_value": "1000.00",
                "previous_value": "0.00",
                "this_period_value": "1000.00",
                "materials_stored": "0.00",
                "total_completed_stored": "1000.00",
                "percent_complete": "100",
                "balance_to_finish": "0.00",
                "retainage": "0.00",
            }
        ],
    }
    app.update(overrides)
    return app


def drawn_runs(data: bytes) -> list[str]:
    """Every non-empty text run the page actually draws."""
    runs: list[str] = []
    for page in pypdf.PdfReader(io.BytesIO(data)).pages:
        page.extract_text(visitor_text=lambda text, cm, tm, font, size: runs.append(text))
    return [run.strip() for run in runs if run.strip()]


@pytest.mark.parametrize(
    "value",
    [
        "R&D Tower <Ltda>",
        # The apostrophe is the case that decides how wide this defect was. The
        # old escaping ran with quote=True, so it also rewrote apostrophes and
        # double quotes, and a name shaped like this one is ordinary in the
        # market that uses AIA documents.
        "O'Brien Construction",
        'Smith "Bud" Contracting',
    ],
)
def test_a_string_cell_is_printed_rather_than_escaped(value: str) -> None:
    """The application number is a plain string cell, so it is never parsed."""
    runs = drawn_runs(aia_pdf.render_aia_application_pdf(application(application_number=value)))
    assert value in runs, f"the application number was not drawn as written: {runs[:12]}"
    assert not any(ENTITY in run for run in runs for ENTITY in ("&amp;", "&lt;", "&#x27;", "&quot;")), (
        f"an HTML entity reached the page: {runs[:12]}"
    )


def test_a_certifier_name_is_printed_rather_than_escaped() -> None:
    """The second population, and the reason the count on the page was two.

    Certifier names are string cells in a different table, so a fix applied to
    one table would leave this one printing entities.
    """
    cert = application()["certification"] | {"owner_certified_by": AMPERSAND_PARTY}
    runs = drawn_runs(aia_pdf.render_aia_application_pdf(application(certification=cert)))
    assert AMPERSAND_PARTY in runs, f"the certifier name was not drawn as written: {runs[:12]}"


def test_a_paragraph_cell_still_escapes_what_it_is_given() -> None:
    """The property this document already had, which the fix must not spend.

    Line descriptions are Paragraph cells, and a Paragraph is parsed. Removing
    the escaping there as well, which is the obvious way to make the tests above
    pass everywhere, would let a description carrying markup style the document
    or silently lose its own text. The bold tag has to survive as four printed
    characters.
    """
    described = application(lines=[application()["lines"][0] | {"description": "Steel <b>frame</b> & cladding"}])
    runs = drawn_runs(aia_pdf.render_aia_application_pdf(described))
    assert "Steel <b>frame</b> & cladding" in runs, f"the description was parsed instead of printed: {runs[:12]}"
