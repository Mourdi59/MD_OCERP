# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""app.core.regional_packs - resolve a project's regional pack at runtime.

A regional pack declares what a market expects: its currency, its date and
number formats, its standards, and - the part this module serves - its
``measurement_system``. Until now every one of those values was readable only
through the pack's own ``GET /config/`` endpoint, so a pack changed what an
API caller could *see* and never what the platform *did*.

This module is the lookup that closes that gap for the measurement system. It
reads the packs' own identity fields rather than a hand-written country table:
each pack declares ``countries`` (ISO 3166-1 alpha-2) and ``region_code``, and
a project carries ``country_code`` and ``region``. Country is tried first
because it is the explicit ISO-2 column; ``region`` is free text that the
schema deliberately leaves open to any market, so it is only ever matched as
an exact fallback against a pack's own ``region_code``.

Resolution is deliberately conservative. A country claimed by several packs
resolves only when those packs agree - the three US packs all declare
``imperial``, so ``"US"`` is unambiguous, while a disagreement would return
``None``. Anything unrecognised also returns ``None``, which callers must
treat as "not configured" rather than as a default.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

#: The regional packs consulted at runtime, listed rather than discovered from
#: the filesystem so the import set is explicit and stable. A pack added later
#: belongs here; the integration test
#: ``test_us_pack_measurement_system_governs_boq_validation`` fails when this
#: tuple drifts from the packs on disk.
PACK_CONFIG_MODULES: tuple[str, ...] = (
    "app.modules.asia_pac_pack.config",
    "app.modules.china_pack.config",
    "app.modules.dach_pack.config",
    "app.modules.india_pack.config",
    "app.modules.latam_pack.config",
    "app.modules.mexico_pack.config",
    "app.modules.middle_east_pack.config",
    "app.modules.russia_pack.config",
    "app.modules.sa_pack.config",
    "app.modules.uk_pack.config",
    "app.modules.us_ca_pack.config",
    "app.modules.us_pack.config",
    "app.modules.us_tx_pack.config",
)

#: The measurement systems a pack may declare. A pack naming anything else is
#: ignored rather than passed through, so a typo cannot reach a rule that
#: branches on the value.
_KNOWN_MEASUREMENT_SYSTEMS: frozenset[str] = frozenset({"metric", "imperial"})


@lru_cache(maxsize=1)
def pack_configs() -> tuple[dict[str, Any], ...]:
    """Return every regional pack configuration, imported once and cached.

    Returns:
        The ``PACK_CONFIG`` dict of each module in :data:`PACK_CONFIG_MODULES`,
        in that order. A module without a dict ``PACK_CONFIG`` is skipped.
    """
    configs: list[dict[str, Any]] = []
    for module_name in PACK_CONFIG_MODULES:
        config = getattr(importlib.import_module(module_name), "PACK_CONFIG", None)
        if isinstance(config, dict):
            configs.append(config)
    return tuple(configs)


def packs_for_country(country_code: str | None) -> tuple[dict[str, Any], ...]:
    """Return the packs that claim ``country_code`` in their ``countries`` list.

    Args:
        country_code: ISO 3166-1 alpha-2 code; case and surrounding space are
            ignored. ``None`` or blank matches nothing.

    Returns:
        The matching pack configurations, possibly empty. A country covered by
        both a national and a state pack matches all of them.
    """
    wanted = (country_code or "").strip().upper()
    if not wanted:
        return ()
    return tuple(
        config
        for config in pack_configs()
        if any(str(code).strip().upper() == wanted for code in config.get("countries") or ())
    )


def packs_for_region(region: str | None) -> tuple[dict[str, Any], ...]:
    """Return the packs whose ``region_code`` equals ``region``.

    Args:
        region: A project's region marker, for example ``"DACH"`` or ``"US"``.
            Case and surrounding space are ignored; ``None`` or blank matches
            nothing.

    Returns:
        The matching pack configurations, possibly empty. Only an exact match
        counts: ``region`` is an open free-text field, and guessing at
        near-misses would attach a market to a project that never chose one.
    """
    wanted = (region or "").strip().upper()
    if not wanted:
        return ()
    return tuple(config for config in pack_configs() if str(config.get("region_code") or "").strip().upper() == wanted)


def resolve_measurement_system(*, country_code: str | None = None, region: str | None = None) -> str | None:
    """Resolve the measurement system a project's regional pack declares.

    Country is tried first and region is used only when no pack claims the
    country, because ``country_code`` is a validated ISO-2 column while
    ``region`` is free text.

    Args:
        country_code: The project's ISO 3166-1 alpha-2 country code.
        region: The project's region marker, used as a fallback.

    Returns:
        ``"metric"`` or ``"imperial"`` when exactly one such value is declared
        by the matching packs, otherwise ``None``. ``None`` means "no pack
        answered"; it is not a default and callers must not substitute one.
    """
    candidates = packs_for_country(country_code) or packs_for_region(region)
    declared = {
        str(config.get("measurement_system") or "").strip().lower() for config in candidates
    } & _KNOWN_MEASUREMENT_SYSTEMS
    if len(declared) != 1:
        return None
    return declared.pop()
