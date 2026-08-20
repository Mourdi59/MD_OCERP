#!/usr/bin/env python3
"""Fail the build if a competitor brand leaks in, or a named CAD tool loses its mark.

Two rules live here and they are not the same rule.

Competitor products must never appear in any commit, code, UI string, changelog
or build artifact. Internal research stays internal; everything shippable uses
neutral generic names. The hashed denylist below enforces that one.

CAD authoring tools we convert FROM are the documented exception. Naming them is
the only way to tell a user which files the pipeline actually reads, so they are
allowed in UI strings, and the founder ruling of 2026-08-14 settles the form:
the first mention in each string carries the registered sign, which is the same
treatment the marketing site has used since 2026-07. The trademark form check
enforces that one. It is deliberately hash-free, because here the word is
permitted and only its form is in question, so the report can name it outright
instead of masking it.

English reaches a user through three surfaces, and a check that guards one of
them reports green over the other two. A locale value is the surface everyone
thinks of; an i18n default inside a component is the fallback when a key is
missing, and `guide.eac.selectors.body` has no entry in any of the forty
locales, so its default is the only English that will ever render; a bare
quoted literal in a component never went through i18n at all. All three are
scanned. What is deliberately NOT marked is data: a file-format token
(RVT/DWG/IFC/DGN), a code identifier, the converter's repository slug, a
shipped release note, and a rule pack's `name`, which another file matches
against byte-for-byte.

This gate enforces both automatically so neither relies on a reviewer
remembering. It is wired into both the local pre-commit hook and CI, exactly
like ``check_version_sync.py``.

Brand-safe by design: this file stores only SHA-256 hashes of the lowercased
brand tokens, never the literal brand strings, so the denylist itself does not
put a brand name in the repo. Because SHA-256 collisions are infeasible, the gate
matches ONLY the exact brand tokens, which means it cannot raise a false positive
on an unrelated word. Generic dictionary words that happen to also be product
names are intentionally left out of the automated list (they would match the
ordinary English word) and are covered by human review instead.

When a match is found the report prints the file, line, and a MASKED form of the
token (first and last character plus length) so a developer can locate and remove
it without the log reproducing the full brand string.

Exit codes:
    0  no brand token found, and every named CAD tool carries its mark
    1  a brand token leaked, or a UI string dropped the mark (file:line listed)

Usage::

    python scripts/check_no_brand_tokens.py                # scan all tracked text files (full audit)
    python scripts/check_no_brand_tokens.py path/a path/b  # scan given files (pre-commit)
    python scripts/check_no_brand_tokens.py --since origin/main   # scan only files changed vs a ref (CI guard)

The ``--since`` mode guards against NEW leaks without failing on pre-existing
debt, which is the right way to turn the gate on while a one-time legacy cleanup
proceeds separately. Run with no args for the full audit that drives that cleanup.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# SHA-256 of the lowercased brand tokens. No literal brand strings in this file.
# Add a hash here (python -c "import hashlib;print(hashlib.sha256(b'<token>').hexdigest())")
# to extend coverage. Keep to unambiguous coined brand tokens to avoid matching
# ordinary words.
#
# Founder ruling (2026-07): third-party product names are purged from every
# shippable surface and referred to only by open format (DWG/RVT/IFC/DGN) or a
# neutral category. CAD/BIM coordination product names are therefore denylisted
# below as well. The few genuinely load-bearing uses (our own DDC converter
# repository URL, a file-format detection value the parser compares against) are
# kept precise via the allowlist plus human review, so enforcement never breaks
# our own integration code.
#
# Amended 2026-08-14: the authoring tool the converter reads from is named in UI
# strings rather than purged, so it is deliberately absent from this list. It is
# not an oversight and must not be hashed in: the trademark form check below is
# what governs it, and hashing it would forbid the very strings that ruling
# permits.
_DENY_HASHES: frozenset[str] = frozenset(
    {
        "a62ee5ab3e8914010c0f75ff149f9415c839c64ccf4d8ed91d13b456dbc1d813",
        "d5b51a471ae081ca48018c369ce9341a4db134246a8a7c56dd47df5103e0c8a7",
        "46621e84f68449c6e68788cb4d78d8118cf2511999dc3136f9542ddf21fc2861",
        "fff045f2575092eee58374e6b24e2c3efae8533ac17811cf15939d4fd09a5284",
        "55af965522a877fbb91c42cc317bc592e7ac2282c8b986ea24d9d19b87f3e6de",
        "175144ba7727300741c47f7c881c12c1da553776a583e10c620cd4d24dc2d1ed",
        "6a3007f60515e405e5f64b07885dd24b25262525761bd45808afed3f82425b8e",
        "bf6c262b9b067db8fdc18a6cb0e78d1244553b65c4e9e48d3546af68e0a437a9",
        "423d16ce8c066ceb5714dbb2f9d16eaa59e3571d0318367039755e7e64ceb32f",
        "46c955d11d47c3d563abeefd1eca2b7c9546169b20d2f24cbb897f2fd4ed9ef8",
        "c04ecdbcc01c4eb5a7f93222146d5f4ed5f280a2ed134f7c7c9d4a52c268b6f0",
        "7d451b6eb01abdb0edf3c7fc440f6d06b3aa93223bca35dc207c31aa07da7121",
        "66d4c34f63b321e5d488acb27ceeff03e58861dc822786ecc16228ab966e560a",
        "9c13fc96144b74b5f10957d73a193662ca94dccb1148041280a9f673267150da",
        "f271bb49840f247f06d44e248a58da4f07a15ac13d19c908f3562cf4c27758ea",
        "a5c4fcc701283c5ed540c2963ba42e1f7af1ef3fed2e491525ef0c3a06d3272b",
        "5b02e0eece69d3f4ad8c913705c45d562b1fdd9672d294bb7ebd7aae75f68bad",
        "01fdc206bcfcd06718f3b964c4d6925905d879cee45d7611d4d3e4f414625239",
        "33df103969d7c653bc10754a41a8dc2156aabd7c33647241926d465ba721bb97",
        "f87e86b8abde90aa4ce0d2547c4465280baad22e833afadbebac3d670ea43617",
        "31135ce02873713edfb32a09bf723e1f436fdb080a8457189147a3f34a9412aa",
        "469be0d71cacd255ba602021b352bdba3c4c736eb3dafb824b48fc8c80971209",
        "21ab87a7ea9a7f6f2c7894beb361a8644f8fed69cad090265583d2edceb4966d",
        "9a2e8e955be161ed90ccef3ab2ce3a6a1e439de4a12b8af75536fd0f2ca1b66f",
        "78f01fedb12362675c783eb39ac7afa7c63a9c8d6d56e0542f1565cf026a8612",
        "7bc4be30839398ae59b2f9b2b8144671794537ad9bd829c9e73a93fbd9e51821",
        "fb6061067f2f48fe42db037321556e2c2ecee66c56b75ce935523d51bae05565",
        "48a712c1a4da10ef9c77d217372b97e875800f6a80e4f5bec36ed1b0fe3e921b",
        "2779934ff606047d5b140b82939b66fc88c9ba101a05d156086d71c1285d4bfb",
        "0b955e689bea821d4646d62739a8dec68ee9baf50c4b1e9f7e6fe8e23c75fc03",
        "1cf0fde0df3ac7d0d4af1ad80ebd7bdcdb5c27eb2518594d55a3f59773cc3f3f",
        "a2f98c7785a1629a12cc425bef2583336aef29d12b6c18fcee64f1469454289d",
        "3ccbd9105a45d8fcd4a0101c6532c599f6f59cfa4d4ce378792f547a869a4bea",
        "404e91050d105f97f8785b94706814e4a6ead40fea25c0ecf9efefa6bea999f5",
        "58b4537b616e657203a685e86b79ab85c981615d4c0ad243608f457cbbe0de34",
        "8ae56be495a96f1f31eabe97921415525913c2985c70b473631f52dee05c25be",
        "e0a27b93a6c5fd64c53a87e60bf2eff7113e271567044c910576f2c5dd760e0f",
        # 2026-07 purge: pure competitor tool names (BCF coordination, BIM
        # authoring, estimating, construction management). Format-intrinsic vendor
        # names that spell a file format's own vocabulary (the DWG version labels
        # and binary sentinel, the RVT/DGN header strings) are NOT hashed here -
        # they are functional-interop, kept off the gate and genericized only on
        # user-facing surfaces by review, per the note above.
        "5f37acd72c2cc038391bde05c11697a168667aa4a27c886638faecfd25b1bdd6",
        "aec4c46090689ecbff828e189c03de452bf3709710b168b0864079e631f772d5",
        "5db318368f0b9f5974d745815cfb9290560966eb7c0fac6077192761748bf07e",
        "82713ff6e800821047c46a2c29642fdaee6f4a3dcf2d98006edac2b311340926",
        "7175b0331bdaf8b428d33897b5b55983293776a5a9ca9ea8612cce412003b442",
        "bac8736b4055203b1e2fbbf131280979d0342920a5d1646e257a9a9e6727fcbd",
        "804a7ac7d37b4944a2c02f8e3f6826aa6c15ec82d8ae848f62cac5d0be9e7af3",
        "55efa080d02d76fdd9021db48718aeababaafa85f082ab4152db505b26f6cbf8",
        "62cfc917c13eda7b31202f66f8378344d69f601bab9c89e043807dc763f1e0bc",
        "96aed7c729899185bf13863acea99b958f81be3d5222ea709d49aa0af3e7446b",
        "5696c9f4a0e58aa85c12d312e051162363c3f29a1fcdf0da152f43bf9a7a604b",
        "0aab8b5450e4846d17896c6115b1620d6b5b6ad130666845845c02554546c746",
        "5971b0dc06256600737ca8ba133808b5d8122016a777948e998535036594a95b",
        # 2026-08: real contractors and design practices that reached users as
        # demo tender bidders and project metadata. They were named in
        # app/scripts/seed_demo_4d5d.py and seed_demo_estimates.py, which the
        # earlier demo sweep did not reach, and shipped in every wheel up to
        # 14.2.1. Surnames are hashed one token at a time because the scanner
        # sees maximal [a-z0-9]+ runs, never a two-word company name.
        "b4d969421ab34a7895fc58810b7f1ffc93520b10c9cc6c403ca607b9f29f8c04",
        "f38f6d7164bf334b3282eda983dcb8d5b69e2e14ffa7b4a83532d61aa7ee03be",
        "65266ec0e12375d08a468a83da9d63a57eaaa9a24c3e5cd055ad706598310752",
        "e3c7e82d53a1ce84c284f43915a66bf147c75b2a8baf3f2d476bd2ecd754590c",
        "4e44ac61bc0519ecccc8ae9c2dae453f13ca786a647087c7a2266a6ec5232c94",
        "09c7945dc8a40843b498d79e60716cf57772480d518db5afbbd2d6ab880826fa",
        "20920c3de23ff769ee1c1113c409113c10f7c9d752b55660c3e6b8137589e66a",
        "5fda8083a1784f7ebb246f2d52001eaaf75e1ce06437f297e12b5e5843659f81",
        "fda1bdcc3e8d94633b84d1ec2277cb3400d298a431259af0d46479732d98c15d",
        "ad05969625c093458a9e1df667770ccf71a19b58159126854bd4bda44f0fdaba",
        # Coined replacements that turned out to collide with live construction
        # firms and were withdrawn before release. Hashed so they cannot be
        # invented a second time: the collision rate on plausible-sounding names
        # is roughly one in two, and a name that reads clean is not evidence.
        "467813f7cf203871621e08b72ee4c210215b1f6a4af0e27da53a3cb490fe8bdf",
        "e186dc4cc7fad46dc412de303e24ee681bfe746267c6488d4af0267122f9f6d7",
        # Two more of the same kind, both found in shipped demo data rather than
        # in a candidate list. One was rejected during an earlier sweep for a
        # reason recorded at the time and shipped anyway, which is why rejection
        # has to be written down as a hash and not as a note.
        "f560bc02f626b8160149369482ae0a5827ba6c8bf1da3a53e1a0426afb0a4e02",
        "3baeea126007538168b11698b963e28e40635c3708ae610b17c382bac9dce1fa",
    }
)

# Brand tokens are coined names 5 to 12 characters long. Only hash candidate
# runs in that range so the scan stays fast on large files.
_MIN_LEN = 5
_MAX_LEN = 14
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Only scan source and content file types; skip binaries and vendored trees.
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".mdx",
    ".html",
    ".css",
    ".scss",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".sql",
    ".sh",
    ".env",
    ".cfg",
    ".ini",
    ".rs",
    ".vue",
    ".svelte",
    # An SVG is markup, not a picture, and a logo traced into one carries the
    # name in its title, its id and its class attributes. Leaving the suffix out
    # meant the gate listed all 94 tracked SVGs and then dropped every one of
    # them on the way in. Measured at zero hits across those 94 before adding
    # it, so this closes a hole rather than declaring an amnesty.
    ".svg",
}
_SKIP_PARTS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "_frontend_dist",
}
# This gate stores hashes, never literals, so it never matches itself, but skip
# it anyway to keep the report clean.
_SELF = Path(__file__).resolve()

# Embedded static mirror of DataDrivenConstruction's own converter website
# (datadrivenconstruction.io), kept as a marketing asset. It is not the product
# UI; its cad2data pages name the CAD formats that converter reads and write, plus
# real external blog URLs, which is functional for that product rather than a
# competitor-brand leak in ours. Excluded so the gate does not fight that asset.
_SKIP_FILES = {
    (REPO_ROOT / "website-marketing/pro/breeze/assets/people/ddc_home.html").resolve(),
}

# Reviewed functional-interop exceptions (e.g. an import-format name or an
# integration-target list that tells a user what they can actually connect to).
# Each line is `<path-substr>||<line-substr>`: a hit is allowed only when the
# file path contains <path-substr> (empty = any file) AND the matched line
# contains <line-substr>. This stays precise - a new brand on a different line
# is still caught, because it will not carry the reviewed context substring.
_ALLOWLIST_FILE = REPO_ROOT / "scripts" / "brand_token_allowlist.txt"


# Named CAD authoring tools: allowed in UI strings, required to carry the mark.
# Literals, not hashes, because the point is the form of a permitted word.
_MARKED_NAMES = ("Revit",)
_REGISTERED = "®"
_LOCALE_DIR = "frontend/src/app/locales/"

# A locale entry is one line, `"some.key": "the display string",`. Only the value
# is display text: a key such as `bim.filter_revit_categories` is an identifier
# and is never marked, so the check reads group 2 and ignores group 1.
_LOCALE_ENTRY_RE = re.compile(r'^\s*"([A-Za-z0-9_.\-]+)"\s*:\s*"(.*)"\s*,?\s*$')

# The one context where the name is an identifier rather than a display name:
# the converter's own repository slug, which is part of a URL and must stay
# byte-exact. Anything else that looks slug-like is still reported, because a
# gate that guesses at new slugs would rather quietly permit than ask.
_SLUG_PREFIX = "cad2data-"

# English that ships inside a component instead of a locale file: an i18n
# default. Locale files are not the whole UI, and `guide.eac.selectors.body`
# proves it - that string has no entry in any of the forty locales, so its
# default is the only English a user will ever see and no locale gate can
# reach it. The hint may sit on the line above, because a long default is
# conventionally written as `bodyDefault:` and then the string.
_DEFAULT_HINT_RE = re.compile(r"default|fallback", re.IGNORECASE)
_FRONTEND_SRC = "frontend/src/"
_COMMENT_STARTS = ("//", "*", "/*")

# The third place English ships: a literal written straight into a component,
# with no i18n call and no locale entry behind it, so no translator ever sees
# it. A radio label, a format list and a thrown message all reached users this
# way. Single and double quotes only; see _scan_display_literals for why a
# template literal is not one of them.
_QUOTED_RE = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")
_FIELD_RE = re.compile(r"^\s*(\w+)\s*:")

# A test fixture is not a display string. `__tests__` alone misses the sibling
# convention (`BIMConverterVerifyGate.test.tsx`), which is how an unmarked
# fixture sat inside the scanned set while the gate read green.
_TEST_MARKERS = ("__tests__", ".test.", ".spec.")

# Ruled 2026-08-14: a shipped release note records what was written that day.
# It is a record, not a surface the product restyles, so the marks stay out of
# it. Marking it once and reverting is what settled this; do not re-mark it.
_ARCHIVE_FILES = ("frontend/src/features/about/Changelog.tsx",)

# Closed decision 2026-08-14 - do not reopen this by "fixing" the gate. A rule
# pack's `name` is its identity rather than a label: the same string is the
# pack name in data/bim_rules/*.yaml, and the copy seeded from the frontend has
# to stay byte-exact against it, so a sign on one side would rename the pack on
# that side only. `description`, sitting directly beside it in the same object,
# IS display text and does carry the mark. Scoped to the one file that holds
# seeded pack identities so it cannot quietly widen into an excuse elsewhere.
_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "frontend/src/features/bim_requirements/SEED_PACKS.ts": ("name",),
}


def _unmarked_first_mention(text: str) -> str | None:
    """Name the CAD tool whose first display mention in `text` lacks the mark.

    Only the first mention needs it. "Revit templates read Revit parameters" is
    correct usage, and demanding a sign on every repetition would make the gate
    reject the very wording the ruling produced. German and Nordic compounds
    keep the sign on the name itself, before the hyphen, as in Revit(R)-Modelle,
    so nothing about a following hyphen makes an occurrence exempt.
    """
    for name in _MARKED_NAMES:
        for match in re.finditer(re.escape(name), text):
            start, end = match.span()
            if text[:start].endswith(_SLUG_PREFIX):
                continue  # repository slug inside a URL, not a display name
            if text[end : end + len(_REGISTERED)] != _REGISTERED:
                return name
            break  # first display mention decides; later ones stay bare
    return None


def _code_before_comment(line: str) -> str:
    """Drop a trailing `//` comment, leaving a `https://` URL intact."""
    at = 0
    while True:
        at = line.find("//", at)
        if at == -1:
            return line
        if at and line[at - 1] == ":":
            at += 2
            continue
        return line[:at]


def _scan_trademark_form(path: Path) -> list[tuple[int, str, str]]:
    """Report a locale string whose first CAD tool mention is missing the mark."""
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        entry = _LOCALE_ENTRY_RE.match(line)
        if not entry:
            continue
        key, value = entry.group(1), entry.group(2)
        name = _unmarked_first_mention(value)
        if name:
            hits.append((lineno, key, name))
    return hits


def _scan_component_defaults(path: Path) -> list[tuple[int, str]]:
    """Report an i18n default in a component whose CAD tool mention is bare.

    Same rule as the locale scan, applied to the other place English lives. The
    filter is the shape of the line rather than the file, so an identifier such
    as RevitCategory and a comment about the converter stay out of it: a gate
    that shouted at code would be turned off within a week.
    """
    hits: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return hits
    for lineno, line in enumerate(lines, start=1):
        if line.lstrip().startswith(_COMMENT_STARTS):
            continue
        previous = lines[lineno - 2] if lineno > 1 else ""
        if not (_DEFAULT_HINT_RE.search(line) or _DEFAULT_HINT_RE.search(previous)):
            continue
        name = _unmarked_first_mention(_code_before_comment(line))
        if name:
            hits.append((lineno, name))
    return hits


def _is_test_path(norm: str) -> bool:
    return any(marker in norm for marker in _TEST_MARKERS)


def _scan_display_literals(path: Path, norm: str) -> list[tuple[int, str]]:
    """Report a quoted display string whose CAD tool mention is bare.

    Scope is narrow on purpose, because a rule over every quoted string in the
    frontend reports text that must NOT be marked:

    Template literals are skipped. SEED_PACKS.ts embeds whole YAML rule-pack
    documents in backticks, and the first mention inside one lands in a ``#``
    comment of that embedded document - a comment this rule has no way to read
    as one. Those documents are the same bytes as data/bim_rules/*.yaml and are
    marked there instead, so nothing is lost by not reading them twice.

    Identity fields are skipped per _IDENTITY_FIELDS: a value that another file
    matches against is data, and marking it would edit the data.
    """
    hits: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return hits
    identity = _IDENTITY_FIELDS.get(norm, ())
    in_template = False
    for lineno, line in enumerate(lines, start=1):
        was_inside = in_template
        if (line.count("`") - line.count("\\`")) % 2:
            in_template = not in_template
        if was_inside:
            continue
        if line.lstrip().startswith(_COMMENT_STARTS):
            continue
        code = _code_before_comment(line)
        field = _FIELD_RE.match(line) or (
            _FIELD_RE.match(lines[lineno - 2]) if lineno > 1 else None
        )
        if field and field.group(1) in identity:
            continue
        for match in _QUOTED_RE.finditer(code):
            body = match.group(1) if match.group(1) is not None else match.group(2)
            name = _unmarked_first_mention(body)
            if name:
                hits.append((lineno, name))
                break
    return hits


def _load_allowlist() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not _ALLOWLIST_FILE.is_file():
        return entries
    for raw in _ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "||" not in line:
            continue
        path_sub, _, line_sub = line.partition("||")
        entries.append((path_sub.strip(), line_sub.strip()))
    return entries


def _is_allowed(relpath: str, line: str, allowlist: list[tuple[str, str]]) -> bool:
    rp = relpath.replace("\\", "/")
    return any(
        (not path_sub or path_sub in rp) and line_sub and line_sub in line
        for path_sub, line_sub in allowlist
    )


def _git_files(args: list[str]) -> list[Path]:
    out = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        p = REPO_ROOT / rel
        if p.suffix.lower() in _TEXT_SUFFIXES:
            files.append(p)
    return files


def _tracked_text_files() -> list[Path]:
    return _git_files(["ls-files"])


def _changed_text_files(ref: str) -> list[Path]:
    # Files changed vs the ref (committed diff) plus anything staged/unstaged,
    # so the CI guard catches a leak whether it is committed or in flight.
    seen: dict[str, Path] = {}
    for spec in (
        ["diff", "--name-only", f"{ref}...HEAD"],
        ["diff", "--name-only", "HEAD"],
    ):
        try:
            for p in _git_files(spec):
                seen[str(p)] = p
        except subprocess.CalledProcessError:
            pass
    return list(seen.values())


def _mask(token: str) -> str:
    if len(token) <= 2:
        return "*" * len(token)
    return f"{token[0]}{'*' * (len(token) - 2)}{token[-1]} (len {len(token)})"


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits  # binary or unreadable - nothing to check
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _TOKEN_RE.finditer(line.lower()):
            token = match.group(0)
            if not (_MIN_LEN <= len(token) <= _MAX_LEN):
                continue
            if hashlib.sha256(token.encode("utf-8")).hexdigest() in _DENY_HASHES:
                hits.append((lineno, _mask(token), line))
    return hits


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--since":
        if len(argv) < 2:
            print("[FAIL] --since needs a git ref, e.g. --since origin/main")
            return 1
        candidates = _changed_text_files(argv[1])
    elif argv:
        candidates = [Path(a).resolve() for a in argv]
    else:
        candidates = _tracked_text_files()

    allowlist = _load_allowlist()
    failures: list[str] = []
    unmarked: list[str] = []
    allowed = 0
    for path in candidates:
        rp = path.resolve()
        if rp == _SELF:
            continue
        if rp in _SKIP_FILES:
            continue
        if any(part in _SKIP_PARTS for part in rp.parts):
            continue
        if rp.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if not rp.is_file():
            continue
        try:
            shown = str(rp.relative_to(REPO_ROOT))
        except ValueError:
            shown = str(rp)
        for lineno, masked, line in _scan_file(rp):
            if _is_allowed(shown, line, allowlist):
                allowed += 1
                continue
            failures.append(f"{shown}:{lineno}: brand token {masked}")

        norm = shown.replace("\\", "/")
        if norm.startswith(_LOCALE_DIR):
            for lineno, key, name in _scan_trademark_form(rp):
                unmarked.append(
                    f"{shown}:{lineno}: {key} names {name} with no {_REGISTERED}"
                )
        elif (
            norm.startswith(_FRONTEND_SRC)
            and norm.endswith((".ts", ".tsx"))
            and not _is_test_path(norm)
        ):
            # A default is also a quoted literal, so report each line once and
            # let the more specific message win.
            seen: set[int] = set()
            for lineno, name in _scan_component_defaults(rp):
                seen.add(lineno)
                unmarked.append(
                    f"{shown}:{lineno}: i18n default names {name} with no {_REGISTERED}"
                )
            if norm not in _ARCHIVE_FILES:
                for lineno, name in _scan_display_literals(rp, norm):
                    if lineno in seen:
                        continue
                    unmarked.append(
                        f"{shown}:{lineno}: display string names {name} "
                        f"with no {_REGISTERED}"
                    )

    if unmarked:
        print(
            f"[FAIL] {len(unmarked)} UI string(s) name a CAD tool without the "
            f"registered sign - add {_REGISTERED} to the first mention:"
        )
        for u in unmarked:
            print(f"  {u}")
        print(
            "\nThe name itself is allowed. Only the first mention in a string "
            "takes the sign; later mentions in the same string stay bare."
        )

    if failures:
        print(
            "[FAIL] competitor/vendor brand token(s) found - remove and use a neutral name:"
        )
        for f in failures:
            print(f"  {f}")
        print(
            "\nThese product names must never appear in the repo. Replace with the "
            "neutral generic term used elsewhere in the codebase."
        )

    if failures or unmarked:
        return 1

    note = f" ({allowed} reviewed interop exception(s) allowed)" if allowed else ""
    print(f"[OK] no brand tokens in {len(candidates)} scanned file(s){note}")
    print("[OK] every CAD tool named in a UI string carries the registered sign")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
