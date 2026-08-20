# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The delivery-board demo seed has to be called by something that actually runs.

Two callers, and only one of them reaches an installation that already exists:

* ``demo_projects._seed_module_data`` fills a project as the installer creates
  it, which covers new installations only;
* ``demo_enrichment.enrich_projects`` re-runs over existing projects at boot and
  on every partner-pack apply, which is what fills the estates people open -
  including the public demo this module's bill link was built for.

A seeder wired into the installer alone therefore ships an empty board to
exactly the installations somebody looks at, and no test that calls the seeder
directly can see it: the seeder works, nothing calls it.

Read out of the source because both seeder lists are built inside their
functions from local imports and cannot be inspected as values. The same
reasoning is used by ``tests/pg/test_einvoice_settings_demo_seed.py``.

The installer is read off the disk rather than imported: ``demo_projects`` is
eleven thousand lines that pull in most of the module tree, and importing it to
read one call site would put that cost on every collection of this directory.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.core import demo_enrichment


def test_the_seed_is_wired_into_the_boot_backfill() -> None:
    source = inspect.getsource(demo_enrichment.enrich_projects)
    assert "seed_site_logistics_demo" in source, "the delivery board seeder is not called from the boot backfill"
    assert '"site_logistics"' in source, "the seeder runs but is not named, so its counters log as unknown"
    # Gates, laydown zones and deliveries are records a real project earns, so
    # the seed runs over the demo estate only. A delivery invented inside a
    # customer's live project is a data incident, not a cosmetic one.
    assert "seed_site_logistics_demo(s, _demo_pids)" in source, "the delivery board seeder is not demo-gated"


def test_the_installer_seeds_the_board_for_a_project_it_creates() -> None:
    source = Path(demo_enrichment.__file__).with_name("demo_projects.py").read_text(encoding="utf-8")
    assert "seed_demo_site_logistics" in source, "a freshly installed demo project gets no delivery board"
    # The supplier names come from the template's own tender companies. A
    # literal here would put a firm name into the product that nobody vetted.
    assert "suppliers=[name for name, _email in _firms_list]" in source, (
        "the seeded deliveries do not take their suppliers from the template"
    )
