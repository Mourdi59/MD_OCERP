#!/usr/bin/env python3
"""i18n computed-key guard: the t() call sites whose key is not a literal.

check_i18n_orphan_keys.py closes the hole where `t('key', {defaultValue})`
names a key no locale file can answer. Its call-site regex requires a quoted
string for the key, and that is not a limitation of its implementation but
the boundary of what it can resolve. Every call site that builds its key at
runtime sits outside it:

    t(`price_breakdown.kind.${c.kind}`, { defaultValue: c.kind })
    t(item.labelKey, { defaultValue: item.defaultLabel })

Both render the English defaultValue in all 40 languages when the key is
missing. That is the same silent failure the orphan guard exists to stop,
arriving through a door it cannot watch. nav.credentials reached production
through the second shape: a sidebar entry whose key existed in no locale
file, invisible to the orphan scan and to the locale-gap scan alike, reading
correct English to every reviewer who opened the page.

This guard asks only about en.ts, deliberately. "Is this key answered by
every locale" already belongs to the orphan guard, and a second script
answering the same question would give two baselines for one fact and neither
would be trusted. A key absent from en.ts is the unambiguous case: it exists
nowhere, no translator was ever asked for it, and the English default is all
anyone will ever see.

Three shapes, and the difference between them is the whole design.

  * Template literal, static head. `price_breakdown.kind.${kind}` cannot be
    resolved to its members without knowing the union, and c.kind arrives
    from the wire as a string, so no amount of cleverness recovers them. But
    "does en.ts hold ANY key beginning with `price_breakdown.kind.`" is
    decidable without knowing a single member, and an empty answer proves
    the entire family is unanswerable. That is the first check.

    It used to stop there, on the claim that a populated prefix might still
    be missing individual members and this guard could say nothing about
    those. That claim was one step short of true. Once en.ts answers a
    prefix, its members are no longer hypothetical: they are literal
    dictionary entries sitting in the file this script has already parsed.
    schedule_advanced.rnc.manpower is exactly as literal as any key the
    orphan guard resolves from a call site, and asking whether every OTHER
    locale carries it is the same question the orphan guard already knows
    how to ask, just fed a key list gathered from en.ts instead of from a
    quoted call site. So the second check enumerates the concrete members of
    every prefix en.ts answers, and asks each of the other locales for each
    of them, exactly as the orphan guard would. A family being "answered"
    used to mean en.ts alone; it now means every locale that has to.
    schedule_advanced.rnc reached 38 of 38 locales that need their own copy
    only because someone measured it by hand outside this script - this
    check exists so the next family like it does not need a human to notice.

  * Literal key paired with a default in a table. `{ labelKey: 'nav.x',
    defaultLabel: 'X' }` is fully resolvable even though the call site that
    consumes it is not, because the key is right there as a literal. This is
    the nav.credentials shape and it is checked exactly. The same prop is
    written under six names in this tree (defaultLabel, defaultName,
    defaultDesc, defaultText, defaultTitle, defaultHelp) and all six pair,
    because a guard keyed to one of them would report the class clean while
    its siblings went unread.

  * Everything else. A bare variable (`t(job.stage, {defaultValue})`), a
    template whose interpolation comes first and leaves no prefix. These
    cannot be resolved at all. They are counted, named, and printed under a
    heading that says they were not checked. A gate that drops what it
    cannot resolve is worse than no gate, because the clean exit reads as
    coverage over ground nobody looked at.

Known debt lives in the baseline file and may only shrink. The prop-shaped
class had no findings when this was written, so it contributes nothing to the
baseline and any new break of that shape fails on arrival.

The baseline arrived at 118 entries. It passed through 188 while the families
were being worked, but that intermediate never existed on main, so the seventy
reasons taken off it are not recoverable from history and would have to be
re-derived from the call sites. Each remaining entry carries its reason because
a bare list of prefixes decays into a list nobody can audit: the reason is the
only thing that tells a later reader whether a family may come off.

The member-completeness check has its own baseline, i18n_computed_member_
baseline.json, and it is a worklist rather than an allowlist for a reason a
plain list of prefixes would not give it. Each entry names the prefix, the
member count and the locale coverage it was frozen at, for example
`"schedule_advanced.rnc.": {"members": 9, "locales_ok": 38, "locales_total":
43, "missing": {"uz": [...]}}`. A prefix recorded only by name tells a later
reader nothing about whether the debt is one locale short of done or has
barely started; the count is what turns the entry into a thing someone can
work down instead of a permanent excuse. The `missing` map is the same shape
i18n_orphan_baseline.json already uses for literal keys, key by key rather
than a plain locale count, because a count cannot tell a repaired locale from
a newly broken one and this baseline may only shrink in the same sense the
orphan baseline does: fewer locales missing each member, never more.

This script, that baseline and the repo-hygiene job that runs it are one change
and cannot be split into three. The job names this file by path, and both this
file and the baseline arrived untracked, so any commit carrying the workflow
without them is red the moment it lands.

One thing to know before correcting English anywhere this guard points. Once a
family has members in en.ts, i18next never reaches its defaultValue, so the
label table at the call site stops being what anyone reads and becomes the
fallback for values outside the declared set. Fixing wording in that table alone
therefore changes the code and not the screen, which is exactly what happened to
the ROM reconciliation band: the table was corrected, the keys had landed hours
earlier, and the panel went on showing the older wording. Worse, the test over
that panel mocks react-i18next, so t() hands back the defaultValue and the
assertions are about the table. It was green throughout. A test written that way
proves the fallback correct and says nothing at all about what renders, so the
place to check a string this guard has landed is en.ts.

Parser desync is a failure, not a pass, on the same reasoning as the sibling
guards: en.ts parsing to zero keys, or a source tree yielding no call sites,
exits 2 rather than reporting a clean scan of nothing.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

DEFAULT_EN_PATH = "frontend/src/app/locales/en.ts"
DEFAULT_SOURCE_GLOB = "frontend/src/**/*.ts*"
DEFAULT_BASELINE_PATH = "scripts/i18n_computed_key_baseline.json"
DEFAULT_LOCALE_GLOB = "frontend/src/app/locales/*.ts"
DEFAULT_MEMBER_BASELINE_PATH = "scripts/i18n_computed_member_baseline.json"

_CLDR_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")

# `"key": ` at the head of a line, the shape the locale files are generated
# in. Double-quote only, like the sibling guards; the zero-key tripwire below
# turns a change in that shape into a failure instead of a smaller scan.
_KEY_LINE = re.compile(r'^\s*"([A-Za-z0-9_.\-]+)"\s*:', re.MULTILINE)

# The opening of `t(` with a template-literal key.
_TPL_HEAD = re.compile(r"\bt\(\s*`")

# The opening of `t(` with a variable key: an identifier or property path,
# never a quoted literal (the orphan guard owns those).
_VAR_HEAD = re.compile(
    r"\bt\(\s*([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z0-9_$]+)*)\s*,\s*\{"
)

# A table entry naming its key: any `<something>Key` or `key` field holding a
# literal. Broad on purpose; the tree calls these labelKey, i18nKey, ariaKey
# and titleKey, and a guard keyed to one name would miss the next one.
_KEY_FIELD = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*[Kk]ey)\s*:\s*(['\"])([A-Za-z0-9_][A-Za-z0-9_.\-]*)\2"
)
# The English standing in for the key. `defaultLabel` is the common name but
# the tree also writes defaultName, defaultDesc, defaultText, defaultTitle and
# defaultHelp for the same job, and a guard keyed to one of them would call the
# prop class clean while its siblings went unread. `defaultValue` is excluded
# because that is the t() option itself, handled by the call-site scan above;
# pairing on it would let an unrelated key field three lines away form a
# spurious pair.
_DEFAULT_FIELD = re.compile(
    r"\b(default(?!Value\b)[A-Z][A-Za-z0-9_]*)\s*:\s*(['\"])(.*?)\2"
)

# How far above or below a defaultLabel its key field may sit. Entries are
# written on one line in this tree; the window catches the wrapped ones.
_PAIR_WINDOW = 3


@dataclass
class Sites:
    """Every computed-key call site, split by what can be decided about it."""

    template: list[tuple[str, str]] = field(default_factory=list)
    """(file, raw template source) for keys with a defaultValue."""

    headless: list[tuple[str, str]] = field(default_factory=list)
    """Templates whose interpolation comes first, leaving no prefix."""

    variable: list[tuple[str, str]] = field(default_factory=list)
    """(file, expression) for `t(expr, {defaultValue})` with a variable key."""

    pairs: list[tuple[str, int, str, str]] = field(default_factory=list)
    """(file, line, literal key, default) from a resolvable table entry."""

    unpaired: list[tuple[str, int]] = field(default_factory=list)
    """default* lines with no key field near them."""


def _close_template(text: str, start: int) -> int | None:
    """Index of the backtick closing the template literal opened at `start`.

    Walks `${...}` by depth rather than stopping at the first `}`, and recurses
    into nested templates, because a defaultValue is very often itself a
    template and a naive scan would end the key in the middle of one.
    """
    i = start + 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "`":
            return i
        if char == "$" and i + 1 < len(text) and text[i + 1] == "{":
            depth = 1
            i += 2
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                elif text[i] == "`":
                    nested = _close_template(text, i)
                    if nested is None:
                        return None
                    i = nested
                i += 1
            continue
        i += 1
    return None


def _options_body(text: str, brace_index: int) -> str | None:
    """The source between the options `{` and its matching `}`."""
    depth = 0
    for i in range(brace_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index + 1 : i]
    return None


def static_prefix(raw: str) -> str:
    """The literal head of a template key, up to its first interpolation."""
    cut = raw.find("${")
    return raw if cut < 0 else raw[:cut]


def _iter_sources(source_glob: str):
    for path in sorted(glob.glob(source_glob, recursive=True)):
        posix = path.replace(os.sep, "/")
        if "/app/locales/" in posix or ".test." in posix or ".spec." in posix:
            continue
        with open(path, encoding="utf-8") as fh:
            yield posix, fh.read()


def collect(source_glob: str) -> Sites:
    """Every computed-key call site under the glob, classified."""
    sites = Sites()
    for posix, text in _iter_sources(source_glob):
        for match in _TPL_HEAD.finditer(text):
            tick = match.end() - 1
            end = _close_template(text, tick)
            if end is None:
                continue
            raw = text[tick + 1 : end]
            rest = text[end + 1 :]
            opening = re.match(r"\s*,\s*\{", rest)
            if not opening:
                # No options object, so no defaultValue: a missing key renders
                # raw on screen, which reports itself. Out of scope, like the
                # orphan guard's own out-of-scope rule and for the same reason.
                continue
            body = _options_body(rest, opening.end() - 1)
            if body is None or "defaultValue" not in body:
                continue
            if static_prefix(raw):
                sites.template.append((posix, raw))
            else:
                sites.headless.append((posix, raw))

        for match in _VAR_HEAD.finditer(text):
            body = _options_body(text, match.end() - 1)
            if body is None or "defaultValue" not in body:
                continue
            sites.variable.append((posix, match.group(1)))

        lines = text.splitlines()
        for i, line in enumerate(lines):
            default = _DEFAULT_FIELD.search(line)
            if default is None:
                continue
            window = "\n".join(lines[max(0, i - _PAIR_WINDOW) : i + _PAIR_WINDOW + 1])
            keyfield = _KEY_FIELD.search(line) or _KEY_FIELD.search(window)
            if keyfield:
                sites.pairs.append((posix, i + 1, keyfield.group(3), default.group(3)))
            else:
                sites.unpaired.append((posix, i + 1))
    return sites


def read_en(en_path: str) -> set[str]:
    with open(en_path, encoding="utf-8") as fh:
        return set(_KEY_LINE.findall(fh.read()))


def _base_of(stem: str, by_locale: dict[str, set[str]]) -> str | None:
    """The language file a regional variant resolves through, if there is one.

    Duplicated from check_i18n_orphan_keys.py rather than imported: the two
    scripts already duplicate _options_body and _KEY_LINE for the same
    reason, one script per concern, neither depending on the other's shape.
    """
    if "-" not in stem:
        return None
    base = stem.split("-", 1)[0]
    return base if base in by_locale else None


def read_locale_keys(locale_glob: str) -> dict[str, set[str]]:
    """Map locale stem to the set of keys that locale file declares."""
    by_locale: dict[str, set[str]] = {}
    for path in sorted(glob.glob(locale_glob)):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in {"index", "types"}:
            continue
        with open(path, encoding="utf-8") as fh:
            by_locale[stem] = set(_KEY_LINE.findall(fh.read()))
    return by_locale


def _reach(key: str, by_locale: dict[str, set[str]]) -> set[str]:
    """Locales that can answer this key, bare form or any CLDR plural form."""
    forms = (key, *(key + suffix for suffix in _CLDR_SUFFIXES))
    return {stem for stem, keys in by_locale.items() if any(f in keys for f in forms)}


def missing_locales(
    key: str, by_locale: dict[str, set[str]], bases: dict[str, str | None]
) -> list[str]:
    """Locales whose reader would see this key's English default.

    A regional variant is answered by its base language, so it counts as
    covered when the base declares the key even though the variant file does
    not, the same rule the orphan guard applies to literal keys.
    """
    reach = _reach(key, by_locale)
    return sorted(
        stem for stem in by_locale if stem not in reach and bases[stem] not in reach
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--en", default=DEFAULT_EN_PATH)
    parser.add_argument("--src", default=DEFAULT_SOURCE_GLOB)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--locales", default=DEFAULT_LOCALE_GLOB)
    parser.add_argument("--member-baseline", default=DEFAULT_MEMBER_BASELINE_PATH)
    args = parser.parse_args(argv)

    try:
        keys = read_en(args.en)
    except FileNotFoundError:
        print(f"ERROR: no English bundle at {args.en!r}", file=sys.stderr)
        return 2
    if not keys:
        print(
            f"ERROR: {args.en} parsed to zero keys. The key regex is double-quote "
            "only; a file written any other way drops out of this scan silently, "
            "so an empty parse is a broken scan rather than a clean one.",
            file=sys.stderr,
        )
        return 2

    by_locale = read_locale_keys(args.locales)
    if not by_locale:
        print(f"ERROR: no files matched {args.locales!r}", file=sys.stderr)
        return 2
    empty_locales = sorted(stem for stem, ks in by_locale.items() if not ks)
    if empty_locales:
        print(
            f"ERROR: {len(empty_locales)} locale file(s) parsed to zero keys: "
            f"{', '.join(empty_locales)}. Same double-quote-only blind spot as "
            "en.ts above; an empty parse is a broken scan, not a clean one.",
            file=sys.stderr,
        )
        return 2

    sites = collect(args.src)
    if not (sites.template or sites.variable or sites.pairs or sites.headless):
        print(
            f"ERROR: no computed-key call sites found under {args.src!r}. "
            "Finding nothing and not having looked must not print the same result.",
            file=sys.stderr,
        )
        return 2

    try:
        with open(args.baseline, encoding="utf-8") as fh:
            baseline = set(json.load(fh))
    except FileNotFoundError:
        baseline = set()

    # ---- decidable: a template prefix no key in en.ts begins with ----
    where: dict[str, list[str]] = {}
    for posix, raw in sites.template:
        where.setdefault(static_prefix(raw), []).append(posix)

    empty = {
        p: files for p, files in where.items() if not any(k.startswith(p) for k in keys)
    }
    new_prefixes = sorted(set(empty) - baseline)

    # A prefix leaves the debt list for two unrelated reasons and the message has
    # to say which, because it is the instruction someone follows when editing
    # the baseline. `empty` is built from the prefixes found at call sites right
    # now, so `baseline - empty` would report a family whose last call site was
    # deleted as "answered by en.ts", which is a false statement about the locale
    # file. Ask en.ts directly for that claim, and call the other case what it is.
    answered = sorted(p for p in baseline if any(k.startswith(p) for k in keys))
    vanished = sorted(p for p in baseline - set(answered) if p not in where)

    # ---- decidable, and previously left unchecked: for a prefix en.ts DOES
    # answer, does every OTHER locale carry every one of its concrete members
    # ----
    answered_prefixes = sorted(p for p in where if p not in empty)
    bases = {stem: _base_of(stem, by_locale) for stem in by_locale}
    member_gaps: dict[str, dict[str, list[str]]] = {}  # prefix -> locale -> keys
    member_counts: dict[str, int] = {}
    for prefix in answered_prefixes:
        members = sorted(k for k in keys if k.startswith(prefix))
        member_counts[prefix] = len(members)
        for key in members:
            for stem in missing_locales(key, by_locale, bases):
                member_gaps.setdefault(prefix, {}).setdefault(stem, []).append(key)

    try:
        with open(args.member_baseline, encoding="utf-8") as fh:
            member_baseline: dict[str, dict] = json.load(fh)
    except FileNotFoundError:
        member_baseline = {}

    new_member_gaps: list[tuple[str, dict[str, list[str]]]] = []
    widened_member_gaps: list[tuple[str, dict[str, list[str]]]] = []
    for prefix, by_stem in member_gaps.items():
        entry = member_baseline.get(prefix)
        if entry is None:
            new_member_gaps.append((prefix, by_stem))
            continue
        declared = {stem: set(ks) for stem, ks in entry.get("missing", {}).items()}
        widened = {
            stem: sorted(set(ks) - declared.get(stem, set()))
            for stem, ks in by_stem.items()
        }
        widened = {stem: ks for stem, ks in widened.items() if ks}
        if widened:
            widened_member_gaps.append((prefix, widened))

    member_healed = sorted(p for p in member_baseline if p not in member_gaps)

    # ---- decidable: a table key absent from en.ts ----
    missing_pairs = [p for p in sites.pairs if p[2] not in keys]

    # ---- what could not be decided, printed rather than dropped ----
    print(
        f"computed-key scan: {len(sites.template)} template call site(s) over "
        f"{len(where)} prefix(es), {len(sites.variable)} variable-key call site(s), "
        f"{len(sites.pairs)} resolvable key/default pair(s), against "
        f"{len(keys)} keys in {args.en}"
    )
    print("\nNOT CHECKED, and no clean exit below covers any of it:")
    print(
        f"  {len(sites.variable):5d} call site(s) take their key from a variable. The key "
        "is not\n        knowable here at all unless it also appears in a table below."
    )
    for expr, n in Counter(e for _, e in sites.variable).most_common(10):
        print(f"          {n:4d}  t({expr}, {{ defaultValue ... }})")
    print(
        f"  {len(sites.headless):5d} template key(s) begin with an interpolation and so have "
        "no static prefix."
    )
    for posix, raw in sites.headless[:5]:
        print(f"          {posix}: `{raw}`")
    incomplete = sorted(set(member_gaps))
    print(
        f"  {len(where) - len(empty):5d} prefix(es) DO have members in en.ts.\n"
        f"  {len(incomplete):5d} of those have a member some other locale does "
        "not answer, checked below like a literal key."
    )
    print(
        f"  {len(sites.unpaired):5d} default* line(s) carry no key field within "
        f"{_PAIR_WINDOW} lines. Sampled and mostly\n        benign: the key is a template at the "
        "call site, already counted above."
    )
    for posix, line in sites.unpaired[:5]:
        print(f"          {posix}:{line}")

    if answered:
        print(
            f"\n{len(answered)} baselined prefix(es) now have members in en.ts; "
            f"remove them from {args.baseline}: {', '.join(answered)}"
        )
    if vanished:
        print(
            f"\n{len(vanished)} baselined prefix(es) no longer appear at any call site, so "
            "nothing renders them and they are not evidence about en.ts either way; remove "
            f"them from {args.baseline}: {', '.join(vanished)}"
        )
    if member_healed:
        shown = ", ".join(member_healed[:12])
        more = (
            f", and {len(member_healed) - 12} more" if len(member_healed) > 12 else ""
        )
        print(
            f"\n{len(member_healed)} member-baselined prefix(es) now have every member in "
            f"every locale that needs one; remove them from {args.member_baseline}: "
            f"{shown}{more}"
        )

    if (
        not new_prefixes
        and not missing_pairs
        and not new_member_gaps
        and not widened_member_gaps
    ):
        # Say how much was compared, not just that it passed. A gate that prints
        # OK without a count reads the same whether it checked everything or
        # walked an empty tree, and this repo has already had a tree walk that
        # visited zero files and exited clean.
        still_short = len(member_baseline) - len(member_healed)
        print(
            f"\ncomputed i18n keys OK: {len(where)} template prefix(es) checked, "
            f"{len(where) - len(empty)} answered by en.ts and {len(empty)} still baselined, "
            f"no new ones; {len(sites.pairs)} key/default pair(s) verified against "
            f"{len(keys)} keys in {args.en}; {len(answered_prefixes)} answered prefix(es) "
            f"checked member by member against {len(by_locale)} locales, {still_short} "
            "still short of full coverage per the member baseline, no new gaps."
        )
        return 0

    for prefix in new_prefixes:
        files = sorted(set(empty[prefix]))
        print(
            f"ERROR: no key in {args.en} begins with {prefix!r}, so every member of "
            f"that family falls back to its English default ({len(empty[prefix])} call site(s))",
            file=sys.stderr,
        )
        for name in files[:3]:
            print(f"  called from {name}", file=sys.stderr)

    for posix, line, key, default in missing_pairs:
        print(
            f"ERROR: {key} is paired with the default {default!r} but no key by that "
            f"name is in {args.en}",
            file=sys.stderr,
        )
        print(f"  declared at {posix}:{line}", file=sys.stderr)

    if new_prefixes or missing_pairs:
        print(
            "\nA key built at runtime and answered by no English bundle renders its "
            "defaultValue in every one of our languages, and the orphan guard cannot "
            "see it: its call-site regex requires a literal key, which is exactly what "
            "these call sites do not have. Add the family to en.ts and then to the other "
            "locales. Do not silence this by dropping the defaultValue, which turns a "
            f"silent English string into a raw key on screen. {args.baseline} records "
            "existing debt only and may only shrink.",
            file=sys.stderr,
        )

    for prefix, by_stem in new_member_gaps:
        key_to_missing: dict[str, list[str]] = {}
        for stem, member_keys in by_stem.items():
            for key in member_keys:
                key_to_missing.setdefault(key, []).append(stem)
        for key in sorted(key_to_missing):
            missing = sorted(key_to_missing[key])
            print(
                f"ERROR: {key} is one of {member_counts[prefix]} member(s) of "
                f"{prefix!r}, answered by {args.en}, but is answered by no locale "
                f"file it needs ({len(by_locale) - len(missing)}/{len(by_locale)})",
                file=sys.stderr,
            )
            print(f"  missing: {', '.join(missing)}", file=sys.stderr)

    for prefix, widened in widened_member_gaps:
        for stem, member_keys in widened.items():
            print(
                f"ERROR: {prefix!r} lost coverage {args.member_baseline} did not record: "
                f"{stem} no longer answers {', '.join(sorted(member_keys))}",
                file=sys.stderr,
            )

    if new_member_gaps or widened_member_gaps:
        print(
            "\nOnce en.ts answers a computed-key family, its members stop being "
            "hypothetical: they are literal dictionary entries, and every other "
            "locale owes each of them exactly as it owes a literal call-site key. "
            '"Answered" used to mean en.ts alone; a member missing from any other '
            "locale falls back to English there just as silently as an unanswered "
            f"prefix does. Add the member to the locales named above. "
            f"{args.member_baseline} records existing debt only and may only shrink.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
