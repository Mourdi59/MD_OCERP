# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""The eleven module framework pack states its manifest twice and its files by path.

``manifest.py`` is what the source tree and every text-reading pack check see.
``manifest.json`` is what a pack dropped into the data directory is read from.
Nothing kept the two equal, and a catalogue the manifest names by path is only
found when the file is there and carries the id and version the entry states:
a mismatch does not fail the install, it leaves the catalogue unpinnable.

One test file elsewhere carries a copy of a pack catalogue body so it can run
without the pack being active. The copy is compared with the shipped file here,
so the test cannot go on proving something the pack no longer ships.

Pure filesystem work: no database and no import from ``app``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = _REPO_ROOT / "packs" / "eleven-areas-framework" / "src" / "openconstructionerp_eleven_areas_framework"
_SITE_LOGISTICS_TEST = _REPO_ROOT / "backend" / "tests" / "pg" / "test_site_logistics_decisions_on_pg.py"


def _json_manifest() -> dict[str, Any]:
    return json.loads((_PACKAGE / "manifest.json").read_text(encoding="utf-8"))


def _literal_manifest() -> dict[str, Any]:
    """The keywords of the ``PartnerPackManifest(...)`` call, read without importing it."""
    tree = ast.parse((_PACKAGE / "manifest.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "PartnerPackManifest":
            out: dict[str, Any] = {}
            for keyword in node.keywords:
                assert keyword.arg is not None, "manifest.py passes ** to PartnerPackManifest, which no reader can see"
                if isinstance(keyword.value, ast.Call):
                    out[keyword.arg] = {k.arg: ast.literal_eval(k.value) for k in keyword.value.keywords}
                else:
                    out[keyword.arg] = ast.literal_eval(keyword.value)
            return out
    raise AssertionError("manifest.py holds no PartnerPackManifest(...) call")


def _catalogues() -> list[dict[str, Any]]:
    return list(_json_manifest()["metadata"]["catalogues"])


def test_the_two_manifests_state_the_same_pack() -> None:
    assert _literal_manifest() == _json_manifest()


def test_the_pack_declares_catalogues_to_check() -> None:
    kinds = sorted(entry["kind"] for entry in _catalogues())
    assert kinds == ["delivery_forms", "permit_type", "phase_model", "site_logistics", "stakeholder_framework"]


@pytest.mark.parametrize("entry", _catalogues(), ids=lambda e: f"{e['kind']}:{e['id']}")
def test_every_declared_catalogue_is_the_file_it_names(entry: dict[str, Any]) -> None:
    path = _PACKAGE / entry["path"]
    assert path.is_file(), f"the manifest names {entry['path']}, which the pack does not ship"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert (body.get("id"), body.get("version")) == (entry["id"], entry["version"]), (
        f"{entry['path']} carries {body.get('id')!r} version {body.get('version')!r}, "
        f"the manifest entry says {entry['id']!r} version {entry['version']!r}"
    )


def test_the_locale_overlays_and_the_demo_file_are_shipped() -> None:
    manifest = _json_manifest()
    for locale, relative in manifest["additional_locales"].items():
        overlay = json.loads((_PACKAGE / relative).read_text(encoding="utf-8"))
        assert overlay.get("$locale") == locale, f"{relative} says it is {overlay.get('$locale')!r}"
    demo = json.loads((_PACKAGE / manifest["metadata"]["demo"]["path"]).read_text(encoding="utf-8"))
    declared = {(e["kind"], e["id"], e["version"]) for e in _catalogues()}
    pinned = {(p["kind"], p["id"], p["version"]) for p in demo["pins"] if p["source"] == "pack"}
    assert pinned <= declared, f"the demo file pins catalogues the pack does not declare: {sorted(pinned - declared)}"
    assert demo["project"]["demo_template_id"] in manifest["demo_template_ids"]


def test_the_copy_in_the_site_logistics_test_is_the_shipped_catalogue() -> None:
    """``PACK_ID``, ``PACK_PATH`` and ``PACK_BODY`` there are a copy of one pack entry and its file."""
    wanted = ("PACK_ID", "PACK_PATH", "PACK_BODY")
    namespace: dict[str, Any] = {}
    tree = ast.parse(_SITE_LOGISTICS_TEST.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(_SITE_LOGISTICS_TEST), "exec"), namespace)  # noqa: S102
    assert all(name in namespace for name in wanted), f"{_SITE_LOGISTICS_TEST.name} no longer defines {wanted}"
    entry = next(e for e in _catalogues() if e["kind"] == "site_logistics")
    assert (namespace["PACK_ID"], namespace["PACK_PATH"]) == (entry["id"], entry["path"])
    shipped = json.loads((_PACKAGE / entry["path"]).read_text(encoding="utf-8"))
    assert namespace["PACK_BODY"] == shipped
