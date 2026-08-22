"""Guard: every ``app.*`` hidden import in the desktop spec names a real file.

PyInstaller reports a hidden import it cannot find and keeps going:

    ERROR: Hidden import 'app.modules.<name>.repository' not found

The sidecar build for 15.4.0 printed 167 of those, and all 167 were invented by
``desktop/pyinstaller.spec`` itself: the module auto-discovery loop named six
layers for each of the 191 module packages whether or not the files existed.
Nothing was missing and nothing was broken, which is exactly what made it
dangerous. A dependency that really is absent from the frozen sidecar announces
itself in the same words, on the same channel, and it would have arrived as one
more line in a wall of them. The founder-visible end of that is a user with a
broken install and a build log that could not warn anyone.

The spec now asks the disk before it names a layer, so the channel is quiet and
a line on it means something. This test holds that open in both directions.

What it proves and what it does not: it proves the spec generates no ``app.*``
hidden import that the source tree cannot back. It says nothing about a build
log being clean, and it cannot - the residual noise on a real build comes from
upstream hooks (psycopg2's probe for MySQLdb / pysqlite2 / mx.DateTime,
pycparser's generated lextab / yacctab, scipy's _cdflib, torch's optional
tensorboard, nvcuda.dll on a machine with no CUDA) and none of that is ours to
declare.

It is a pure file-parsing test - the spec is executed with PyInstaller's own
symbols stubbed out, no application import, no build - so it runs anywhere the
suite is collected.
"""

import sys
import types
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_DESKTOP = _BACKEND.parent / "desktop"
_SPEC = _DESKTOP / "pyinstaller.spec"
_MODULES = _BACKEND / "app" / "modules"

# A floor on how many names this guard actually looked at. Without it the whole
# file passes green the day the discovery loop moves out of the spec or an
# upstream rename empties the capture: zero unresolvable names out of twelve
# examined reads identically to zero out of twelve hundred. The tree carries
# 191 module packages and roughly 980 layer files, so anything under this means
# the instrument stopped seeing the population, not that the population shrank.
_MIN_APP_HIDDEN_IMPORTS = 900


class _Opaque:
    """Stand-in for the PyInstaller objects the spec chains attributes off."""

    def __getattr__(self, name: str) -> "_Opaque":
        return _Opaque()


def _run_spec() -> tuple[dict, dict]:
    """Execute ``desktop/pyinstaller.spec``; return its Analysis kwargs and namespace.

    Reading the ``Analysis(hiddenimports=...)`` argument rather than the
    ``hidden_imports`` local is deliberate: the argument is what reaches
    PyInstaller, and a future edit that builds one list and passes another
    would leave this guard measuring the wrong object.

    The namespace comes back with it so the layer names can be read out of the
    spec instead of copied into this file. A second copy would go stale the
    first time the spec learns a layer, and it would go stale in the direction
    that reads worst: the historical control below would report the new layer's
    files as unbacked when they are on disk.
    """
    captured: dict = {}

    def _analysis(*_args, **kwargs) -> _Opaque:
        captured.update(kwargs)
        return _Opaque()

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    # Third-party packages are not installed in the test environment, so the
    # real collect_submodules cannot run and its results are not what this
    # guard is about. The names it returns belong to qdrant_client and
    # sentence_transformers, which requirements-desktop.lock covers and
    # test_desktop_lock_deps.py checks.
    hooks.collect_submodules = lambda *_a, **_k: []
    utils = types.ModuleType("PyInstaller.utils")
    utils.hooks = hooks
    package = types.ModuleType("PyInstaller")
    package.utils = utils

    stubs = {
        "PyInstaller": package,
        "PyInstaller.utils": utils,
        "PyInstaller.utils.hooks": hooks,
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        namespace = {
            "__file__": str(_SPEC),
            "__name__": "pyinstaller_spec_under_test",
            # PyInstaller injects SPECPATH into the spec's namespace; the spec
            # derives every path in it from that one value.
            "SPECPATH": str(_DESKTOP),
            "Analysis": _analysis,
            "PYZ": lambda *_a, **_k: _Opaque(),
            "EXE": lambda *_a, **_k: _Opaque(),
        }
        exec(compile(_SPEC.read_text(encoding="utf-8"), str(_SPEC), "exec"), namespace)  # noqa: S102
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    assert captured, f"parsed no Analysis(...) call from {_SPEC}; this guard went blind"
    return captured, namespace


def _app_hidden_imports() -> list[str]:
    hidden = _run_spec()[0].get("hiddenimports")
    assert isinstance(hidden, list), f"Analysis in {_SPEC} was given no hiddenimports list"
    return [name for name in hidden if name == "app" or name.startswith("app.")]


def _module_layers() -> tuple[str, ...]:
    """The per-module layers the spec declares, read out of the spec itself."""
    layers = _run_spec()[1].get("_MODULE_LAYERS")
    assert layers, (
        f"{_SPEC} no longer defines _MODULE_LAYERS. The historical control in this file rebuilds the "
        "pre-fix cross product from that tuple, so it cannot run without it. Restore the name or "
        "rewrite the control against whatever replaced it - do not leave it reading an empty set."
    )
    return tuple(layers)


def _unresolvable(names) -> list[str]:
    """Names with no ``.py`` file and no package directory under ``backend/``."""
    missing = []
    for dotted in names:
        base = _BACKEND.joinpath(*dotted.split("."))
        if not base.with_suffix(".py").is_file() and not (base / "__init__.py").is_file():
            missing.append(dotted)
    return sorted(missing)


def _module_packages() -> set[str]:
    return {path.parent.name for path in _MODULES.glob("*/__init__.py")}


def _absent_layers_by_census() -> set[str]:
    """The absent layer names, counted a second way.

    ``_unresolvable`` stats one path per candidate name. This globs the tree
    per layer and subtracts, so the two disagree if either instrument is
    miscounting. An upper-bound gate that trusts a single matcher passes when
    that matcher undercounts, and the number this produces is the denominator
    the negative control below rests on.
    """
    packages = _module_packages()
    absent = set()
    for layer in _module_layers():
        present = {path.parent.name for path in _MODULES.glob(f"*/{layer}.py")}
        present |= {path.parent.parent.name for path in _MODULES.glob(f"*/{layer}/__init__.py")}
        absent |= {f"app.modules.{name}.{layer}" for name in packages - present}
    return absent


def _pre_fix_hidden_imports() -> list[str]:
    """The discovery loop as it stood before the disk check, verbatim.

    This is the shipped defect, reproduced. It is what the negative control
    below runs the checker against, so the control is a repeat of the real
    failure rather than an invented one. The defect was the full cross product
    of module packages and whatever layers the spec names, so the layer tuple
    is read from the spec rather than pinned here.
    """
    layers = _module_layers()
    names = []
    for mod_dir in sorted(_MODULES.iterdir()):
        if mod_dir.is_dir() and (mod_dir / "__init__.py").exists():
            names.append(f"app.modules.{mod_dir.name}")
            names.extend(f"app.modules.{mod_dir.name}.{layer}" for layer in layers)
    return names


def test_every_app_hidden_import_in_the_desktop_spec_resolves_to_a_file() -> None:
    names = _app_hidden_imports()
    assert len(names) >= _MIN_APP_HIDDEN_IMPORTS, (
        f"the desktop spec declares only {len(names)} app.* hidden imports, under the floor of "
        f"{_MIN_APP_HIDDEN_IMPORTS}. The tree has {len(_module_packages())} module packages, so this "
        f"guard is no longer reading the discovery loop and a zero from it means nothing. Names seen: "
        f"{sorted(names)}"
    )

    missing = _unresolvable(names)
    assert not missing, (
        f"{len(missing)} hidden import(s) in {_SPEC} name nothing on disk, and PyInstaller will print "
        f"one 'Hidden import ... not found' line for each of them on every desktop build:\n  "
        + "\n  ".join(missing)
        + "\nEither the file is genuinely missing from the sidecar - which is the case this channel "
        "exists to report - or the spec is naming a layer that was never there. Do not silence it by "
        "adding the name to excludes: that list means 'nothing in the sidecar imports this'."
    )


def test_a_hidden_import_that_names_a_file_that_is_not_there_is_reported() -> None:
    """Negative control, one injected name: the checker must single it out."""
    invented = "app.modules.boq.this_layer_was_never_written"
    flagged = _unresolvable([*_app_hidden_imports(), invented])
    assert flagged == [invented], (
        "the checker did not isolate a hidden import naming a file that does not exist; it returned "
        f"{flagged} instead of exactly ['{invented}']"
    )


def test_the_checker_reports_the_layers_the_pre_fix_loop_invented() -> None:
    """Negative control, the real defect: the pre-fix loop, measured two ways."""
    pre_fix = _pre_fix_hidden_imports()
    flagged = set(_unresolvable(pre_fix))
    census = _absent_layers_by_census()

    assert flagged, (
        "the pre-fix discovery loop produced no unresolvable name, so this control proves nothing "
        "about the checker. Either every module now carries all six layers or the checker is broken."
    )
    assert flagged == census, (
        "the two ways of counting the absent layers disagree, so one of them is undercounting. "
        f"Only stat() saw: {sorted(flagged - census)}. Only the glob census saw: {sorted(census - flagged)}"
    )

    # 167 on the 15.4.0 tree. Asserted as a relationship rather than as a
    # literal, because the number moves the moment a module gains or loses a
    # layer file and a stale literal would fail for the wrong reason.
    print(f"pre-fix loop: {len(pre_fix)} names, {len(flagged)} of them unresolvable")
    print("\n".join(sorted(flagged)))

    kept = {name for name in _app_hidden_imports() if name.startswith("app.modules.")}
    assert kept == set(pre_fix) - flagged, (
        "the disk-driven loop did not simply drop the names that no file backs. Dropped but still "
        f"backed: {sorted((set(pre_fix) - flagged) - kept)}. Added and not backed: {sorted(kept - set(pre_fix))}"
    )
