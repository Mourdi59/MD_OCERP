"""The AGPL-3.0 text has to be present, verbatim, and reachable by the build.

The project declares ``AGPL-3.0-or-later`` everywhere it can - the SPDX
expression in ``pyproject.toml``, the trove classifier, ``NOTICE``, the desktop
installer EULA, and a line in the About page telling users the full text ships
with the source. Up to and including 15.9.1 none of that was true: the repo-root
``LICENSE`` was a summary, no copy of the licence text existed anywhere in the
tree, the built wheel's ``dist-info`` had no licence file, and the container
image carried none either. A summary sitting where the licence belongs is worse
than an obvious absence, because it looks like the thing it replaces.

Two copies of the text exist, and they exist for different consumers:

* ``LICENSE`` at the repo root, which is where the licence conventionally lives,
  where GitHub's detector reads it, and what ``desktop/src-tauri/tauri.conf.json``
  points the installer at.
* ``backend/LICENSE``, which is the one the wheel can actually use. PEP 639
  resolves ``license-files`` against the project root, and for this build that is
  ``backend/``, which cannot reach ``../LICENSE``.

Duplication is the deliberate trade, and this module is what stops it drifting.
The AGPL-3.0 text is frozen (the FSF will not revise version 3), so the only way
the two can diverge is by accident, which is exactly what an assertion is for.

Line endings are normalised before comparing. ``core.autocrlf`` is on for many
contributors, so the working-tree bytes differ by platform even though the git
blob does not; what has to hold is that the text is the same, not that a
checkout picked one convention.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_LICENCE = REPO_ROOT / "LICENSE"
WHEEL_LICENCE = REPO_ROOT / "backend" / "LICENSE"
PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"

# Structural landmarks of the real text, not a fingerprint of one download.
# Section 13 is the clause that makes this the Affero licence rather than the
# GPL, so a file passing every other check and missing that one would be the
# wrong licence shipped under the right name.
REQUIRED_MARKERS = [
    "GNU AFFERO GENERAL PUBLIC LICENSE",
    "Version 3, 19 November 2007",
    "TERMS AND CONDITIONS",
    "0. Definitions.",
    "13. Remote Network Interaction; Use with the GNU General Public License.",
    "17. Interpretation of Sections 15 and 16.",
    "END OF TERMS AND CONDITIONS",
    "How to Apply These Terms to Your New Programs",
]

# The eighteen numbered sections, 0 through 17.
_SECTION_RX = re.compile(r"^\s{2,}(\d{1,2})\. \S", re.MULTILINE)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing licence file: {path}"
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("path", [ROOT_LICENCE, WHEEL_LICENCE], ids=["root", "backend"])
def test_licence_file_is_the_verbatim_agpl_text(path: Path) -> None:
    """Each copy is the licence itself, not a notice pointing at one."""
    text = _text(path)

    for marker in REQUIRED_MARKERS:
        assert marker in text, f"{path.relative_to(REPO_ROOT)} is missing AGPL landmark: {marker!r}"

    sections = {int(m.group(1)) for m in _SECTION_RX.finditer(text)}
    missing = sorted(set(range(18)) - sections)
    assert not missing, f"{path.relative_to(REPO_ROOT)} is missing AGPL sections {missing}"

    # A summary is short. The canonical text is ~34 KB over 661 lines; the floor
    # is well under that so a future FSF-side whitespace nudge cannot fail this,
    # while the 2 KB notice this replaced could never clear it.
    assert len(text) > 30_000, (
        f"{path.relative_to(REPO_ROOT)} is {len(text)} characters - too short to be the AGPL-3.0 text. "
        "A summary or a pointer must not occupy the place the licence belongs."
    )


def test_the_two_licence_copies_are_identical() -> None:
    """``backend/LICENSE`` exists only so the wheel can carry the root one."""
    assert _text(ROOT_LICENCE) == _text(WHEEL_LICENCE), (
        "LICENSE and backend/LICENSE have drifted apart. backend/LICENSE is a copy of the "
        "repo-root licence made because PEP 639 cannot reach outside the project root; "
        "copy the root file over it rather than editing either in place."
    )


def test_the_wheel_build_is_told_to_ship_the_licence() -> None:
    """Without ``license-files`` the text sits in the tree and never travels.

    ``license = "AGPL-3.0-or-later"`` writes ``License-Expression`` into METADATA
    and ships no bytes. This is the line that puts the text at
    ``*.dist-info/licenses/LICENSE`` inside the wheel.
    """
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert re.search(r'^license-files\s*=\s*\[\s*"LICENSE"\s*\]', pyproject, re.MULTILINE), (
        'backend/pyproject.toml no longer declares license-files = ["LICENSE"], so the built '
        "wheel conveys no licence text for the licence it declares."
    )
