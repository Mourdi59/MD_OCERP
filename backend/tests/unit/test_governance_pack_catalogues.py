"""The ``pack`` catalogue source: what the active pack ships resolves like any other catalogue.

Pack discovery is replaced by three fakes, so no pack has to be installed.
The bodies are the shipped neutral catalogue under another id: a pack file is
the same JSON a shipped catalogue is.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.partner_pack import discovery
from app.modules.project_governance import catalogue as cat
from app.modules.project_governance import catalogue_packs as packs
from app.modules.project_governance import catalogue_store, evaluator, public
from app.modules.project_governance.catalogue_store import CatalogueStore, resolve_catalogue
from app.modules.project_governance.errors import GovernanceError
from app.modules.project_governance.schemas import ModelChange, ModelSet


def _body(catalogue_id: str, version: int = 1) -> bytes:
    raw = json.loads((cat.CATALOGUE_DIR / "neutral.json").read_text(encoding="utf-8"))
    raw["id"] = catalogue_id
    raw["version"] = version
    return json.dumps(raw).encode("utf-8")


def _entry(catalogue_id: str, version: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "kind": "phase_model",
        "id": catalogue_id,
        "version": version,
        "path": f"catalogues/phase_model/{catalogue_id}_v{version}.json",
        **extra,
    }


def _pack(slug: str, *entries: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(slug=slug, metadata={"catalogues": list(entries)})


class Packs:
    """The installation's packs for one test: which exist, which is active, what files they carry."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.active: SimpleNamespace | None = None
        self.all: list[SimpleNamespace] = []
        self.files: dict[tuple[str, str], bytes] = {}
        monkeypatch.setattr(discovery, "get_active_pack", lambda: self.active)
        monkeypatch.setattr(discovery, "discover_packs", lambda: list(self.all))
        monkeypatch.setattr(discovery, "read_pack_file", lambda slug, rel: self.files.get((slug, rel)))

    def install(self, pack: SimpleNamespace, *, active: bool = False, with_files: bool = True) -> SimpleNamespace:
        self.all.append(pack)
        if active:
            self.active = pack
        if with_files:
            for entry in pack.metadata["catalogues"]:
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    self.files[(pack.slug, entry["path"])] = _body(entry["id"], entry["version"])
        return pack


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> Packs:
    packs.clear_pack_catalogue_cache()
    yield Packs(monkeypatch)
    packs.clear_pack_catalogue_cache()


def _resolve(catalogue_id: str, version: int | None = None, **kwargs: Any) -> Any:
    return asyncio.run(resolve_catalogue(None, "pack", catalogue_id, version, **kwargs))


def _refusal(catalogue_id: str, version: int | None = None, **kwargs: Any) -> GovernanceError:
    with pytest.raises(GovernanceError) as caught:
        _resolve(catalogue_id, version, **kwargs)
    return caught.value


# --------------------------------------------------------------------- the declaration


def test_a_manifest_declares_its_catalogues(installed: Packs) -> None:
    pack = _pack("acme", _entry("acme_model", 2, default_for_new_projects=True, default_for_countries=["de", " at "]))
    (ref,) = packs.declared_catalogues(pack)
    assert ref == packs.PackCatalogue(
        slug="acme",
        kind="phase_model",
        id="acme_model",
        version=2,
        path="catalogues/phase_model/acme_model_v2.json",
        default_for_new_projects=True,
        default_for_countries=("DE", "AT"),
    )


@pytest.mark.parametrize(
    "entry",
    [
        "not an object",
        {"kind": "phase_model", "id": "x", "version": 1},
        {"kind": "phase_model", "id": "x", "version": "1", "path": "x.json"},
        {"kind": "phase_model", "id": "x", "version": 0, "path": "x.json"},
        {"kind": "phase_model", "id": "x", "version": True, "path": "x.json"},
        {"kind": "phase_model", "id": " ", "version": 1, "path": "x.json"},
        {"kind": "phase_model", "id": "x", "version": 1, "path": "x.json", "default_for_countries": "DE"},
    ],
)
def test_a_malformed_entry_is_left_out_and_the_good_one_stays(installed: Packs, entry: Any) -> None:
    pack = _pack("acme", entry, _entry("acme_model"))
    assert [c.id for c in packs.declared_catalogues(pack)] == ["acme_model"]


def test_a_manifest_without_catalogues_declares_none(installed: Packs) -> None:
    assert packs.declared_catalogues(SimpleNamespace(slug="acme", metadata={})) == ()
    assert packs.declared_catalogues(SimpleNamespace(slug="acme", metadata=None)) == ()
    assert packs.declared_catalogues(SimpleNamespace(slug="acme", metadata={"catalogues": {"id": "x"}})) == ()


# --------------------------------------------------------------------- G-01: the resolver


def test_pack_is_a_source_the_api_accepts(installed: Packs) -> None:
    assert "pack" in catalogue_store.SOURCES
    assert ModelSet(catalogue_source="pack", catalogue_id="acme_model").catalogue_source == "pack"
    assert ModelChange(catalogue_source="pack", catalogue_id="acme_model", mapping={}).catalogue_source == "pack"


def test_the_active_packs_catalogue_resolves_through_the_kind(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True)
    resolved = _resolve("acme_model")
    assert isinstance(resolved, cat.Catalogue)
    assert (resolved.id, resolved.version) == ("acme_model", 1)
    # The same body the shipped neutral catalogue is, so the tags came through the same validator.
    assert resolved.host_of("permits") == cat.get_catalogue("neutral").host_of("permits")


def test_without_a_version_the_highest_declared_one_resolves(installed: Packs) -> None:
    installed.install(
        _pack("acme", _entry("acme_model", 1), _entry("acme_model", 3), _entry("acme_model", 2)), active=True
    )
    assert _resolve("acme_model").version == 3
    assert _resolve("acme_model", 2).version == 2
    assert _refusal("acme_model", 9).code == "unknown_catalogue"


def test_an_unknown_kind_or_id_is_not_found(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True)
    refused = _refusal("something_else")
    assert (refused.code, refused.status_code) == ("unknown_catalogue", 404)
    # The shipped id does not leak into the pack source, nor the pack id into the shipped one.
    assert _refusal("neutral").code == "unknown_catalogue"
    with pytest.raises(GovernanceError) as caught:
        asyncio.run(resolve_catalogue(None, "shipped", "acme_model", None))
    assert caught.value.code == "unknown_catalogue"


def test_no_active_pack_means_nothing_to_pin(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")))
    assert _refusal("acme_model").code == "unknown_catalogue"


def test_a_request_id_resolves_only_in_the_active_pack(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True)
    installed.install(_pack("other", _entry("other_model")))
    assert _refusal("other_model").code == "unknown_catalogue"
    # A tenant id changes nothing: a pack catalogue belongs to the installation.
    assert _refusal("other_model", tenant_id="t1").code == "unknown_catalogue"
    assert _resolve("acme_model", tenant_id="t1").id == "acme_model"


def test_a_stored_pin_keeps_resolving_after_another_pack_became_active(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True)
    installed.install(_pack("other", _entry("other_model")))
    assert _resolve("other_model", 1, from_pin=True).id == "other_model"
    # A pin on a pack that is no longer installed at all cannot resolve.
    assert _refusal("gone_model", 1, from_pin=True).code == "unknown_catalogue"


def test_the_active_pack_wins_when_two_packs_declare_one_id(installed: Packs) -> None:
    installed.install(_pack("other", _entry("shared_model", 1)))
    installed.install(_pack("acme", _entry("shared_model", 1)), active=True)
    ref = packs.find_pack_catalogue("phase_model", "shared_model", 1, active_only=False)
    assert ref is not None and ref.slug == "acme"


def test_a_declared_file_that_is_missing_is_named(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True, with_files=False)
    refused = _refusal("acme_model")
    assert (refused.code, refused.status_code) == ("pack_catalogue_invalid", 422)


def test_a_body_that_carries_another_id_or_version_is_refused(installed: Packs) -> None:
    pack = installed.install(_pack("acme", _entry("acme_model"), _entry("second_model", 2)), active=True)
    first, second = (e["path"] for e in pack.metadata["catalogues"])
    installed.files[("acme", first)] = _body("another_id", 1)
    installed.files[("acme", second)] = _body("second_model", 1)
    assert _refusal("acme_model").code == "pack_catalogue_invalid"
    refused = _refusal("second_model")
    assert refused.code == "pack_catalogue_invalid"
    assert "declaration_mismatch" in str(refused)


def test_a_pack_cannot_bring_a_catalogue_the_validator_refuses(installed: Packs) -> None:
    pack = installed.install(_pack("acme", _entry("acme_model"), _entry("junk_model")), active=True)
    first, second = (e["path"] for e in pack.metadata["catalogues"])
    raw = json.loads(_body("acme_model"))
    # A subject outside the vocabulary: the same refusal a tenant catalogue gets on publish.
    raw["document_types"][0]["hosts"] = ["not_a_subject"]
    installed.files[("acme", first)] = json.dumps(raw).encode("utf-8")
    installed.files[("acme", second)] = b"{ not json"
    refused = _refusal("acme_model")
    assert refused.code == "pack_catalogue_invalid"
    assert "document_hosts_unknown" in str(refused)
    assert _refusal("junk_model").code == "pack_catalogue_invalid"


def test_a_replaced_pack_file_is_read_again(installed: Packs) -> None:
    pack = installed.install(_pack("acme", _entry("acme_model")), active=True)
    path = pack.metadata["catalogues"][0]["path"]
    assert _resolve("acme_model").id == "acme_model"
    installed.files[("acme", path)] = _body("renamed", 1)
    assert _refusal("acme_model").code == "pack_catalogue_invalid"


def test_the_new_code_is_registered() -> None:
    assert "pack_catalogue_invalid" in evaluator.ALL_CODES


# --------------------------------------------------------------------- pinning and listing


def test_only_the_active_packs_catalogue_is_pinnable(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model", 2)), active=True)
    installed.install(_pack("other", _entry("other_model")))
    store = CatalogueStore(None)
    assert asyncio.run(store.assert_pinnable(None, "pack", "acme_model", None)) == 2
    with pytest.raises(GovernanceError) as caught:
        asyncio.run(store.assert_pinnable("t1", "pack", "other_model", None))
    assert caught.value.code == "unknown_catalogue"


def test_the_list_offers_the_active_packs_catalogues(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model", 1), _entry("acme_model", 2), _entry("broken")), active=True)
    installed.install(_pack("other", _entry("other_model")))
    installed.files[("acme", "catalogues/phase_model/broken_v1.json")] = b"{ not json"
    items = asyncio.run(CatalogueStore(None).list_available(None))
    from_packs = [i for i in items if i["source"] == "pack"]
    assert [(i["id"], i["latest_version"], i["pack"]) for i in from_packs] == [("acme_model", 2, "acme")]
    assert from_packs[0]["phases"] and from_packs[0]["state"] == "published"
    # The shipped ones are still there.
    assert {"neutral", "hoai_lph"} <= {i["id"] for i in items if i["source"] == "shipped"}


def test_without_a_pack_the_list_is_the_shipped_one(installed: Packs) -> None:
    items = asyncio.run(CatalogueStore(None).list_available(None))
    assert items and {i["source"] for i in items} == {"shipped"}


# --------------------------------------------------------------------- G-02: the default


def test_a_pack_names_the_default_for_new_projects(installed: Packs) -> None:
    installed.install(
        _pack(
            "acme",
            _entry("acme_general", 3, default_for_new_projects=True),
            _entry("acme_german", 1, default_for_countries=["DE"]),
            _entry("acme_plain", 1),
        ),
        active=True,
    )
    assert packs.pack_default_pin("phase_model") == packs.CataloguePin("pack", "acme_general", 3)
    assert packs.pack_default_pin("phase_model", "FR") == packs.CataloguePin("pack", "acme_general", 3)
    # The catalogue named for the country wins over the one named for every country.
    assert packs.pack_default_pin("phase_model", " de ") == packs.CataloguePin("pack", "acme_german", 1)
    assert packs.pack_default_pin("delivery_forms") is None


def test_a_pack_without_an_opinion_or_an_inactive_pack_names_nothing(installed: Packs) -> None:
    installed.install(_pack("other", _entry("other_model", default_for_new_projects=True)))
    assert packs.pack_default_pin("phase_model") is None
    installed.install(_pack("acme", _entry("acme_plain")), active=True)
    assert packs.pack_default_pin("phase_model", "DE") is None


def test_the_default_pin_falls_back_to_the_shipped_country_default(installed: Packs) -> None:
    assert public.default_catalogue_pin("phase_model", "DE") == packs.CataloguePin(
        "shipped",
        cat.default_catalogue_id_for_country("DE"),
        cat.get_catalogue(cat.default_catalogue_id_for_country("DE")).version,
    )
    installed.install(_pack("acme", _entry("acme_model", 2, default_for_new_projects=True)), active=True)
    assert public.default_catalogue_pin("phase_model", "DE") == packs.CataloguePin("pack", "acme_model", 2)


def test_another_kind_without_a_pack_opinion_has_no_default_here(installed: Packs) -> None:
    assert public.default_catalogue_pin("delivery_forms", "DE") is None


def test_a_default_whose_file_is_broken_is_not_the_default(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model", default_for_new_projects=True)), active=True, with_files=False)
    pin = public.default_catalogue_pin("phase_model", None)
    assert pin is not None and pin.source == "shipped"


def test_the_list_marks_exactly_one_default(installed: Packs) -> None:
    store = CatalogueStore(None)
    shipped_default = cat.default_catalogue_id_for_country("DE")
    items = asyncio.run(store.list_available(None, country_code="DE"))
    assert [(i["source"], i["id"]) for i in items if i["default"]] == [("shipped", shipped_default)]
    installed.install(_pack("acme", _entry("acme_model", default_for_countries=["DE"])), active=True)
    items = asyncio.run(store.list_available(None, country_code="DE"))
    assert [(i["source"], i["id"]) for i in items if i["default"]] == [("pack", "acme_model")]
    items = asyncio.run(store.list_available(None, country_code="FR"))
    assert [i["source"] for i in items if i["default"]] == ["shipped"]


# --------------------------------------------------------------------- cloning into a tenant catalogue


class _Repo:
    """The two repository calls a clone makes, kept in memory."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def list_tenant_catalogues(self, *_a: Any, **_k: Any) -> list[Any]:
        return []

    async def add(self, row: Any) -> Any:
        self.added.append(row)
        return row


def _clone(based_on_id: str, version: int | None = None) -> Any:
    store = CatalogueStore.__new__(CatalogueStore)
    store.session = None
    store.repo = _Repo()
    return asyncio.run(
        store.create(
            "tenant-1",
            code="ours",
            name="Our model",
            based_on_source="pack",
            based_on_id=based_on_id,
            based_on_version=version,
            actor_id=None,
        )
    )


def test_a_company_starts_its_own_catalogue_from_the_packs(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model", 1), _entry("acme_model", 2)), active=True)
    row = _clone("acme_model")
    assert (row.tenant_id, row.code, row.state, row.based_on) == ("tenant-1", "ours", "draft", "pack:acme_model@2")
    assert (row.draft_body["id"], row.draft_body["version"]) == ("ours", 1)
    # The pack's structure came along, and the draft is a catalogue the tenant rules accept.
    draft = cat.catalogue_from_body(row.draft_body, source="tenant", origin="clone")
    source = _resolve("acme_model")
    assert [p.code for p in draft.phases] == [p.code for p in source.phases]
    assert draft.host_of("permits") == source.host_of("permits")
    assert _clone("acme_model", 1).based_on == "pack:acme_model@1"


def test_only_the_active_packs_catalogue_can_be_cloned(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True)
    installed.install(_pack("other", _entry("other_model")))
    with pytest.raises(GovernanceError) as caught:
        _clone("other_model")
    assert (caught.value.code, caught.value.status_code) == ("unknown_catalogue", 404)


def test_a_broken_pack_file_cannot_be_cloned(installed: Packs) -> None:
    installed.install(_pack("acme", _entry("acme_model")), active=True, with_files=False)
    with pytest.raises(GovernanceError) as caught:
        _clone("acme_model")
    assert caught.value.code == "pack_catalogue_invalid"
