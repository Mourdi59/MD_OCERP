# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the DDC Community converters come from - one declaration, one place.

The converter binaries are NOT published as GitHub Releases. They live
committed in the source repository under
``DDC_WINDOWS_Converters/DDC_CONVERTER_{FORMAT}/``, and the installer walks
them with the GitHub Contents API. Linux users get separate ``.deb`` packages
from the apt source at ``pkg.datadrivenconstruction.io``.

**The ref is a commit SHA and must stay one.** It used to read ``"main"``,
which meant every install fetched whatever the branch tip happened to be at
that moment: no tag, no pin, no checksum, and native executables at the other
end. The ref is not cosmetic here, because the ``download_url`` the Contents
API hands back carries it, so a SHA-pinned listing resolves to SHA-addressed
``raw.githubusercontent.com`` blobs that a later force-push cannot change. A
branch name resolves to whatever that branch points at today.

Upstream publishes no tags and no releases (measured 2026-08-22: ``/tags``
returns an empty array, ``/releases/latest`` returns 404), so a commit SHA is
the only pinnable ref available. This one is the tree the 2026-08-22 licence
audit enumerated - 1266 entries, verified identical to ``main`` at the time of
pinning.

Why this module exists at all, rather than a constant in the takeoff router:
the ref had been written down three times - the installer, the desktop release
workflow, and ``/api/system/converters/version-check`` in ``app.main``. The
version check compares the git-blob SHA of each installed converter against
the ref, and the dashboard turns a mismatch into an "Update available" badge
whose button runs the installer. Two copies that disagree therefore produce a
badge that never clears over a button that reinstalls identical bytes, which
teaches users that our status indicators lie. The workflow copy is checked
against this one by ``tests/unit/test_converter_ref_is_pinned.py``; the two
Python readers now import instead of repeating.

This module deliberately has no imports beyond ``os`` and no dependencies of
its own. ``app.main`` duplicated these constants in the first place so the
system endpoint keeps working when the takeoff module is not loaded (it ships
disabled in some configurations), and importing from here preserves that:
neither reader depends on the other. Keep it that way - anything added here
becomes a dependency of the system endpoint.

Moving the pin is a deliberate act: bump ``DEFAULT_CONVERTER_REF`` below, or
set ``OE_CONVERTER_REF`` to point a fork or a newer commit at the installer
without a code change.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

DEFAULT_CONVERTER_REF = "45498426fd225c36a2a2a3a67993fd39c5d9d0ff"

DEFAULT_CONVERTER_REPO = "datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN"


def resolve_converter_repo(env: Mapping[str, str] | None = None) -> str:
    """Pick the converter repository: the override, then the default."""
    source = os.environ if env is None else env
    return source.get("OE_CONVERTER_REPO") or DEFAULT_CONVERTER_REPO


def resolve_converter_ref(env: Mapping[str, str] | None = None) -> str:
    """Pick the converter ref: new env name, old env name, then the pin.

    Takes ``env`` so the precedence is testable without touching the real
    process environment. An empty string is treated as unset - a CI runner
    that exports ``OE_CONVERTER_REF=`` from an undefined variable should get
    the pin, not an empty ref that would make every Contents API call 404.

    ``OE_CONVERTER_BRANCH`` predates the rename and is still honoured, so an
    operator who already set it does not silently fall back to the pin.
    """
    source = os.environ if env is None else env
    return source.get("OE_CONVERTER_REF") or source.get("OE_CONVERTER_BRANCH") or DEFAULT_CONVERTER_REF


# Per-format directory inside the repo for the Windows binaries. Each holds
# the small ``*Exporter.exe``, the matching ``DDC_Community_*_converter.exe``
# GUI shell, the bundled Qt6 DLLs, and ``platforms/``, ``styles/`` and
# ``datadrivenlibs/`` subfolders.
WINDOWS_CONVERTER_DIRS: dict[str, str] = {
    "rvt": "DDC_WINDOWS_Converters/DDC_CONVERTER_REVIT",
    "ifc": "DDC_WINDOWS_Converters/DDC_CONVERTER_IFC",
    "dwg": "DDC_WINDOWS_Converters/DDC_CONVERTER_DWG",
    "dgn": "DDC_WINDOWS_Converters/DDC_CONVERTER_DGN",
}
