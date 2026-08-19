"""The desktop bundle must ship the runtime data the wheel force-includes.

A wheel and a frozen sidecar are two ways of shipping one backend, and they
collect files by two unrelated mechanisms. Hatchling walks the ``app`` package
and adds whatever ``force-include`` names on top of it; PyInstaller adds only
what ``desktop/pyinstaller.spec`` lists. Anything the runtime reads from a path
that resolves OUTSIDE the ``app`` package therefore has to be named twice, once
in each file, and until this test there was nothing that made the second naming
happen.

It is written against a failure that reached users. ``app/core/i18n.py``
resolves its catalogue as a ``locales`` directory sitting NEXT TO the ``app``
package, the wheel force-included it, and the spec never did, so no desktop
build had ever carried it. That stayed invisible while a missing catalogue was
a warning that refilled the directory from an embedded copy, and became a
sidecar that exits during startup the moment refilling was correctly replaced
by a hard error. Both halves were defensible on their own; nothing compared
them.

The spec is executed rather than read. A test that greps the spec for a path
passes on a spec that computes the same path and then never appends it, which
is the failure mode being guarded against, so the real module runs with the
PyInstaller API stubbed out and the assertions read the list it actually built.

Blind spot, stated here rather than left to be rediscovered: the denominator is
the wheel's force-include map. A directory the runtime reads that is missing
from BOTH files has no anchor and is invisible to this test. ``alembic.ini`` is
exactly that case today, and its absence is deliberate on both sides: the
frozen bundle carries no ``alembic/`` script directory, so shipping the ini
alone would turn ``stamp_head_if_unstamped``'s graceful "cannot locate it, skip
stamping" into an exception raised during startup.
"""

from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SPEC = ROOT / "desktop" / "pyinstaller.spec"
PYPROJECT = BACKEND / "pyproject.toml"


def _wheel_force_include() -> dict[str, str]:
    """Return the wheel's force-include map, keyed by path relative to backend/."""
    with open(PYPROJECT, "rb") as handle:
        data = tomllib.load(handle)
    targets = data["tool"]["hatch"]["build"]["targets"]
    return dict(targets["wheel"]["force-include"])


def _spec_datas() -> list[tuple[str, str]]:
    """Execute the spec with the PyInstaller API stubbed out and return its ``datas``.

    The spec imports ``collect_submodules`` and calls ``Analysis``/``PYZ``/``EXE``
    at module level. None of that can run here, and none of it decides what the
    bundle carries, so each is replaced by the smallest stand-in that lets the
    module reach the end: the point is to run the real path/append logic above
    them and read the result.
    """
    # Written through __dict__ rather than as attributes because that is what
    # populating a module object actually is, and a type checker reading
    # ModuleType has no way to know these names are meant to exist.
    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.__dict__["collect_submodules"] = lambda _package: []
    utils = types.ModuleType("PyInstaller.utils")
    utils.__dict__["hooks"] = hooks
    pyinstaller = types.ModuleType("PyInstaller")
    pyinstaller.__dict__["utils"] = utils

    captured: dict[str, list[tuple[str, str]]] = {}

    class _Analysis:
        def __init__(self, *_args, **kwargs):
            captured["datas"] = [tuple(entry) for entry in (kwargs.get("datas") or [])]
            # EXE() folds these three into the single file; PYZ() reads .pure.
            self.pure = []
            self.scripts = []
            self.binaries = []
            self.zipfiles = []
            self.datas = captured["datas"]

    namespace: dict[str, object] = {
        "__file__": str(SPEC),
        "__name__": "openconstructionerp_desktop_spec",
        "SPECPATH": str(SPEC.parent),
        "DISTPATH": str(SPEC.parent / "dist"),
        "workpath": str(SPEC.parent / "build"),
        "Analysis": _Analysis,
        "PYZ": lambda *_a, **_kw: None,
        "EXE": lambda *_a, **_kw: None,
    }

    fakes = {
        "PyInstaller": pyinstaller,
        "PyInstaller.utils": utils,
        "PyInstaller.utils.hooks": hooks,
    }
    source = SPEC.read_text(encoding="utf-8")
    with patch.dict(sys.modules, fakes):
        exec(compile(source, str(SPEC), "exec"), namespace)  # noqa: S102

    if "datas" not in captured:
        pytest.fail("the spec ran without ever calling Analysis, so it declared no data files")
    return captured["datas"]


def test_the_spec_declares_data_files_at_all() -> None:
    """Guard the instrument before the assertions that lean on it.

    A stub that swallows the call, or a spec that stops building its list part
    way through, would leave every comparison below vacuously true. Saying how
    many entries were read is what separates "checked and agreed" from "found
    nothing to check".
    """
    datas = _spec_datas()
    print(f"\ndesktop spec declares {len(datas)} data entries")
    assert len(datas) >= 3, (
        f"the spec declared {len(datas)} data entries. It is expected to ship the frontend dist, "
        f"the app package, the locale catalogue and pyproject.toml, so a number this small means "
        f"the spec changed shape and this test is no longer reading what it thinks it is."
    )


def test_the_bundle_ships_what_the_wheel_force_includes() -> None:
    """Every path the wheel force-includes must also reach the frozen bundle.

    Force-include exists precisely for files the package walk cannot see, which
    makes it the register of things the frozen build is most likely to miss:
    they sit outside ``app``, so the one line that ships ``app`` does not carry
    them and no error appears until the runtime reaches for one.
    """
    force_include = _wheel_force_include()
    datas = _spec_datas()
    by_source = {Path(source).resolve(): dest for source, dest in datas}

    verified: list[str] = []
    unverifiable: list[str] = []
    for relative, wheel_dest in sorted(force_include.items()):
        source = (BACKEND / relative).resolve()
        if not source.exists():
            # The frontend dist is absent on a tree nobody has built yet. That
            # is not this test's business to fail on, but it is its business to
            # say so, because a silent skip is how a check reports success over
            # something it never looked at.
            unverifiable.append(f"{relative} (not present on this machine)")
            continue
        assert source in by_source, (
            f"backend/pyproject.toml force-includes {relative!r} into the wheel at {wheel_dest!r}, "
            f"and desktop/pyinstaller.spec never adds it, so the frozen sidecar ships without it. "
            f"Force-included paths sit outside the app package, which is why shipping app/ does not "
            f"carry them. Add datas.append((str(BACKEND / {relative!r}), {wheel_dest!r})) to the spec."
        )
        assert by_source[source] == wheel_dest, (
            f"{relative!r} lands at {wheel_dest!r} in the wheel and at {by_source[source]!r} in the "
            f"frozen bundle. The runtime computes one path for both, so the two destinations have to "
            f"agree or the desktop build looks for the files somewhere they are not."
        )
        verified.append(f"{relative} -> {wheel_dest}")

    print(f"\nverified {len(verified)} of {len(force_include)} force-included paths: {verified}")
    if unverifiable:
        print(f"could not verify {len(unverifiable)}: {unverifiable}")
    assert verified, (
        "no force-included path could be checked, so this test proved nothing. Either the "
        "force-include map is empty or every source it names is missing from this checkout."
    )


def test_the_locale_catalogue_lands_where_the_runtime_looks_for_it() -> None:
    """Pin the invariant itself, not just the agreement between two files.

    The test above compares the spec against the wheel, which is one step removed
    from what actually matters: that the directory arrives at the path
    ``load_translations`` computes. This one asks ``i18n.py`` where that is and
    checks the bundle against the answer, so the check survives the wheel map
    being edited and states plainly why a sibling directory needs its own line.
    """
    from app.core.i18n import LOCALES_DIR

    app_package = Path(__import__("app").__file__).resolve().parent
    locales = LOCALES_DIR.resolve()

    assert locales.parent == app_package.parent, (
        f"the catalogue resolves to {locales}, which is no longer a sibling of the app package at "
        f"{app_package}. If it moved inside the package it is carried by the one line that ships "
        f"app/ and both this test and the spec entry should go; if it moved elsewhere the spec "
        f"destination has to move with it."
    )

    expected_dest = locales.name
    dests = {dest for _source, dest in _spec_datas()}
    assert expected_dest in dests, (
        f"load_translations() reads its catalogue from a directory named {expected_dest!r} sitting "
        f"beside the app package, which in a frozen bundle is sys._MEIPASS/{expected_dest}. The spec "
        f"declares destinations {sorted(dests)} and none of them puts it there, so the sidecar will "
        f"raise FileNotFoundError during startup and the launcher will report only that the backend "
        f"did not start in time."
    )
