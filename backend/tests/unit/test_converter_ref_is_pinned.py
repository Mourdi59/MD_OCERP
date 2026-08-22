"""The converter ref is a commit SHA, and both copies of it agree.

A 2026-08-22 licence audit measured what our Windows installer actually
carries. Two facts came out of it that this file exists to keep true.

First, the installer downloads native executables - roughly 220 to 600 MB of
them per format - from a GitHub repository, and the ref used to be the string
``"main"``. Every install therefore fetched whatever the branch tip happened to
be at that moment. Nothing verified a checksum or a signature on that path:
``manifest_verifier.py`` has an Ed25519 verifier, but ``verify_downloaded_file``
has no call sites on the live install path and both of its manifest URLs answer
404. A commit SHA does not replace signing, and it is not claimed to. What it
does is make the bytes addressable: the Contents API puts the ref into the
``download_url`` it returns, so a SHA-pinned listing resolves to SHA-addressed
``raw.githubusercontent.com`` blobs that a later force-push cannot change.

Second, the ref is written down twice - once in the backend, once in the
desktop release workflow that bakes the IFC converter into the Windows
installer. Asserting only that each one looks like a SHA would let them drift
to two *different* SHAs and stay green, which would ship a machine carrying two
builds of the same Qt DLLs. So the equality is the assertion, and the shape
check applies to the single value they agree on.

The upstream repository publishes no tags and no releases (measured on
2026-08-22: ``/tags`` returns an empty array, ``/releases/latest`` returns 404),
so a commit SHA is the only pinnable ref there is. If upstream starts tagging,
widen ``_looks_pinned`` deliberately rather than dropping the gate.

No network here. Everything is read off disk.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.modules.takeoff import router

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "desktop-release.yml"

# A full 40-character lowercase hex commit SHA and nothing else. Abbreviated
# SHAs are rejected on purpose: GitHub resolves them, but an abbreviation can
# become ambiguous as the repository grows, and the whole point is that the ref
# names exactly one tree.
_FULL_SHA = re.compile(r"\A[0-9a-f]{40}\Z")

# The workflow line the gate reads:
#   OE_CONVERTER_REF: ${{ vars.OE_CONVERTER_REF || '<default>' }}
# The repository variable is the deliberate-move knob; the quoted literal is
# the default we are pinning, and it is what this pattern captures.
_WORKFLOW_REF = re.compile(
    r"^\s*OE_CONVERTER_REF:\s*\$\{\{\s*vars\.OE_CONVERTER_REF\s*\|\|\s*'([^']*)'\s*\}\}\s*$",
    re.MULTILINE,
)


def _looks_pinned(ref: str) -> bool:
    return bool(_FULL_SHA.match(ref))


def _workflow_default_ref() -> str:
    """Read the workflow's ref default, failing loudly if it cannot be found.

    Every failure here is a hard failure rather than a skip. A gate that skips
    when its input is missing reports the same green as a gate that passed, and
    the input going missing - a renamed workflow, a moved repository root, a
    rewritten env block - is exactly the change that should wake somebody.
    """
    if not WORKFLOW_PATH.is_file():
        pytest.fail(
            f"{WORKFLOW_PATH} does not exist. This gate keeps the desktop release "
            f"workflow and the backend pinned to the same converter commit; if the "
            f"workflow moved, point this test at its new path rather than deleting it."
        )
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    matches = _WORKFLOW_REF.findall(text)
    if not matches:
        pytest.fail(
            "Could not find an 'OE_CONVERTER_REF: ${{ vars.OE_CONVERTER_REF || '...' }}' "
            f"line in {WORKFLOW_PATH.name}. The bundling step still exists, so either the "
            "env block was rewritten or the override knob was dropped - both need a human."
        )
    if len(set(matches)) > 1:
        pytest.fail(f"The workflow sets OE_CONVERTER_REF to more than one default: {sorted(set(matches))}")
    return matches[0]


# ── The pin itself ───────────────────────────────────────────────────────


def test_the_backend_converter_ref_is_a_commit_sha() -> None:
    """``"main"`` here means every install fetches an unknown tree."""
    assert _looks_pinned(router._DDC_DEFAULT_REF), (
        f"_DDC_DEFAULT_REF is {router._DDC_DEFAULT_REF!r}, which is not a full commit SHA. "
        f"The converter installer downloads native executables from this ref; a branch "
        f"name means the bytes are whatever the branch tip is at install time."
    )


def test_the_release_workflow_pins_the_same_commit_as_the_backend() -> None:
    """One source of truth, checked as equality rather than as shape twice.

    The workflow bakes the IFC converter into the Windows installer while the
    backend downloads dwg/rvt/dgn at runtime. Two different SHAs would put two
    builds of the same Qt DLLs on one machine.
    """
    workflow_ref = _workflow_default_ref()
    assert workflow_ref == router._DDC_DEFAULT_REF, (
        f"desktop-release.yml pins the converter repo at {workflow_ref!r} but "
        f"backend/app/modules/takeoff/router.py pins it at {router._DDC_DEFAULT_REF!r}. "
        f"Bump both or neither."
    )


def test_the_agreed_ref_is_pinned_on_both_sides() -> None:
    """Shape check on the value the two sides agree on, not on each separately."""
    assert _looks_pinned(_workflow_default_ref())


# ── The matcher, checked in both directions ──────────────────────────────
#
# A gate is only worth its green if it can go red. These pin down what
# ``_looks_pinned`` rejects, so a future loosening of the pattern - to let a
# tag through, say - cannot quietly start accepting "main" again.


@pytest.mark.parametrize(
    "ref",
    [
        "main",
        "master",
        "develop",
        "HEAD",
        "v1.0.0",
        "refs/heads/main",
        "",
        "45498426",  # abbreviated: resolves today, ambiguous later
        "45498426fd225c36a2a2a3a67993fd39c5d9d0f",  # 39 chars
        "45498426fd225c36a2a2a3a67993fd39c5d9d0fff",  # 41 chars
        "45498426FD225C36A2A2A3A67993FD39C5D9D0FF",  # uppercase
        "45498426fd225c36a2a2a3a67993fd39c5d9d0gg",  # not hex
        " 45498426fd225c36a2a2a3a67993fd39c5d9d0ff",  # leading space
        "45498426fd225c36a2a2a3a67993fd39c5d9d0ff\n",  # trailing newline
    ],
)
def test_a_ref_that_is_not_a_full_commit_sha_is_rejected(ref: str) -> None:
    assert not _looks_pinned(ref)


def test_a_full_commit_sha_is_accepted() -> None:
    assert _looks_pinned("0123456789abcdef0123456789abcdef01234567")


# ── The override knob still works ────────────────────────────────────────
#
# Pinning is not meant to weld the ref shut. An operator pointing the installer
# at a fork or a newer commit is the supported way to move it, and the older
# env name has to keep working for anyone who already set it.


def test_the_new_env_name_overrides_the_pin() -> None:
    assert router._resolve_converter_ref({"OE_CONVERTER_REF": "some-fork-ref"}) == "some-fork-ref"


def test_the_older_env_name_is_still_honoured() -> None:
    """``OE_CONVERTER_BRANCH`` predates the rename and may be set in the wild."""
    assert router._resolve_converter_ref({"OE_CONVERTER_BRANCH": "legacy-ref"}) == "legacy-ref"


def test_the_new_env_name_wins_when_both_are_set() -> None:
    resolved = router._resolve_converter_ref({"OE_CONVERTER_REF": "new-name", "OE_CONVERTER_BRANCH": "old-name"})
    assert resolved == "new-name"


def test_an_empty_override_falls_back_to_the_pin() -> None:
    """CI exporting an undefined variable yields "", which must not become the ref."""
    assert router._resolve_converter_ref({"OE_CONVERTER_REF": ""}) == router._DDC_DEFAULT_REF
    assert router._resolve_converter_ref({"OE_CONVERTER_BRANCH": ""}) == router._DDC_DEFAULT_REF


def test_no_override_yields_the_pin() -> None:
    assert router._resolve_converter_ref({}) == router._DDC_DEFAULT_REF


# ── The ref reaches the URLs that matter ─────────────────────────────────


def test_the_contents_api_url_carries_the_ref() -> None:
    """The listing URL is what turns the pin into SHA-addressed blob downloads.

    If the ref stopped reaching this f-string the pin would be decorative: the
    API would default to the repository's HEAD and hand back ``download_url``
    values pointing at the branch tip again.
    """
    source = Path(router.__file__).read_text(encoding="utf-8")
    assert "contents/{repo_path}?ref={_DDC_REF}" in source
