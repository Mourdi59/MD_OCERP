"""The vector and encoder checks must import, not merely locate.

``find_spec`` resolves a module without executing it. That is the wrong
question for the two optional extras that are mostly compiled code: lancedb is
almost entirely one Rust library, and sentence-transformers imports torch, a
pile of native shared objects. Either can sit on disk, resolve perfectly, and
still fail to load.

This is not hypothetical. A frozen desktop build was measured reporting
"sentence-transformers installed" while carrying no torch at all, because the
check asked where the module was rather than whether it worked. The operator
reading that line has no way to tell a working install from a broken one, which
is the exact failure ``doctor`` exists to prevent.

The same lesson was already learned once in this file for the PDF readers. These
tests keep it from being unlearned for the other two.

Everything here runs with ``sys.frozen`` set, so the probe imports in-process
and no child interpreter is spawned. That keeps the tests hermetic and fast, and
it exercises the desktop branch, which is where the measured defect lived.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType

import pytest

from app import cli

VECTOR = "Vector search [vector]"
SEMANTIC = "Semantic search [semantic]"


def _named(checks: list[cli.Check], name: str) -> cli.Check:
    found = [c for c in checks if c.name == name]
    assert found, f"the {name!r} check disappeared from the doctor output entirely"
    return found[0]


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Take the in-process branch, so no test spawns the app binary."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)


def _fake_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolves: set[str],
    fails: dict[str, BaseException],
    imported: list[str] | None = None,
) -> None:
    """Make named modules resolve, and optionally blow up on import.

    Every other module keeps the real behaviour, so the rest of the doctor
    output stays truthful and the test is not quietly asserting against a
    stubbed-out world.
    """
    real_find_spec = importlib.util.find_spec
    real_import = importlib.import_module

    def fake_find_spec(name: str, package: str | None = None) -> object:
        if name in resolves:
            return ModuleType(name).__spec__ or object()
        return real_find_spec(name, package)

    def fake_import(name: str, package: str | None = None) -> object:
        if imported is not None:
            imported.append(name)
        if name in fails:
            raise fails[name]
        if name in resolves:
            return ModuleType(name)
        return real_import(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(importlib, "import_module", fake_import)


class TestPresentButBrokenIsNotOk:
    """The case find_spec cannot see, and the whole reason for the change."""

    def test_a_resolvable_lancedb_that_will_not_load_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch, frozen: None
    ) -> None:
        _fake_resolution(
            monkeypatch,
            resolves={"lancedb"},
            fails={
                "lancedb": ImportError("DLL load failed while importing lancedb: %1 is not a valid Win32 application")
            },
        )

        check = _named(cli.check_optional_extras(), VECTOR)

        assert check.status == "error", (
            f"a lancedb that resolves but cannot load was reported as {check.status!r}. "
            "That is find_spec answering 'is it on disk' for a module that is almost "
            "entirely a Rust extension, which is the defect this check exists to catch"
        )
        assert "will not import" in check.message
        assert "DLL load failed" in check.message, "the operator needs the actual failure, not just a verdict"

    def test_a_resolvable_encoder_that_will_not_load_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch, frozen: None
    ) -> None:
        _fake_resolution(
            monkeypatch,
            resolves={"sentence_transformers"},
            fails={"sentence_transformers": ModuleNotFoundError("No module named 'torch'")},
        )

        check = _named(cli.check_optional_extras(), SEMANTIC)

        assert check.status == "error", (
            f"an encoder package with no torch under it was reported as {check.status!r}. "
            "This is the measured frozen-build defect: 167 sentence-transformers "
            "modules present, torch absent, doctor saying installed"
        )
        assert "torch" in check.message, "the missing piece must survive into the message"

    def test_the_broken_hint_repairs_rather_than_installs(self, monkeypatch: pytest.MonkeyPatch, frozen: None) -> None:
        """Telling someone to install what they already have is not a fix."""
        _fake_resolution(
            monkeypatch,
            resolves={"lancedb"},
            fails={"lancedb": ImportError("boom")},
        )

        check = _named(cli.check_optional_extras(), VECTOR)

        assert "--force-reinstall" in check.hint, (
            f"hint for a present-but-broken extra was {check.hint!r}, which asks the "
            "operator to install a package that is already there"
        )


class TestTheOtherTwoStatesStillBehave:
    """Absent and healthy must stay distinguishable from broken."""

    def test_absent_stays_a_warning_with_an_install_hint(self, monkeypatch: pytest.MonkeyPatch, frozen: None) -> None:
        _fake_resolution(monkeypatch, resolves=set(), fails={})

        check = _named(cli.check_optional_extras(), VECTOR)

        assert check.status == "warn", "a stock server without the extra is not an error"
        assert "not installed" in check.message
        assert "--force-reinstall" not in check.hint
        assert "openconstructionerp[vector]" in check.hint

    def test_present_and_importable_is_ok(self, monkeypatch: pytest.MonkeyPatch, frozen: None) -> None:
        _fake_resolution(monkeypatch, resolves={"lancedb"}, fails={})

        check = _named(cli.check_optional_extras(), VECTOR)

        assert check.status == "ok", f"a working lancedb was reported as {check.status!r}: {check.message}"
        assert "imports cleanly" in check.message


class TestTheLookupStillGuardsTheImport:
    """Absent modules must not pay the import cost.

    Importing sentence-transformers pulls torch and takes seconds. The common
    install does not have either, and ``doctor`` is meant to be quick there, so
    the cheap lookup has to run first and short-circuit.
    """

    def test_an_absent_extra_is_never_imported(self, monkeypatch: pytest.MonkeyPatch, frozen: None) -> None:
        imported: list[str] = []
        _fake_resolution(monkeypatch, resolves=set(), fails={}, imported=imported)

        cli.check_optional_extras()

        assert "lancedb" not in imported, "doctor imported a module find_spec had already said was absent"
        assert "sentence_transformers" not in imported, (
            "doctor imported the encoder despite it being absent, which costs a torch "
            "import on every run of a command that is supposed to be quick"
        )

    def test_a_present_extra_is_actually_imported(self, monkeypatch: pytest.MonkeyPatch, frozen: None) -> None:
        """The control: the probe must be reachable, or the test above is vacuous."""
        imported: list[str] = []
        _fake_resolution(monkeypatch, resolves={"lancedb"}, fails={}, imported=imported)

        cli.check_optional_extras()

        assert "lancedb" in imported, (
            "the import probe never ran for a module reported as present, so the "
            "check is still only locating and the absence test above proves nothing"
        )
