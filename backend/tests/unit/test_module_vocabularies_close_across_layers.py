# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""A module's vocabulary is one list, and every layer that names it has to agree.

Several registers offer the user a closed set of words: a meeting is one of
seven types, a correspondence entry one of five kinds. Each of those sets is
declared in Python, again in TypeScript because the browser cannot import the
tuple, and again as a label in every locale file. Nothing joins the three, so
they drift, and the drift is quiet. A word in the picker that the API refuses
is a form that will not save. A word the API stores that no locale names is a
raw token printed at the reader. A word in one page's list and not the other's
is a type you can create on one screen and not the other.

The rule this file holds is not "the list contains X". It is that no layer
keeps a second copy: the Python constant is the source, the pattern is built
from it, the TypeScript union is derived from one exported array both pages
import, and every locale file that speaks the family speaks all of it. Adding a
module here is a row in the registry below, not another copy of these checks.

Behaviour that belongs to one module only, such as the meetings keyword
classifier and the prompt the model is shown, stays in that module's own test.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.modules.correspondence.schemas import CORRESPONDENCE_TYPES, CorrespondenceCreate
from app.modules.fieldreports.schemas import WEATHER_CONDITIONS, FieldReportCreate
from app.modules.meetings.schemas import MEETING_TYPES, MeetingCreate
from app.modules.submittals.schemas import SUBMITTAL_TYPES, SubmittalCreate

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend" / "app" / "modules"
FEATURES = REPO_ROOT / "frontend" / "src" / "features"
LOCALES = REPO_ROOT / "frontend" / "src" / "app" / "locales"

# Two locale files carry part of a family and are meant to. Uzbek translation
# was stopped by the founder and uz.ts is short of much else too; en-US.ts is a
# thin overlay over en.ts that carries only the words American English renders
# differently, so it holds one label out of seven by design rather than by
# neglect. Everywhere else, part of a family is the bug.
PARTIAL_BY_DESIGN = frozenset({"uz.ts", "en-US.ts"})

_A_PROJECT = "3f7c1b2e-0a4d-4c8e-9b1a-2d5e6f708192"


@dataclass(frozen=True)
class Vocabulary:
    """One closed set of words, and every place that has to know about it."""

    module: str
    field: str
    values: tuple[str, ...]
    create_schema: type[BaseModel]
    create_payload: dict[str, Any]
    feature: str
    ts_const: str
    locale_prefix: str
    descriptions: bool
    prose_keys: tuple[str, ...]
    # Words English carries that the translation pass has not reached yet.
    # A vocabulary grows in English first and the other locales follow in
    # one sweep, so between those two commits every locale legitimately
    # holds part of the family. Naming the new words here keeps the rest of
    # the family under the same check instead of dropping the module out of
    # it, and the sweep that translates them deletes the entry.
    awaiting_translation: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.module


REGISTRY = [
    Vocabulary(
        module="meetings",
        field="meeting_type",
        values=MEETING_TYPES,
        create_schema=MeetingCreate,
        create_payload={"project_id": _A_PROJECT, "title": "M", "meeting_date": "2026-09-01"},
        feature="meetings",
        ts_const="MEETING_TYPES",
        locale_prefix="meetings.type_",
        descriptions=True,
        prose_keys=("howto.meetings.how.1", "meetings.intro_more"),
    ),
    Vocabulary(
        module="correspondence",
        field="correspondence_type",
        values=CORRESPONDENCE_TYPES,
        create_schema=CorrespondenceCreate,
        create_payload={"project_id": _A_PROJECT, "direction": "incoming", "subject": "S"},
        feature="correspondence",
        ts_const="CORRESPONDENCE_TYPES",
        locale_prefix="correspondence.type_",
        descriptions=False,
        # Nine of them, which is the point. The correspondence types are
        # spelled out in the how-to, the summary, the explainer, the subtitle,
        # the info panel, both intro panels and both step captions. The list
        # was found by grepping en.ts for a sentence carrying two of the words,
        # not by remembering where the prose lives, which is the only method
        # that finds the ninth one.
        prose_keys=(
            "howto.correspondence.how.1",
            "howto.correspondence.summary",
            "howto.correspondence.what",
            "correspondence.subtitle",
            "correspondence.info_body_v2",
            "correspondence.intro_body",
            "correspondence.intro_more",
            "correspondence.how_step1_desc",
            "correspondence.how_intro",
        ),
    ),
    Vocabulary(
        module="submittals",
        field="submittal_type",
        values=SUBMITTAL_TYPES,
        create_schema=SubmittalCreate,
        create_payload={"project_id": _A_PROJECT, "title": "S"},
        feature="submittals",
        ts_const="SUBMITTAL_TYPES",
        locale_prefix="submittals.type_",
        descriptions=False,
        # Empty on purpose. Submittals names examples rather than listing the
        # vocabulary: the how-to says "shop drawing, product data, sample,
        # certificate and more", and the one sentence that did enumerate all
        # seven stopped doing so when the eighth type arrived, which is the
        # standing rule. A hedged list does not go stale, so there is nothing
        # here to hold in step.
        prose_keys=(),
    ),
    Vocabulary(
        module="fieldreports",
        field="weather_condition",
        values=WEATHER_CONDITIONS,
        create_schema=FieldReportCreate,
        create_payload={"project_id": _A_PROJECT, "report_date": "2026-01-05"},
        feature="fieldreports",
        ts_const="WEATHER_CONDITIONS",
        locale_prefix="fieldreports.weather_",
        descriptions=False,
        # Empty on purpose. The package docstring and the manifest line name
        # the subject, "weather", without listing the conditions under it,
        # which is the spelling that cannot go stale.
        prose_keys=(),
    ),
]

_ids = [v.module for v in REGISTRY]


def _named_in_prose(text: str, values: tuple[str, ...]) -> list[str]:
    """Which of the values a sentence names, allowing plurals and prose spelling.

    A vocabulary word is snake_case in the code and ordinary English in a
    sentence, so ``shop_drawing`` has to match "shop drawings" and ``mock_up``
    has to match "mock-ups".
    """
    haystack = re.sub(r"[-_\s]+", " ", text.lower())
    return [v for v in values if re.search(_surface_forms(v), haystack)]


def _surface_forms(value: str) -> str:
    """The shapes one vocabulary word takes in an English sentence.

    The word boundaries carry this check. Without them "report" is found inside
    "reported" and "design" inside "designated", so a sentence passes for a
    word it never names. The -y plural is spelled out separately because
    "warranty" reaches the reader as "warranties" and nothing else matches it.
    """
    forms = [re.escape(value.replace("_", " ")) + "s?"]
    if value.endswith("y"):
        forms.append(re.escape(value[:-1].replace("_", " ")) + "ies")
    return r"\b(?:" + "|".join(forms) + r")\b"


def _sentences_in_namespace(text: str, module: str) -> dict[str, str]:
    """Every en.ts string belonging to a module, keyed by its full key name."""
    pattern = re.compile(rf'"((?:howto\.)?{re.escape(module)}\.[a-z0-9_.]+)"\s*:\s*"(.*?)(?<!\\)",\n', re.S)
    return {match.group(1): match.group(2) for match in pattern.finditer(text)}


def _locale_families(prefix: str) -> dict[str, tuple[set[str], set[str]]]:
    """Per locale file, the label names and the description names it declares."""
    key = re.compile(rf'"{re.escape(prefix)}([a-z0-9_]+)"\s*:')
    families: dict[str, tuple[set[str], set[str]]] = {}
    for path in sorted(LOCALES.glob("*.ts")):
        names = set(key.findall(path.read_text(encoding="utf-8")))
        labels = {n for n in names if not n.endswith("_desc")}
        descriptions = {n[: -len("_desc")] for n in names if n.endswith("_desc")}
        families[path.name] = (labels, descriptions)
    return families


def test_the_paths_are_where_this_file_thinks_they_are():
    """Guarding the guard: a wrong root would make every check below vacuous."""
    assert BACKEND.is_dir() and FEATURES.is_dir() and LOCALES.is_dir()
    assert len(list(LOCALES.glob("*.ts"))) > 30


class TestThePythonSide:
    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_the_set_has_no_repeats_and_no_blank_words(self, vocab: Vocabulary):
        assert len(set(vocab.values)) == len(vocab.values)
        assert all(v and v.strip() == v for v in vocab.values)

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_the_create_schema_takes_every_word_and_refuses_an_invented_one(self, vocab: Vocabulary):
        for value in vocab.values:
            assert vocab.create_schema(**vocab.create_payload, **{vocab.field: value})
        # Without this the loop above would pass against a pattern of `.*`.
        with pytest.raises(ValidationError):
            vocab.create_schema(**vocab.create_payload, **{vocab.field: "not_a_real_kind"})

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_every_schema_that_constrains_the_field_states_the_same_words(self, vocab: Vocabulary):
        """A sibling schema that kept an older pattern is the classic drift.

        The create schema is the one people remember. The update schema and,
        where there is one, the series or bulk schema are the ones that quietly
        keep yesterday's list, and the failure only shows when somebody edits a
        record instead of creating one.
        """
        import importlib

        module = importlib.import_module(f"app.modules.{vocab.module}.schemas")
        seen: dict[str, set[str]] = {}
        for name in dir(module):
            attr = getattr(module, name)
            fields = getattr(attr, "model_fields", None)
            if not isinstance(fields, dict) or vocab.field not in fields:
                continue
            for meta in getattr(fields[vocab.field], "metadata", []) or []:
                pattern = getattr(meta, "pattern", None)
                if isinstance(pattern, str):
                    seen[name] = set(re.fullmatch(r"\^\((.+)\)\$", pattern).group(1).split("|"))
        assert seen, f"no schema in {vocab.module} constrains {vocab.field}, so this check measures nothing"
        wrong = {name: sorted(words) for name, words in seen.items() if words != set(vocab.values)}
        assert wrong == {}, f"these schemas state a different vocabulary from the constant: {wrong}"

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_a_module_that_lists_its_types_in_prose_lists_all_of_them(self, vocab: Vocabulary):
        """The package docstring and the manifest description are the catalogue entry.

        Naming no types is fine, and naming one as an example is fine. Naming
        some of them is the bug: the correspondence manifest offered "letters,
        emails, notices" for as long as the module existed, which is the line a
        reader sees in the module catalogue, and it was already two words short
        before this change added a third. A partial list reads as a complete
        one, so it is worse than no list at all.
        """
        import importlib

        package = importlib.import_module(f"app.modules.{vocab.module}")
        manifest = importlib.import_module(f"app.modules.{vocab.module}.manifest").manifest
        texts = {"the package docstring": package.__doc__ or "", "the manifest description": manifest.description}
        assert all(texts.values()), f"{vocab.module} has an empty docstring or description, so this check reads nothing"
        for where, text in texts.items():
            named = _named_in_prose(text, vocab.values)
            if len(named) < 2:
                continue
            missing = [v for v in vocab.values if v not in named]
            assert missing == [], f"{where} of {vocab.module} lists types and leaves out {missing}"

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_nobody_writes_the_alternation_out_by_hand(self, vocab: Vocabulary):
        """Two of the words beside each other joined by a pipe is a second copy.

        This is the check that actually holds the shape, because a hand written
        alternation is correct on the day it is written and is the copy the
        next addition will miss.
        """
        pair = re.compile("|".join(rf"{a}\|{b}" for a in vocab.values for b in vocab.values if a != b))
        offenders = sorted(
            path.name for path in (BACKEND / vocab.module).glob("*.py") if pair.search(path.read_text(encoding="utf-8"))
        )
        assert offenders == [], f"these spell the vocabulary out instead of building it: {offenders}"

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_no_second_collection_of_the_words_either(self, vocab: Vocabulary):
        """An alternation is one shape a copy takes and a bare collection is the other.

        The field reports CSV import held ``{"clear", "cloudy", "rain", ...}``
        beside the schema's own list and rewrote anything it did not recognise
        to "clear", so an import naming a real condition lost it with nothing
        printed anywhere. There is no pipe in that line, so the check above
        cannot see it. The vocabulary's own definition is excused once, by
        being the first literal that states it exactly; a second one is a copy.
        """
        import ast

        excused = False
        offenders: dict[str, list[str]] = {}
        for path in sorted((BACKEND / vocab.module).glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Set | ast.List | ast.Tuple):
                    continue
                words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if tuple(words) == tuple(vocab.values) and not excused:
                    excused = True
                    continue
                shared = set(words) & set(vocab.values)
                if len(shared) >= 2:
                    offenders.setdefault(path.name, []).extend(sorted(shared))
        assert excused, f"{vocab.module} no longer states {vocab.field} as one literal, so this check is adrift"
        assert offenders == {}, f"these keep a second collection of the words: {offenders}"


class TestTheTypeScriptSide:
    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_the_exported_array_matches_the_python_tuple_in_order(self, vocab: Vocabulary):
        """Order matters: it is the order every picker shows."""
        source = (FEATURES / vocab.feature / "api.ts").read_text(encoding="utf-8")
        block = re.search(rf"export const {vocab.ts_const} = \[(.*?)\] as const;", source, re.S)
        assert block, f"{vocab.feature}/api.ts no longer exports {vocab.ts_const} as a const array"
        assert tuple(re.findall(r"'([a-z0-9_]+)'", block.group(1))) == tuple(vocab.values)

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_no_page_keeps_its_own_copy_of_the_list(self, vocab: Vocabulary):
        """Pages used to hold a list each, so a word could reach one and not the other."""
        own = re.compile(rf"\bconst {vocab.ts_const}\b|\bconst [A-Z_]*TYPES(_LIST)? *: *[A-Za-z]+\[\] *= *\[")
        offenders = sorted(
            path.name
            for path in (FEATURES / vocab.feature).glob("*.ts*")
            if path.name != "api.ts" and own.search(path.read_text(encoding="utf-8"))
        )
        assert offenders == [], f"these declare their own list instead of importing it: {offenders}"


class TestTheLocaleSide:
    """English is held strictly, the other locales only to their own consistency.

    A label with no key renders under the English fallback in every language,
    which looks like a translation nobody got round to and is really a key that
    exists nowhere. The correspondence register shipped four such words to
    every reader for as long as it existed, and the only way to see that is to
    open the files rather than the screens.

    English is where a new word lands and the translation pass follows behind
    it, so a check demanding all forty two files carry the word would be red
    for the length of that gap on every single addition, and a gate that is red
    by design is a gate somebody switches off. What holds instead is that
    English carries every word, and that a file carrying part of a family
    carries all of it. None of the family means the pass has not reached the
    file yet, which is ordinary; three words out of five means a picker
    offering two words nobody translated.
    """

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_english_carries_every_word(self, vocab: Vocabulary):
        labels, descriptions = _locale_families(vocab.locale_prefix)["en.ts"]
        assert labels >= set(vocab.values)
        if vocab.descriptions:
            assert descriptions >= set(vocab.values)

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_a_locale_speaks_all_of_the_family_or_none_of_it(self, vocab: Vocabulary):
        # Narrowed to the vocabulary's own words, because a prefix also
        # matches keys that are not labels at all: `fieldreports.weather_`
        # catches `weather_filled` and `weather_unavailable`, which every
        # locale carries, and without this no file could ever read as "the
        # pass has not reached here yet" however little of the family it has.
        words = set(vocab.values)
        started = {
            name: labels & words
            for name, (labels, _) in _locale_families(vocab.locale_prefix).items()
            if labels & words and name not in PARTIAL_BY_DESIGN
        }
        assert started, f"no locale carries any of {vocab.module}, so this check measures nothing"
        required = words - set(vocab.awaiting_translation)
        incomplete = {name: sorted(required - labels) for name, labels in started.items() if not labels >= required}
        assert incomplete == {}, f"these locales offer some of {vocab.module} and not the rest: {incomplete}"

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_a_word_waiting_for_translation_is_really_waiting(self, vocab: Vocabulary):
        """An exception has to read as an inclusion backwards, or it never expires.

        ``awaiting_translation`` excuses a word from the check above, which
        makes it the one place a word can be parked and forgotten. Two claims
        keep it honest: the word has to belong to the vocabulary and be in
        English already, and it stops being excused the moment every locale
        carries it.
        """
        if not vocab.awaiting_translation:
            pytest.skip(f"{vocab.module} has no words waiting for the translation pass")
        families = _locale_families(vocab.locale_prefix)
        pending = set(vocab.awaiting_translation)
        assert pending <= set(vocab.values), f"{sorted(pending - set(vocab.values))} is not one of {vocab.module}"
        assert pending <= families["en.ts"][0], f"{sorted(pending - families['en.ts'][0])} is not in English either"
        elsewhere = [
            labels for name, (labels, _) in families.items() if name not in PARTIAL_BY_DESIGN and name != "en.ts"
        ]
        landed = sorted(word for word in pending if all(word in labels for labels in elsewhere))
        assert landed == [], (
            f"every locale now carries {landed}, so drop them from {vocab.module}'s "
            "awaiting_translation and let the check hold the whole family again"
        )

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_a_label_never_ships_without_its_description(self, vocab: Vocabulary):
        """Where a module has descriptions, half a pair is a card with a blank line."""
        if not vocab.descriptions:
            pytest.skip(f"{vocab.module} labels its values without a description")
        lopsided = {
            name: sorted(labels ^ descriptions)
            for name, (labels, descriptions) in _locale_families(vocab.locale_prefix).items()
            if labels != descriptions
        }
        assert lopsided == {}, f"these have a label and no description, or the reverse: {lopsided}"

    @pytest.mark.parametrize("vocab", REGISTRY, ids=_ids)
    def test_the_english_help_text_names_every_word_the_picker_offers(self, vocab: Vocabulary):
        """Help text is prose, and prose goes stale without anything failing.

        These sentences list the values by name, and they are also what the
        forty translations are written from, so English drifting here drifts
        everywhere on the next translation pass.
        """
        text = (LOCALES / "en.ts").read_text(encoding="utf-8")
        if not vocab.prose_keys:
            sentences = _sentences_in_namespace(text, vocab.locale_prefix.split(".")[0])
            assert sentences, f"no {vocab.module} strings found in en.ts, so this check measures nothing"
            listed = sorted(
                key
                for key, sentence in sentences.items()
                if not set(vocab.values) - set(_named_in_prose(sentence, vocab.values))
            )
            assert listed == [], (
                f"{vocab.module} is registered as naming examples, but these now name the whole "
                f"vocabulary and will go stale on the next type: {listed}"
            )
            return
        for key in vocab.prose_keys:
            sentence = re.search(rf'"{re.escape(key)}"\s*:\s*"(.*?)(?<!\\)",\n', text, re.S)
            assert sentence, f"{key} is gone from en.ts"
            missing = [v for v in vocab.values if v not in sentence.group(1).lower()]
            assert missing == [], f"{key} does not mention {missing}"
