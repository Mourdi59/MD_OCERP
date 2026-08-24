# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The version fallback has to name a version, not a pydantic sentinel.

``_resolve_version`` asks ``importlib.metadata`` first and falls back to the
``Settings`` field when that fails. The fallback exists for exactly one
situation: an install whose package metadata cannot be read, which is the frozen
desktop build and a source checkout that was never pip installed. It read
``Settings.model_fields["app_version"].default``, and ``app_version`` is
declared with ``default_factory``, so pydantic keeps ``PydanticUndefined`` in
``default`` and there is no default to read.

``PydanticUndefined`` is an object with a ``__str__``, which is what made this
survive. Nothing raised, so the ``except`` below it never ran and the value
never became "unknown". The line printed to the user was

    OpenConstructionERP vPydanticUndefined

on the one code path that only ever runs when somebody is already trying to
work out what they have installed.

What this file asserts, and the limit of it: it drives the fallback by making
the metadata lookup raise, which is a stand in for the real cause rather than
the cause itself. It cannot prove the frozen build takes this branch. What it
can do is fail the day the fallback stops naming a version, which is the
regression that shipped.
"""

from __future__ import annotations

import argparse
import importlib.metadata
from typing import Any

import pytest

from app.cli import _resolve_version, cmd_version


def _boom(*_args: Any, **_kwargs: Any) -> str:
    raise importlib.metadata.PackageNotFoundError("openconstructionerp")


def test_the_fallback_returns_a_version_and_not_a_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """With metadata unreadable, the fallback still names the version."""
    monkeypatch.setattr(importlib.metadata, "version", _boom)

    resolved = _resolve_version()

    # Named rather than merely truthy. "PydanticUndefined" is a perfectly good
    # non-empty string, so a test that only checked for emptiness would have
    # passed against the defect it exists to catch.
    assert "Undefined" not in resolved, f"the fallback returned a pydantic sentinel: {resolved!r}"
    assert resolved != "unknown", "the fallback gave up where it has a value available"
    assert resolved[0].isdigit(), f"a version starts with a digit, got {resolved!r}"


def test_the_fallback_agrees_with_the_field_it_reads() -> None:
    """The fallback value is the one the model would have produced itself."""
    from app.config import Settings

    field = Settings.model_fields["app_version"]
    factory = field.default_factory
    expected = str(factory()) if factory is not None else str(field.default)  # type: ignore[call-arg]

    assert expected[0].isdigit()
    assert "Undefined" not in expected


def test_the_primary_path_still_wins_when_metadata_is_readable() -> None:
    """A control. Without the patch above, the answer comes from metadata.

    Without this the suite could not tell a fixed fallback from a fallback that
    had quietly become the only path, which would hide a broken metadata lookup
    behind a working default.
    """
    try:
        from_metadata = importlib.metadata.version("openconstructionerp")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("this tree is not pip installed, so there is no primary path to check")

    assert _resolve_version() == from_metadata


def test_the_printed_line_uses_the_resolver(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``version`` prints what the resolver returns, under the same conditions.

    ``cmd_version`` used to carry its own copy of the lookup, which is how one
    of the two copies could be fixed while the other went on printing the
    sentinel. Asserting on the printed line rather than on the source keeps that
    from coming back without pinning how the sharing is written.
    """
    monkeypatch.setattr(importlib.metadata, "version", _boom)

    expected = _resolve_version()
    cmd_version(argparse.Namespace())
    printed = capsys.readouterr().out

    assert f"OpenConstructionERP v{expected}" in printed
    assert "Undefined" not in printed
