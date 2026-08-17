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
    the entire family is unanswerable. That is the check. It cannot prove
    the opposite: a populated prefix may still be missing individual members,
    and this guard says nothing about those. Reported as such rather than
    counted as coverage.

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--en", default=DEFAULT_EN_PATH)
    parser.add_argument("--src", default=DEFAULT_SOURCE_GLOB)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH)
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
    print(
        f"  {len(where) - len(empty):5d} prefix(es) DO have members in en.ts. This guard says "
        "nothing about\n        whether every member of those families is present, only that the "
        "family is."
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

    if not new_prefixes and not missing_pairs:
        # Say how much was compared, not just that it passed. A gate that prints
        # OK without a count reads the same whether it checked everything or
        # walked an empty tree, and this repo has already had a tree walk that
        # visited zero files and exited clean.
        print(
            f"\ncomputed i18n keys OK: {len(where)} template prefix(es) checked, "
            f"{len(where) - len(empty)} answered by en.ts and {len(empty)} still baselined, "
            f"no new ones; {len(sites.pairs)} key/default pair(s) verified against "
            f"{len(keys)} keys in {args.en}."
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
