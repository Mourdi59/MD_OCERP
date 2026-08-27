#!/usr/bin/env python3
"""Check that the vendored NSIS installer template is upstream plus our one edit.

``desktop/src-tauri/windows/installer.nsi`` is a copy of the template that ships
inside the Tauri bundler, carrying a single deliberate change: on the upgrade
branch of the reinstall page the second radio button, "Do not uninstall", starts
selected instead of the first. The reason is written at length in that file.

Vendoring it costs something, and this script is the payment. The template is a
Handlebars template, not plain NSI: blocks like each-resources and each-binaries
bind to the bundler's internal data model, and the bundler renders it with
strict mode off, so a name that stops existing upstream renders as nothing at
all. A stale copy would therefore not fail the build. It would produce an
installer that is missing files, or missing a language, and say nothing.

So this compares our copy against the real thing. It reads the Tauri CLI version
out of the release workflow rather than carrying its own copy of it, fetches the
template at that tag, applies our edit to what it fetched, and demands the result
match our file byte for byte. Anything else upstream changed, inside our patched
region or anywhere else, shows up as a diff.

The direction matters. A gate that merely ignored our known diff would go green
if upstream rewrote the very lines we patched. This one reconstructs instead: the
pre-edit text must occur in the fetched upstream exactly once, and the
substitution must actually change something. If our copy ever reverts to stock,
the reconstruction no longer matches it and the gate goes red.

It also asserts that ``tauri.conf.json`` still names the vendored file, because
that is the other way the fix can vanish quietly: without the template key the
bundler uses its own built-in copy, and ours sits on disk being perfect and
unused, which no file comparison can notice.

An unreachable or empty upstream is a failure, never a pass. That makes the check
network bound, so it belongs in CI rather than on pre-commit.

Usage:
    python scripts/check_nsis_template_drift.py
    python scripts/check_nsis_template_drift.py --vendored path/to/copy.nsi
    python scripts/check_nsis_template_drift.py --config path/to/tauri.conf.json
    python scripts/check_nsis_template_drift.py --version 2.11.4
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-release.yml"
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
VENDORED = REPO_ROOT / "desktop" / "src-tauri" / "windows" / "installer.nsi"

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v{version}"
    "/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi"
)

# The template was 32007 bytes at 2.11.4. The floor is far below that: it is here
# to reject a truncated body or an error page served with a 200, not to track the
# file's real size.
MIN_UPSTREAM_BYTES = 20_000

# Landmarks that any recognisable version of this template has, spread across the
# file so that a body which is short of one section still fails. A length check
# alone would accept a 30 KB HTML error page.
REQUIRED_ANCHORS = (
    "Var ReinstallPageCheck",
    "Function PageReinstall",
    "Function PageLeaveReinstall",
    "reinst_uninstall:",
    "!insertmacro MUI_LANGUAGE",
)

# Our edit, held as the pair of texts rather than as a diff to ignore, so that an
# upstream rewrite of these very lines is caught instead of skipped. PATCH_BEFORE
# has to appear in the fetched template exactly once.
PATCH_BEFORE = """\
    ; Check the first radio button if this the first time
    ; we enter this page or if the second button wasn't
    ; selected the last time we were on this page
    ${If} $ReinstallPageCheck <> 2
      SendMessage $R2 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${Else}
      SendMessage $R3 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${EndIf}

    ${NSD_SetFocus} $R2
"""

PATCH_AFTER = """\
    ; OpenConstructionERP fork of the stock Tauri template. The block below and
    ; this comment are the only difference from upstream, and
    ; scripts/check_nsis_template_drift.py proves that by fetching the template
    ; at the CLI version pinned in .github/workflows/desktop-release.yml and
    ; reconstructing this file from it.
    ;
    ; What it defends against. On an upgrade the first radio button reads
    ; "Uninstall before installing", and upstream starts it selected, so a user
    ; who clicks Next takes it. That path reaches reinst_uninstall further down,
    ; which reads UninstallString out of the registry and ExecWaits the
    ; uninstaller ALREADY ON DISK, never the one inside the installer being run.
    ; The uninstaller that decides whether an upgrade finishes is therefore the
    ; one that shipped in the version the user already has.
    ;
    ; Every release from v11.7.1 to v15.8.0 shipped an uninstaller whose
    ; process-stop step called nsExec with no /TIMEOUT, and nsExec without a
    ; timeout waits for its child forever. When that child is a PowerShell that
    ; never returns, the uninstaller never returns, the installer waits on the
    ; uninstaller, and the upgrade stops dead on "Closing OpenConstructionERP..."
    ; with nothing to do but the task manager. Those calls are bounded from
    ; v15.9.0 onwards, but a fix to them only reaches a machine one update after
    ; it is installed. That is also why this cannot live in windows/hooks.nsh:
    ; all four hook macros the template offers run later than PageLeaveReinstall.
    ;
    ; So on the upgrade branch, and only there, the second radio button, "Do not
    ; uninstall", starts selected. It skips the old uninstaller and installs over
    ; the existing files after this installer's own NSIS_HOOK_PREINSTALL has
    ; stopped the running processes, and that hook is bounded. The first radio
    ; button is still present and still works for anyone who wants it.
    ;
    ; Scope. Only the upgrade case, $R0 = 1. The same-version case offers a
    ; different pair of choices and keeps its default, and the downgrade case
    ; keeps its default. The WiX migration path is excluded by hand, and that is
    ; the one exclusion that is not obvious: it reaches this page with $R0 = 1
    ; too, but PageLeaveReinstall uninstalls on it whichever button is selected,
    ; so pre-selecting "Do not uninstall" there would show a default the
    ; installer does not honour. The condition also requires $ReinstallPageCheck
    ; to still be empty, which is true only the first time the page is shown, so
    ; a user who picks the first radio button and then walks back into the page
    ; still finds their own choice selected.
    ;
    ; The focus now follows the selection. Upstream did not have to move it,
    ; because it focused the button it had just checked. Leaving it on the first
    ; radio button would put the exposed path one space bar away from a user who
    ; never touches the mouse.
    ;
    ; What this does not fix. The text above the radio buttons still recommends
    ; uninstalling the current version first, which now contradicts the default.
    ; That sentence is a LangString and lives in the bundler's own language
    ; files, not in this template, so it cannot be reached from here. Changing it
    ; would mean supplying a replacement language file for each of the 21
    ; languages we ship, every one of them carrying all 27 strings, which is a
    ; far larger fork than this one is worth.
    ;
    ; When to delete this. Once no supported upgrade path starts below v15.9.0,
    ; every uninstaller in the field is bounded and this file can go back to
    ; being the stock template: drop the template key from tauri.conf.json and
    ; delete the drift gate along with it.
    ${If} $R0 = 1
    ${AndIf} $WixMode <> 1
    ${AndIf} $ReinstallPageCheck == ""
      StrCpy $ReinstallPageCheck 2
    ${EndIf}

    ; Check the first radio button if this the first time
    ; we enter this page or if the second button wasn't
    ; selected the last time we were on this page
    ${If} $ReinstallPageCheck <> 2
      SendMessage $R2 ${BM_SETCHECK} ${BST_CHECKED} 0
      ${NSD_SetFocus} $R2
    ${Else}
      SendMessage $R3 ${BM_SETCHECK} ${BST_CHECKED} 0
      ${NSD_SetFocus} $R3
    ${EndIf}

"""

HANDLEBARS = re.compile(r"\{\{.*?\}\}", re.DOTALL)


class CheckError(Exception):
    """A reason to fail, carrying the message the operator should read."""


def _normalise(text: str) -> str:
    """Line endings only. core.autocrlf is on here, so the working tree is CRLF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def pinned_cli_version(workflow: Path) -> str:
    """The Tauri CLI version the release workflow builds with.

    Read rather than duplicated: a gate that carried its own copy of the version
    would keep passing after the pin moved, which is the one moment it matters.
    """
    if not workflow.is_file():
        raise CheckError(f"release workflow not found: {workflow}")
    found = set(re.findall(r"^\s*TAURI_CLI_VERSION:\s*\"([^\"]+)\"", workflow.read_text(encoding="utf-8"), re.M))
    if not found:
        raise CheckError(f"no TAURI_CLI_VERSION in {workflow}")
    if len(found) > 1:
        raise CheckError(f"TAURI_CLI_VERSION is set to more than one value in {workflow}: {sorted(found)}")
    return found.pop()


def check_config_points_at_the_fork(config: Path) -> None:
    """The bundle config has to name the vendored template, or the fork is inert.

    This is the other way the fix can disappear without a sound. Delete one line
    from tauri.conf.json and the bundler falls back to the template compiled into
    it: our copy stays on disk, stays perfect, and stops being used. Nothing in a
    file comparison can see that, so the coupling is asserted here instead.

    It is deliberately checked against the repo's own path rather than whatever
    --vendored was pointed at, because --vendored exists to feed this script
    deliberately broken copies.
    """
    if not config.is_file():
        raise CheckError(f"tauri config not found: {config}")
    try:
        nsis = json.loads(config.read_text(encoding="utf-8"))["bundle"]["windows"]["nsis"]
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckError(f"{config} has no bundle.windows.nsis section: {exc}") from exc
    template = nsis.get("template")
    if not template:
        raise CheckError(
            f"{config} does not set bundle.windows.nsis.template, so the bundler uses its own built-in "
            f"template and {VENDORED.name} is dead weight. Point it at windows/installer.nsi or, if the "
            "fork is being retired on purpose, delete the vendored template and this script with it."
        )
    named = (config.parent / template).resolve()
    if os.path.normcase(named) != os.path.normcase(VENDORED.resolve()):
        raise CheckError(f"{config} points bundle.windows.nsis.template at {named}, not at {VENDORED}")


def fetch_upstream(version: str) -> str:
    """The stock template at `version`, or a failure. Never an empty success."""
    url = UPSTREAM_URL.format(version=version)
    request = urllib.request.Request(url, headers={"User-Agent": "openconstructionerp-nsis-drift-check"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise CheckError(f"upstream fetch failed: HTTP {exc.code} for {url}") from exc
    except Exception as exc:  # noqa: BLE001 - URLError, timeouts, DNS, TLS all mean the same thing here
        raise CheckError(f"upstream fetch failed: {type(exc).__name__}: {exc} for {url}") from exc

    if status != 200:
        raise CheckError(f"upstream fetch failed: HTTP {status} for {url}")
    if len(body) < MIN_UPSTREAM_BYTES:
        raise CheckError(f"upstream fetch failed: {len(body)} bytes from {url}, expected at least {MIN_UPSTREAM_BYTES}")

    text = _normalise(body.decode("utf-8-sig"))
    missing = [anchor for anchor in REQUIRED_ANCHORS if anchor not in text]
    if missing:
        raise CheckError(f"upstream fetch failed: {url} does not look like the template, missing {missing}")
    return text


def reconstruct(upstream: str) -> str:
    """Upstream with our edit applied, which is what the vendored file must be."""
    occurrences = upstream.count(PATCH_BEFORE)
    if occurrences != 1:
        raise CheckError(
            f"upstream moved: the lines this fork patches occur {occurrences} times upstream, expected exactly 1. "
            "Re-vendor the template and re-derive the patch by hand."
        )
    patched = upstream.replace(PATCH_BEFORE, PATCH_AFTER)
    if patched == upstream:
        raise CheckError("the patch is a no-op, which means PATCH_BEFORE and PATCH_AFTER are the same text")
    return patched


def compare_handlebars(vendored: str, upstream: str) -> list[str]:
    """Every Handlebars expression upstream has, ours must have, as many times."""
    ours, theirs = Counter(HANDLEBARS.findall(vendored)), Counter(HANDLEBARS.findall(upstream))
    problems = []
    for token in sorted((theirs - ours).elements()):
        problems.append(f"missing from the vendored template: {token}")
    for token in sorted((ours - theirs).elements()):
        problems.append(f"present in the vendored template but not upstream: {token}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vendored", type=Path, default=VENDORED, help="the copy to check (default: the repo's)")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW, help="where to read TAURI_CLI_VERSION from")
    parser.add_argument("--config", type=Path, default=TAURI_CONF, help="the tauri config that must name the fork")
    parser.add_argument("--version", help="check against this Tauri CLI version instead of the pinned one")
    args = parser.parse_args()

    try:
        check_config_points_at_the_fork(args.config)
        version = args.version or pinned_cli_version(args.workflow)
        if not args.vendored.is_file():
            raise CheckError(f"vendored template not found: {args.vendored}")
        vendored = _normalise(args.vendored.read_text(encoding="utf-8-sig"))
        upstream = fetch_upstream(version)
        expected = reconstruct(upstream)
    except CheckError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    problems = compare_handlebars(vendored, upstream)
    if vendored != expected:
        diff = difflib.unified_diff(
            expected.splitlines(),
            vendored.splitlines(),
            fromfile=f"upstream tauri-cli-v{version} plus our patch",
            tofile=str(args.vendored),
            lineterm="",
        )
        print("FAIL: the vendored template is not upstream plus our one edit.", file=sys.stderr)
        for line in diff:
            print(line, file=sys.stderr)
        problems.append("content differs")

    if problems:
        print("", file=sys.stderr)
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        print(
            "\nIf upstream moved on purpose, re-fetch the template at the pinned version, re-apply the fork "
            "described in its header comment, and update PATCH_BEFORE and PATCH_AFTER in this script to match.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {args.vendored} is tauri-cli-v{version} plus the reinstall-page default, "
        f"{len(HANDLEBARS.findall(vendored))} Handlebars expressions intact."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
