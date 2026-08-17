# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the OpenConstructionERP backend sidecar.

Builds the FastAPI backend into a single executable that Tauri
launches as a sidecar process.

Usage:
    cd desktop
    pyinstaller pyinstaller.spec
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Paths
ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_CATALOG = ROOT / "data" / "catalog"

# Collect all backend module packages for hidden imports
modules_dir = BACKEND / "app" / "modules"
hidden_imports = [
    # Embedded PostgreSQL 16 + its drivers. SQLAlchemy picks the driver from
    # the URL at runtime (create_engine), so PyInstaller's static import graph
    # never sees asyncpg / psycopg2 and would otherwise omit them, leaving the
    # frozen sidecar unable to connect to its own database. pixeltable_pgserver
    # boots the cluster; its bundled PG binaries are collected by the
    # hook-pixeltable_pgserver.py hook on hookspath below.
    "asyncpg",
    "psycopg2",
    "pixeltable_pgserver",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "app.cli",
    "app.cli_static",
    "app.main",
    "app.config",
    "app.database",
    "app.core",
    "app.core.module_loader",
    "app.core.i18n",
    "app.core.i18n_router",
    "app.core.permissions",
    "app.core.validation",
    "app.core.validation.engine",
    "app.core.validation.rules",
    "app.core.vector",
    "app.core.hooks",
    "app.core.events",
    "app.core.demo_projects",
    "app.core.marketplace",
    # Heavy feature deps imported lazily / dynamically inside service methods,
    # so PyInstaller's static import graph never sees them and would omit the
    # modules from the frozen sidecar - silently breaking the feature on the
    # DESKTOP build only (the wheel works because pip installs them). PyMuPDF
    # exposes both the legacy "fitz" and the modern "pymupdf" import names and
    # the code uses both. lazrs is the LAZ/COPC decompression backend that
    # laspy imports dynamically, so it must be named explicitly or point-cloud
    # LAZ reads fail at runtime. The cv2 / fitz / pymupdf binary payloads are
    # collected by their pyinstaller-hooks-contrib hooks once the module is in
    # the graph.
    "fitz",  # PyMuPDF - PDF vector takeoff, raster render, text extract
    "pymupdf",  # PyMuPDF modern import alias
    "cv2",  # opencv-python-headless - raster room/wall detector
    "laspy",  # LAS/LAZ/COPC point-cloud reader
    "lazrs",  # laspy's LAZ/COPC decompression backend (dynamic import)
    "pypdf",  # PDF stamping / merge (pdf_stamp, property_dev exports)
]

# The CWICR vector-store client, in the lock since the [semantic-clients] extra
# landed. It is imported inside a function body (qdrant_adapter._get_client) so
# the static graph never sees it, and naming the top-level package alone is not
# enough: the submodules the code reaches for are themselves lazy
# (qdrant_client.http.models, qdrant_client.local for the embedded on-disk
# store). collect_submodules walks the whole package so the frozen sidecar
# carries the same client the wheel does. Without this the lock would ship the
# wheel into the build and PyInstaller would drop it again, leaving the desktop
# channel on the broken behaviour the extra just fixed.
hidden_imports += collect_submodules("qdrant_client")

# The local encoder, in the lock since the [semantic-encoder] extra landed.
# Every import of it sits inside a function body (core/vector.py get_embedder,
# costs/matcher.py), which is thinner than it looks rather than invisible: the
# static graph does follow imports inside function bodies, and a Windows build
# with this line deleted still collected 167 sentence_transformers modules off
# those two call sites. collect_submodules supplies the remaining 18.
#
# It has to be named here for a second reason that has nothing to do with
# imports. embedding_installer.start_background_download() asks
# semantic_library_available() before it fetches anything, and that answers by
# looking up a sentence_transformers spec. A frozen sidecar that carries the
# weights-downloader but not the library would find no spec, decline to start
# the download, and log a single INFO line - the desktop build advertising an
# encoder it had already decided not to fetch.
#
# torch and transformers arrive on their own as module-level imports of
# sentence_transformers, and their binary payloads are collected by the
# pyinstaller-hooks-contrib hooks once the packages are in the graph. They are
# named anyway, because what drags them in is one import statement inside
# somebody else's package and that is a thin thread to hang a gigabyte on.
hidden_imports += collect_submodules("sentence_transformers")
hidden_imports += ["torch", "transformers"]

# Auto-discover modules
if modules_dir.is_dir():
    for mod_dir in sorted(modules_dir.iterdir()):
        if mod_dir.is_dir() and (mod_dir / "__init__.py").exists():
            mod_name = mod_dir.name
            hidden_imports.extend([
                f"app.modules.{mod_name}",
                f"app.modules.{mod_name}.models",
                f"app.modules.{mod_name}.schemas",
                f"app.modules.{mod_name}.router",
                f"app.modules.{mod_name}.service",
                f"app.modules.{mod_name}.repository",
                f"app.modules.{mod_name}.manifest",
            ])

# Data files to include
datas = []

# Frontend dist
if FRONTEND_DIST.is_dir():
    datas.append((str(FRONTEND_DIST), "app/_frontend_dist"))

# Translation files, validation rules, etc. from backend
datas.append((str(BACKEND / "app"), "app"))

# Ship pyproject.toml next to the bundled app package. _detect_version()
# reads the version from the source tree first and only falls back to the
# installed-wheel metadata if it cannot find a pyproject. In a frozen build
# there is no source tree, so without this the sidecar would report whatever
# openconstructionerp version happens to be pip-installed on the build
# machine instead of the real product version. Landing it at the bundle root
# (one level above app/) is exactly where _read_pyproject_version walks to.
_pyproject = BACKEND / "pyproject.toml"
if _pyproject.is_file():
    datas.append((str(_pyproject), "."))

a = Analysis(
    [str(BACKEND / "app" / "cli.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    # Local hooks dir holds hook-pixeltable_pgserver.py, which collects the
    # ~40 MB pginstall/ tree (postgres, initdb, pg_ctl + runtime libs) the
    # embedded cluster needs. Without it the sidecar starts then dies with
    # "postgres executable not found".
    hookspath=[str(Path(SPECPATH) / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    # numpy / pandas / openpyxl / pyarrow are base runtime deps (cost-DB
    # Excel/CSV/Parquet import), so they must NOT be excluded. What is left here
    # is dropped because nothing in the sidecar imports it, and that is the only
    # thing this list is allowed to mean.
    #
    # torch and scipy used to sit here, and the comment above them called the
    # whole list genuinely unused. That was true when it was written and stopped
    # being true when the encoder download went default-on for desktop_mode: the
    # feature ships an embedding model, the model is loaded through
    # sentence_transformers, and sentence_transformers imports torch at module
    # level and pulls scipy through scikit-learn. Excluding them did not slim a
    # build that used them, it removed a feature the same release advertises,
    # and it removed it only on the desktop channel, where nobody installing a
    # wheel would ever see it. Both names are now in requirements-desktop.lock
    # and both are gone from this list.
    #
    # It costs what a machine-learning runtime costs, and the number depends on
    # a decision made in the lock rather than here. torch's Linux wheels on PyPI
    # declare the whole nvidia CUDA stack, so a lock compiled without
    # --torch-backend=cpu adds about 2.7 GB there against about 190 MB on
    # Windows. The lock pins the CPU build, which brings Linux back in line and
    # costs the other two platforms nothing, because their PyPI wheels were
    # CPU-only to begin with. It is worth more than a download counter: the EXE
    # below is a onefile build that unpacks its entire payload to a temporary
    # directory on every launch, so this weight is paid at every start.
    #
    # The Qt bindings stay excluded because the sidecar is a headless HTTP
    # server with no GUI; they are never imported at runtime. That exclusion
    # also avoids PyInstaller's hard abort when a build machine happens to have
    # more than one Qt binding installed (it refuses to bundle both PyQt and
    # PySide), which would otherwise break the build on developer machines that
    # carry a full scientific Python stack.
    #
    # Nothing here may also appear in requirements-desktop.lock. A name in both
    # files is the exact shape of the bug above: a dependency deliberately
    # installed and then deliberately thrown away. That pairing is checked by
    # backend/tests/unit/test_desktop_lock_deps.py.
    excludes=[
        "tkinter",
        "matplotlib",
        "tensorflow",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

# Ad-hoc sign every Mach-O collected into the archive, not only the executable
# wrapped around it. macOS only; PyInstaller ignores the option elsewhere, and
# naming it unconditionally would be a lie about what the build does on Windows.
#
# An ad-hoc signature carries no Team ID, so two ad-hoc binaries can never
# mismatch. The binaries collected into the archive are a different matter: the
# Python framework installed by the build machine is signed by whoever built
# that Python, and PyInstaller packs it verbatim. At launch the onefile
# bootloader extracts the archive to a temporary directory and dlopens the
# framework from there, and dyld compares the two signatures:
#
#   code signature in '.../_MEIxxxxxx/Python.framework/Versions/3.12/Python'
#   not valid for use in process: mapping process and mapped file
#   (non-platform) have different Team IDs
#
# The process is ad-hoc with no Team ID, the framework has a real one, and the
# load is refused. The app reaches "Starting the application server" and stops
# there, on a machine that is otherwise fine. Reported against 14.4.0 on macOS
# 26, Apple Silicon, by a user who had already cleared Gatekeeper by hand.
#
# The fix is to make the payload's identity match the process's rather than to
# grant the process permission to ignore the mismatch. That needs no
# entitlement and no hardened runtime, so Entitlements.plist stays out of this
# and the ad-hoc rule in docs/desktop/MACOS_NOTARIZATION.md still holds: on the
# ad-hoc path, sign with "-" and no timestamp.
#
# This is also a prerequisite for notarization rather than a stopgap. The notary
# service sees a onefile sidecar as one Mach-O and never inspects the archive
# appended to it, so a notarized build made without this would sign the wrapper,
# pass review and still fail to start, with the mismatch now against a real Team
# ID instead of none.
codesign_identity = "-" if sys.platform == "darwin" else None

# Build a SINGLE self-contained executable (onefile), not a onedir folder.
# Tauri ships the sidecar as an externalBin, which must be one standalone file;
# a onedir build (exe + a separate _internal/ folder) cannot be used that way,
# because Tauri copies only the named binary and the sidecar would then fail to
# find its bundled Python runtime and PostgreSQL binaries. Folding a.binaries /
# a.datas / a.zipfiles into EXE produces the single file.
#
# UPX is deliberately off. Compressing the embedded PostgreSQL executables and
# their DLLs risks corrupting them, and UPX-packed binaries frequently trip
# antivirus heuristics, which is the last thing a downloadable installer needs.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="openconstructionerp-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # Keep console for server logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    entitlements_file=None,
)
