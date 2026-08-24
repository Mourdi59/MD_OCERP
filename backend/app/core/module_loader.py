# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Module loader​‌‍⁠​‌‍⁠​‌‍⁠​‌‍⁠ - discovers, loads, and manages business modules.

Each module is a Python package under app/modules/ with a manifest.py.
The loader handles dependency resolution, lifecycle, and route mounting.

Module lifecycle:
    1. Discovery: scan app/modules/ for manifest.py files
    2. Resolution: topological sort by dependencies
    3. Loading: import module, register models, hooks, events
    4. Mounting: attach router to FastAPI app
    5. Startup: call module.on_startup() if defined
"""

import contextlib
import importlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

MODULES_DIR = Path(__file__).parent.parent / "modules"


def _walk_routes(routes: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Recurse an include tree, rebuilding each route's full URL as it goes."""
    for entry in routes:
        original_router = getattr(entry, "original_router", None)
        if original_router is not None:
            context = getattr(entry, "include_context", None)
            yield from _walk_routes(original_router.routes, prefix + (getattr(context, "prefix", "") or ""))
            continue
        path = getattr(entry, "path", None)
        if isinstance(path, str):
            yield prefix + path, entry


def served_routes(app: FastAPI) -> Iterator[tuple[str, Any]]:
    """Every endpoint the application answers on: its URL, and the route behind it.

    Reading ``path`` off each entry of ``app.routes`` used to be the whole
    answer, because including a router copied its routes into the application's
    own table. FastAPI 0.141 stopped copying: an include appends a single marker
    object that carries the router and resolves paths when a request arrives.
    A marker has no ``path``, so the old reading now sees only the handful of
    routes the application declared itself and reports every mounted module as
    absent - which is silent, and turns a sweep over the application's endpoints
    into a sweep over nothing.

    Do not reach for ``iter_route_contexts`` here, which is the obvious repair
    and was what this function used. It is FastAPI's own flattening, so it
    resolves HTTP paths correctly, but measured on 0.141.1 it yields an EMPTY
    path for every ``APIWebSocketRoute``. Every socket therefore arrived as
    ``""``, which no prefix test can match, and :meth:`ModuleLoader._has_live_routes`
    consequently could not see a module whose only routes are WebSockets - on
    the version CI installs and every fresh install resolves to. Walking the
    include tree ourselves is what makes sockets come back with real URLs.

    Both halves are needed and they come from different places: the URL is only
    known to the include that mounted the route, while everything else about the
    endpoint - its dependencies, its methods, the function itself - lives on the
    route object, whose own ``path`` is the unprefixed one it was declared with.

    One traversal, deliberately, rather than a version test with two branches.
    On the older shape neither private attribute exists, the prefix stays empty
    and the route's own already-prefixed path is yielded, so the same code is
    correct on both. ``original_router`` and ``include_context`` are private and
    have moved once already; if they move again this returns too few routes, so
    callers that can afford it should sanity-check the count rather than trust
    a small answer.
    """
    yield from _walk_routes(app.routes)


def served_paths(app: FastAPI) -> Iterator[str]:
    """Every URL path the application actually answers on. See :func:`served_routes`."""
    for path, _ in served_routes(app):
        yield path


_LOADER_BUILD_TAG: str = "42bfabefac2dd435"


@dataclass
class ModuleManifest:
    """Metadata for a module. Defined in each module's manifest.py."""

    name: str  # Unique module name, e.g. "oe_boq"
    version: str  # SemVer, e.g. "1.0.0"
    display_name: str  # Human-readable name
    description: str = ""
    author: str = ""
    category: str = "core"  # "core", "integration", "regional", "community"
    depends: list[str] = field(default_factory=list)
    optional_depends: list[str] = field(default_factory=list)
    display_name_i18n: dict[str, str] = field(default_factory=dict)  # {"de": "...", "ru": "..."}
    auto_install: bool = False
    enabled: bool = True


@dataclass
class LoadedModule:
    """A module that has been loaded into the application."""

    manifest: ModuleManifest
    package: Any  # The imported Python package
    router: Any | None = None
    models: list[Any] = field(default_factory=list)


class ModuleLoader:
    """Discovers, resolves, and loads modules."""

    def __init__(self) -> None:
        self._manifests: dict[str, ModuleManifest] = {}
        self._modules: dict[str, LoadedModule] = {}
        self._load_order: list[str] = []
        self._disabled: set[str] = set()  # modules disabled via state persistence

    @property
    def loaded_modules(self) -> dict[str, LoadedModule]:
        return self._modules

    def discover(self, modules_dir: Path | None = None) -> list[ModuleManifest]:
        """Scan for manifest.py files across every module root.

        With no argument this walks the whole ``app.modules`` search path:
        the shipped directory plus any runtime root attached by
        :mod:`app.core.module_runtime_root`. A directory name found in more
        than one root is scanned once, from the root Python will import it
        from, so the manifest read here is the manifest that runs.

        An explicit ``modules_dir`` scans only that directory.
        """
        if modules_dir is not None:
            return self._discover_in(modules_dir)

        manifests: list[ModuleManifest] = []
        seen: set[str] = set()
        for root in self._module_roots():
            for manifest in self._discover_in(root, skip=seen):
                manifests.append(manifest)
        return manifests

    @staticmethod
    def _module_roots() -> list[Path]:
        """Every directory ``app.modules`` is searched in, in import order."""
        with contextlib.suppress(Exception):
            from app.core.module_runtime_root import module_search_paths

            return module_search_paths()
        return [MODULES_DIR]

    def _discover_in(self, scan_dir: Path, skip: set[str] | None = None) -> list[ModuleManifest]:
        """Read every manifest in one directory, recording names into ``skip``."""
        manifests: list[ModuleManifest] = []

        if not scan_dir.exists():
            logger.warning("Modules directory not found: %s", scan_dir)
            return manifests

        for module_dir in sorted(scan_dir.iterdir()):
            if skip is not None:
                if module_dir.name in skip:
                    continue
                if module_dir.is_dir() and (module_dir / "manifest.py").exists():
                    skip.add(module_dir.name)
            if not module_dir.is_dir():
                continue
            if module_dir.name.startswith("_"):
                continue

            manifest_file = module_dir / "manifest.py"
            if not manifest_file.exists():
                continue

            try:
                module_path = f"app.modules.{module_dir.name}.manifest"
                mod = importlib.import_module(module_path)
                manifest = getattr(mod, "manifest", None)
                if isinstance(manifest, ModuleManifest):
                    self._manifests[manifest.name] = manifest
                    manifests.append(manifest)
                    logger.info(
                        "Discovered module: %s v%s (%s)",
                        manifest.name,
                        manifest.version,
                        manifest.display_name,
                    )
                else:
                    logger.warning("No valid manifest in %s", module_dir.name)
            except Exception:
                logger.exception("Failed to load manifest from %s", module_dir.name)

        return manifests

    def resolve_order(self) -> list[str]:
        """Topological sort of modules by dependencies."""
        resolved: list[str] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in resolved:
                return
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving: {name}")
            if name not in self._manifests:
                logger.warning("Unknown dependency: %s", name)
                return

            visiting.add(name)
            manifest = self._manifests[name]
            for dep in manifest.depends:
                visit(dep)
            visiting.discard(name)
            seen.add(name)
            resolved.append(name)

        for name, manifest in self._manifests.items():
            if manifest.enabled:
                visit(name)

        self._load_order = resolved
        return resolved

    async def load_all(self, app: FastAPI) -> None:
        """Discover, resolve, and load all modules.

        Reads persisted module states to skip disabled non-core modules.
        """
        from app.core.module_state import load_module_states

        self.discover()

        # Apply persisted states: mark non-core modules as disabled
        states = load_module_states()
        for name, state in states.items():
            if name in self._manifests and not state.enabled:
                manifest = self._manifests[name]
                if manifest.category != "core":
                    manifest.enabled = False
                    self._disabled.add(name)
                    logger.info("Module %s is disabled by persisted state", name)

        order = self.resolve_order()

        logger.info("Loading %d modules in order: %s", len(order), order)

        for module_name in order:
            try:
                await self._load_module(module_name, app)
            except Exception:
                logger.exception("Failed to load module: %s", module_name)
                raise

        logger.info("All modules loaded successfully")

    async def _load_module(self, module_name: str, app: FastAPI) -> None:
        """Load a single module."""
        manifest = self._manifests[module_name]

        # Determine the package directory name (oe_boq → boq if using oe_ prefix)
        # Convention: module directory name = manifest.name without oe_ prefix
        dir_name = module_name.removeprefix("oe_")
        package_path = f"app.modules.{dir_name}"

        try:
            package = importlib.import_module(package_path)
        except ModuleNotFoundError:
            # Try with full name
            package_path = f"app.modules.{module_name}"
            package = importlib.import_module(package_path)

        loaded = LoadedModule(manifest=manifest, package=package)

        # Load router if exists
        try:
            router_module_name = f"{package_path}.router"
            # Plain import: reuse the already-imported router module if present,
            # import it fresh otherwise. Each module is loaded exactly once at
            # startup, so this is all production ever needs. We deliberately do
            # NOT importlib.reload() or pop-and-reimport the router here: a
            # module's router is built once at import time, and including it onto
            # a fresh app does not consume it, so the cached object is always the
            # fully populated one.
            router_mod = importlib.import_module(router_module_name)
            router = getattr(router_mod, "router", None)
            if router:
                # URL convention: kebab-case (hyphens), not snake_case.
                # Python module directories use underscores, but the public
                # REST surface should be hyphenated (`/api/v1/bi-dashboards`,
                # `/api/v1/schedule-advanced`, etc.). Mount on the
                # hyphenated path as the canonical URL, and additionally
                # mirror it under the underscore form so legacy callers
                # do not regress when this convention is tightened.
                kebab_name = dir_name.replace("_", "-")
                prefix = f"/api/v1/{kebab_name}"
                app.include_router(router, prefix=prefix, tags=[manifest.display_name])
                loaded.router = router
                logger.info("Mounted router for %s at %s", module_name, prefix)
                if kebab_name != dir_name:
                    legacy_prefix = f"/api/v1/{dir_name}"
                    app.include_router(
                        router,
                        prefix=legacy_prefix,
                        tags=[manifest.display_name],
                        include_in_schema=False,
                    )
                    logger.info(
                        "Mirrored router for %s at legacy prefix %s",
                        module_name,
                        legacy_prefix,
                    )
        except ModuleNotFoundError as exc:
            # Distinguish two very different cases that both surface as
            # ModuleNotFoundError:
            #   1. The module simply has no router.py - expected, stay quiet.
            #   2. router.py exists but one of its (transitive) imports is
            #      missing - the router silently disappears and every one of
            #      the module's endpoints 404s. That must never be swallowed.
            # The missing module's dotted name is on the exception. When it is
            # the router module itself, case 1; otherwise a dependency of the
            # router failed to import (case 2) and we log loudly so a missing
            # package can be diagnosed instead of producing phantom 404s.
            if exc.name in (router_module_name, f"{package_path}.router"):
                logger.debug("No router for module %s", module_name)
            else:
                logger.warning(
                    "Router for module %s was NOT mounted: import of %r failed "
                    "(%s). The module's API endpoints are unavailable - this "
                    "usually means a required dependency is not installed.",
                    module_name,
                    exc.name,
                    exc,
                    exc_info=True,
                )

        # Load models (for Alembic discovery)
        try:
            models_mod = importlib.import_module(f"{package_path}.models")
            loaded.models = [models_mod]
        except ModuleNotFoundError:
            pass

        # Load hooks
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{package_path}.hooks")

        # Load events
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{package_path}.events")

        # Load validators
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{package_path}.validators")

        # Load pipeline node runners - a module opts node types into the
        # Pipeline Builder's Node Capability Registry by defining a
        # ``pipeline_nodes.py`` that calls ``register_node(...)`` at import
        # time (same autodiscovery contract as hooks/events/validators).
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{package_path}.pipeline_nodes")

        # Call on_startup if defined
        startup = getattr(package, "on_startup", None)
        if callable(startup):
            await startup()

        self._modules[module_name] = loaded
        logger.info("Loaded module: %s v%s", module_name, manifest.version)

    def get_module(self, name: str) -> LoadedModule | None:
        return self._modules.get(name)

    def list_modules(self) -> list[dict[str, Any]]:
        """List all discovered modules with enabled/disabled/loaded status."""
        result: list[dict[str, Any]] = []

        for name, manifest in self._manifests.items():
            loaded = name in self._modules
            loaded_mod = self._modules.get(name)
            result.append(
                {
                    "name": manifest.name,
                    "version": manifest.version,
                    "display_name": manifest.display_name,
                    "display_name_i18n": manifest.display_name_i18n,
                    "description": manifest.description,
                    "author": manifest.author,
                    "category": manifest.category,
                    "depends": manifest.depends,
                    "optional_depends": manifest.optional_depends,
                    "has_router": loaded_mod.router is not None if loaded_mod else False,
                    "loaded": loaded,
                    "enabled": name not in self._disabled,
                    "is_core": manifest.category == "core",
                }
            )

        return result

    # ── Runtime enable / disable ─────────────────────────────────────────

    def is_enabled(self, module_name: str) -> bool:
        """Check if module is enabled (considers state persistence)."""
        if module_name not in self._manifests:
            return False
        return module_name not in self._disabled

    async def enable_module(self, module_name: str, app: FastAPI) -> dict[str, Any]:
        """Enable a disabled module at runtime (loads router, models).

        Also loads any unloaded dependencies required by this module.

        Returns:
            dict with module info after enabling.

        Raises:
            ValueError: If module_name is unknown.
        """
        from app.core.module_state import set_module_enabled as persist_enable

        if module_name not in self._manifests:
            raise ValueError(f"Unknown module: {module_name}")

        manifest = self._manifests[module_name]

        # Already enabled and loaded
        if module_name in self._modules and module_name not in self._disabled:
            return {"name": module_name, "status": "already_enabled"}

        # Ensure required dependencies are loaded first
        for dep in manifest.depends:
            if dep not in self._modules:
                if dep in self._manifests:
                    await self.enable_module(dep, app)
                else:
                    logger.warning("Missing dependency %s for %s", dep, module_name)

        # Update state
        manifest.enabled = True
        self._disabled.discard(module_name)

        # Load if not already loaded. Also force a reload when a stale
        # _modules record exists but the live app route table no longer
        # carries this module's prefix (e.g. routes were stripped by a
        # prior disable) - otherwise the router would never be re-included
        # and the endpoints would keep 404ing until a process restart.
        if module_name not in self._modules or not self._has_live_routes(module_name, app):
            self._modules.pop(module_name, None)
            await self._load_module(module_name, app)

        # Persist
        core_names = {n for n, m in self._manifests.items() if m.category == "core"}
        persist_enable(module_name, True, core_modules=core_names)

        return {
            "name": module_name,
            "status": "enabled",
            "display_name": manifest.display_name,
            "version": manifest.version,
        }

    @staticmethod
    def _route_under_prefix(route_path: str, prefix: str) -> bool:
        """True when ``route_path`` belongs to the module mounted at ``prefix``.

        Boundary-aware: a route is owned by the module only when it equals the
        prefix or sits directly beneath it (``prefix`` + ``/``). A bare
        ``startswith`` would let a short module segment (``/api/v1/schedule``)
        over-match a longer sibling (``/api/v1/schedule-advanced/...``) and strip
        its routes, so match on the path boundary instead.
        """
        return route_path == prefix or route_path.startswith(prefix + "/")

    @classmethod
    def _belongs_to(cls, route: Any, router: Any, prefixes: set[str]) -> bool:
        """Whether an entry in the application's route table is this module's.

        ``original_router`` is what an include leaves behind on current FastAPI,
        and comparing it by identity is exact: it cannot mistake a neighbour
        with a similar name for this module, and it finds the legacy mirror as
        well, since mounting a module twice includes one router twice. Older
        releases have no such attribute and the path is all there is.
        """
        if getattr(route, "original_router", None) is router:
            return True
        path = getattr(route, "path", None)
        return isinstance(path, str) and any(cls._route_under_prefix(path, p) for p in prefixes)

    def _has_live_routes(self, module_name: str, app: FastAPI) -> bool:
        """True if the live ASGI route table carries this module's prefix.

        Mirrors the prefix derivation used by _load_module / disable_module
        (canonical kebab-case plus the legacy underscore mirror). Asked of the
        paths the application serves rather than of ``app.routes`` directly,
        because an included router no longer appears there as its routes: see
        :func:`served_paths`. Answering no about a mounted module makes every
        enable mount it a second time.
        """
        dir_name = module_name.removeprefix("oe_")
        kebab_name = dir_name.replace("_", "-")
        prefixes = (f"/api/v1/{kebab_name}", f"/api/v1/{dir_name}")
        return any(any(self._route_under_prefix(path, p) for p in prefixes) for path in served_paths(app))

    @staticmethod
    def _routes_changed(app: FastAPI) -> None:
        """Tell the application that its route table was edited behind its back.

        ``app.routes`` is a plain list, and removing from it in place is
        invisible to everything that caches a view of it. The published schema
        is one such cache, keyed on a counter the router bumps when routes are
        added through its own methods, so without this a document generated
        before the removal keeps being handed out and keeps describing a module
        that is gone.
        """
        app.openapi_schema = None
        mark = getattr(getattr(app, "router", None), "_mark_routes_changed", None)
        if callable(mark):
            mark()

    async def disable_module(self, module_name: str, app: FastAPI) -> dict[str, Any]:
        """Disable a module at runtime (removes router from app).

        Core modules cannot be disabled.

        Returns:
            dict with module info after disabling.

        Raises:
            ValueError: If module is core or if other enabled modules depend on it.
        """
        from app.core.module_state import set_module_enabled as persist_enable

        if module_name not in self._manifests:
            raise ValueError(f"Unknown module: {module_name}")

        manifest = self._manifests[module_name]

        if manifest.category == "core":
            raise ValueError(f"Module '{module_name}' is a core module and cannot be disabled.")

        # Check that no other enabled module depends on this one
        tree = self.get_dependency_tree(module_name)
        dependents = tree.get("dependents", [])
        enabled_dependents = [d for d in dependents if d not in self._disabled]
        if enabled_dependents:
            raise ValueError(
                f"Cannot disable '{module_name}': required by enabled modules: {', '.join(enabled_dependents)}"
            )

        # Remove the router from the FastAPI app. Two ways of finding it,
        # because there are two ways it can be in there. Current FastAPI does
        # not copy a router's routes on include: it appends one marker per
        # include, holding the router itself, and a marker has no path to match
        # on. Identity is the exact answer there, and it takes the legacy mirror
        # with it in the same pass because both includes carry the same router
        # object. Older releases did copy, so the prefix sweep still has to run:
        # it is the only thing that finds those, and it also catches a route
        # added under the module's prefix by something other than the include.
        loaded = self._modules.get(module_name)
        if loaded and loaded.router:
            dir_name = module_name.removeprefix("oe_")
            kebab_name = dir_name.replace("_", "-")
            prefixes = {f"/api/v1/{kebab_name}", f"/api/v1/{dir_name}"}
            app.routes[:] = [r for r in app.routes if not self._belongs_to(r, loaded.router, prefixes)]
            self._routes_changed(app)
            logger.info(
                "Removed routes for %s (prefixes %s)",
                module_name,
                ", ".join(sorted(prefixes)),
            )

        # Drop the loaded record so a subsequent enable_module() re-runs
        # _load_module() and re-includes the router via app.include_router.
        # Without this, enable_module()'s `module_name not in self._modules`
        # guard stays False, the router is never re-mounted, and every
        # /api/v1/<module>/* route 404s until the process restarts.
        self._modules.pop(module_name, None)

        # Mark as disabled
        manifest.enabled = False
        self._disabled.add(module_name)

        # Persist
        core_names = {n for n, m in self._manifests.items() if m.category == "core"}
        persist_enable(module_name, False, core_modules=core_names)

        return {
            "name": module_name,
            "status": "disabled",
            "display_name": manifest.display_name,
        }

    def get_module_info(self, name: str) -> dict[str, Any]:
        """Detailed module info including dependencies, state, routes."""
        if name not in self._manifests:
            raise ValueError(f"Unknown module: {name}")

        manifest = self._manifests[name]
        loaded = self._modules.get(name)
        dir_name = name.removeprefix("oe_")

        return {
            "name": manifest.name,
            "version": manifest.version,
            "display_name": manifest.display_name,
            "display_name_i18n": manifest.display_name_i18n,
            "description": manifest.description,
            "author": manifest.author,
            "category": manifest.category,
            "depends": manifest.depends,
            "optional_depends": manifest.optional_depends,
            "auto_install": manifest.auto_install,
            "is_core": manifest.category == "core",
            "enabled": name not in self._disabled,
            "loaded": loaded is not None,
            "has_router": loaded.router is not None if loaded else False,
            "route_prefix": f"/api/v1/{dir_name}" if loaded and loaded.router else None,
            "has_models": bool(loaded.models) if loaded else False,
            "dependency_tree": self.get_dependency_tree(name),
        }

    def get_dependency_tree(self, name: str) -> dict[str, Any]:
        """Returns which modules depend on this module (for disable warnings)."""
        if name not in self._manifests:
            raise ValueError(f"Unknown module: {name}")

        # Find all modules that list `name` in their depends
        dependents: list[str] = []
        optional_dependents: list[str] = []
        for mod_name, manifest in self._manifests.items():
            if mod_name == name:
                continue
            if name in manifest.depends:
                dependents.append(mod_name)
            if name in manifest.optional_depends:
                optional_dependents.append(mod_name)

        return {
            "module": name,
            "depends_on": self._manifests[name].depends,
            "optional_depends_on": self._manifests[name].optional_depends,
            "dependents": dependents,
            "optional_dependents": optional_dependents,
            "enabled_dependents": [d for d in dependents if d not in self._disabled],
        }


# Global singleton
module_loader = ModuleLoader()
