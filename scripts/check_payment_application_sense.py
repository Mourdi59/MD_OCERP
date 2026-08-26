#!/usr/bin/env python3
"""A payment application is a claim for money, never a piece of software.

On the subcontractor payment portal and the cost value reconciliation screen,
the English word "application" means a formal claim for work done in a period,
the same sense as applying for planning permission. This product has no
software-application meaning: all fifty three English strings containing the
word are the claim sense.

Fifteen locales had translated it as a phone app anyway. Spanish said
"Aplicaciones de pago", French "Applications de paiement", Croatian "Primjene
placanja", Urdu left the English word inside the Urdu. In three languages the
whole payment portal read that way, and Bengali managed to use the correct
native word in five keys and a transliterated loanword in seven others, so one
namespace disagreed with itself.

This exists because that class of fix does not stay fixed. A later batch pass
translating the English word out of context reintroduces it, and nothing
notices: the key is present, the value is not empty, it is not the English
string, and it is in the right script. Every check we run passes on a fluent
wrong noun.

Deliberately narrow. It does not try to judge translations in general, and it
does not guess at which word each language should use. It watches an enumerated
set of keys for one specific family of roots, which is why it cannot produce a
false positive on a language it does not know: if a key is not in the list it is
not examined at all.

`payportal.back_to_app` is excluded by name. It means go back to this product,
which really is the software, and it is the one string on that screen where the
app reading is correct. A sweep that went by the word rather than the meaning
would have broken it.
"""

from __future__ import annotations

import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = os.path.join(REPO, "frontend", "src", "app", "locales")
Q = '"'

# Roots meaning a software application, or "a use of", in the languages we ship.
# English is not among them: "Payment applications" is the correct English.
APP_ROOTS = (
    "aplicac",
    "aplicaç",
    "aplikac",
    "aplikas",
    "aplicaci",
    "applicaz",
    "anwendung",
    "toepassing",
    "primjen",
    "приложен",
    "аппликац",
    "تطبيق",
    "অ্যাপ্লিকেশন",
    "แอปพลิเคชัน",
    "アプリ",
    "应用程序",
    "앱",
)

# Keys whose English is the payment-claim sense. back_to_app is NOT here.
GUARDED = (
    "cvr.payment_applications",
    "payportal.title",
    "payportal.subtitle",
    "payportal.empty_title",
    "payportal.empty_desc",
    "payportal.load_failed",
    "payportal.form_title",
    "payportal.submitted_ok",
    "payportal.new_application",
    "payportal.app_number",
    "payportal.submit",
    "payportal.submit_failed",
    "payportal.back_to_list",
    "payportal.detail_title",
)

EXCLUDED_BY_DESIGN = ("payportal.back_to_app",)


def value(text: str, key: str) -> str | None:
    m = re.search(Q + re.escape(key) + Q + r"\s*:\s*" + Q + r'([^"]*)' + Q, text)
    return m.group(1) if m else None


def check(locales_dir: str) -> list[str]:
    problems: list[str] = []
    for name in sorted(os.listdir(locales_dir)):
        if not name.endswith(".ts") or name in ("en.ts", "en-US.ts"):
            continue
        loc = name[:-3]
        text = io.open(
            os.path.join(locales_dir, name), encoding="utf-8", errors="replace"
        ).read()
        for key in GUARDED:
            v = value(text, key)
            if not v:
                continue
            hit = next((r for r in APP_ROOTS if r in v.lower()), None)
            if hit:
                problems.append(f"{loc}: {key} = {v}    (contains {hit!r})")
    return problems


def selftest() -> int:
    """Prove it fires, on the exact string that shipped before the fix."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        io.open(os.path.join(tmp, "xx.ts"), "w", encoding="utf-8").write(
            '  "cvr.payment_applications": "Aplicaciones de pago",\n'
            '  "payportal.back_to_app": "Volver a la aplicacion",\n'
        )
        found = check(tmp)
        if len(found) != 1 or "cvr.payment_applications" not in found[0]:
            print("selftest FAILED: expected exactly the cvr key, got:", found)
            return 1
        # The excluded key must not be reported even though it carries the root.
        if any("back_to_app" in f for f in found):
            print("selftest FAILED: reported the key that is correct by design")
            return 1
        io.open(os.path.join(tmp, "xx.ts"), "w", encoding="utf-8").write(
            '  "cvr.payment_applications": "Solicitudes de pago",\n'
        )
        if check(tmp):
            print("selftest FAILED: still reporting after the value was corrected")
            return 1
    print(
        "selftest ok: fires on the shipped defect, ignores back_to_app, "
        "goes quiet once corrected"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    problems = check(LOCALES)
    if not problems:
        print(
            f"All {len(GUARDED)} payment application strings read as a claim for "
            f"money, in every locale that defines them."
        )
        return 0
    print(f"{len(problems)} payment application strings read as software:\n")
    for line in problems:
        print("  " + line)
    print(
        "\nThe word here means a claim for work done, not an app. Each of these "
        "files already carries the right noun on the payment portal.\n"
        f"Correct by design and never reported: {', '.join(EXCLUDED_BY_DESIGN)}."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
