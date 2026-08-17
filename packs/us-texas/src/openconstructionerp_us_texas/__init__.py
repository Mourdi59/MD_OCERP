"""OpenConstructionERP - Texas construction pack.

State depth for Texas, layered on the national US pack rather than repeating
it. What this pack adds:

* **Sales tax on construction** - a lump sum contract makes the contractor the
  consumer of its materials, a separated contract makes it the seller of them,
  and nonresidential repair and remodeling reverses the whole rule by taxing
  the total charge including labor
* **Prevailing wage** - Texas runs no state wage schedule. The awarding public
  body sets the rate itself, by its own local survey or by adopting the federal
  determination, so the rate is a property of the contract documents
* **Retainage** - the public works cap is 10 percent below a 5 million dollar
  contract price and 5 percent at or above it, and the subchapter does not
  reach contracts estimated under 400 thousand dollars
* **Payment and lien clocks** - 30 days on public work and 35 on private, with
  the lien affidavit falling on the 15th day of a later month rather than after
  a count of days

No cost database is bundled. The rules the application reads are served by the
``oe_us_tx_pack`` backend module, which carries a statutory citation on every
figure; this package is the activatable pack around them.

This package exports a module-level ``MANIFEST`` instance of
:class:`PartnerPackManifest` referenced from ``pyproject.toml``::

    [project.entry-points."openconstructionerp.partner_packs"]
    us-texas = "openconstructionerp_us_texas:MANIFEST"

The OCERP core discovers this entry point at boot, validates the manifest, and
applies the pack overrides (branding, locale, cost regions, validation rule
packs, onboarding script).
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.1.0"
