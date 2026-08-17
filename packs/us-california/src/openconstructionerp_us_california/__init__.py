"""OpenConstructionERP - California construction pack.

State depth for California, layered on the national US pack rather than
repeating it. What this pack adds:

* **Sales tax on construction** - the contractor is the consumer of the
  materials it installs but the retailer of the fixtures it installs, so one
  invoice carries two tax treatments and the split follows what the item is
  rather than what the contract says. District taxes stack on the 7.25 percent
  statewide base and are a property of the address, republished quarterly
* **Prevailing wage** - California's own regime under the Labor Code, distinct
  from the federal one, biting at 1,000 dollars, with a separate registration
  duty for public works on top of the contractor licence
* **Retention** - 5 percent on public work since 2012 unless the agency made a
  substantially complex finding before bid, and 5 percent on private work too
  for agreements entered into from 1 January 2026
* **Payment and lien clocks** - 30 days on both public and private progress
  payments, 7 days down the chain at 2 percent a month, and a mechanics lien
  window that a recorded notice of completion cuts from 90 days to 30

No cost database is bundled. The rules the application reads are served by the
``oe_us_ca_pack`` backend module, which carries a statutory citation on every
figure; this package is the activatable pack around them.

This package exports a module-level ``MANIFEST`` instance of
:class:`PartnerPackManifest` referenced from ``pyproject.toml``::

    [project.entry-points."openconstructionerp.partner_packs"]
    us-california = "openconstructionerp_us_california:MANIFEST"

The OCERP core discovers this entry point at boot, validates the manifest, and
applies the pack overrides (branding, locale, cost regions, validation rule
packs, onboarding script).
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.1.0"
