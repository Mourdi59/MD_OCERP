# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""A meeting type is one word, and every layer has to be saying it.

The meetings vocabulary used to be typed out in eight places: three Pydantic
patterns, two membership checks in the router, the prompt the model is shown,
and a list of the same six words in each of the two frontend files that render
a picker. Every copy was correct on the day it was written, which is exactly
what makes this shape dangerous - a seventh type reaches one copy and not the
others, and the result is not a crash but a quiet disagreement. The dropdown
offers a type the API rejects, or the API stores a type the screen has no word
for and prints the raw token instead.

So the checks here are not "does the list contain commercial". They are:
nobody keeps a second copy, every type survives the whole round trip from
picker to database to label, and the layers that cannot import the tuple - the
TypeScript union and forty locale files - still say the same thing as the tuple.

A failure here is usually not a bug in the layer that failed. It is a type that
was added to one layer and not to this one.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.meetings.router import _AI_MEETING_PROMPT, _infer_meeting_type
from app.modules.meetings.schemas import (
    MEETING_TYPES,
    MeetingCreate,
    MeetingSeriesCreate,
    MeetingUpdate,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MEETINGS_MODULE = REPO_ROOT / "backend" / "app" / "modules" / "meetings"
MEETINGS_FEATURE = REPO_ROOT / "frontend" / "src" / "features" / "meetings"
LOCALES = REPO_ROOT / "frontend" / "src" / "app" / "locales"

# A project id and a date, because the schemas want a whole meeting before they
# will tell us anything about one field.
_A_PROJECT = "3f7c1b2e-0a4d-4c8e-9b1a-2d5e6f708192"
_A_DATE = "2026-09-01"

# One transcript fragment per type, so that adding a type to the tuple and
# leaving the classifier alone fails here rather than shipping a type the
# import path can never produce. The fragments are deliberately short and
# ordinary; they are not tuned to pass.
_TRANSCRIPT_BY_TYPE: dict[str, str] = {
    "safety": "Toolbox talk on the scaffold edge protection, one near miss reported this week.",
    "design": "Design review of the revised stair detail, architect to reissue the drawing.",
    "subcontractor": "Trade coordination with the cladding subcontractor over their scope of work.",
    "kickoff": "Project kickoff, mobilization dates and site setup agreed with all parties.",
    "closeout": "Closeout walk, the punch list is down to nine items before handover.",
    "commercial": "Interim valuation number seven, the payment application and retention release.",
    "progress": "Weekly site walk, the slab pour is on programme and the crane arrives Monday.",
}


class TestTheVocabularyItself:
    def test_the_tuple_has_no_repeats_and_no_empty_words(self):
        assert len(set(MEETING_TYPES)) == len(MEETING_TYPES)
        assert all(t and t.strip() == t for t in MEETING_TYPES)

    @pytest.mark.parametrize("meeting_type", MEETING_TYPES)
    def test_every_type_survives_the_schemas_that_gate_the_write(self, meeting_type: str):
        """Create, update and series all have to accept it, not just create.

        The series schema is the one that gets forgotten, because a recurring
        meeting is created through a different endpoint and a pattern that
        drifted there only shows up when somebody schedules a standing meeting
        of the new kind.
        """
        assert MeetingCreate(project_id=_A_PROJECT, meeting_type=meeting_type, title="M", meeting_date=_A_DATE)
        assert MeetingUpdate(meeting_type=meeting_type)
        assert MeetingSeriesCreate(
            project_id=_A_PROJECT,
            meeting_type=meeting_type,
            title="M",
            meeting_date=_A_DATE,
            recurrence_rule="FREQ=WEEKLY",
        )

    def test_a_word_that_is_not_in_the_tuple_is_refused(self):
        """Without this the parametrised test above would pass on a pattern of `.*`."""
        with pytest.raises(ValidationError):
            MeetingCreate(project_id=_A_PROJECT, meeting_type="cost_review", title="M", meeting_date=_A_DATE)

    def test_nobody_keeps_a_second_copy_of_the_alternation(self):
        """The pattern is built from the tuple, so the words never appear joined by a pipe.

        This is the check that actually holds the shape. Two of these words
        beside each other separated by a pipe means somebody wrote the
        alternation out by hand again, and that copy is the one a later
        addition will miss.
        """
        pair = re.compile("|".join(rf"{a}\|{b}" for a in MEETING_TYPES for b in MEETING_TYPES if a != b))
        offenders = sorted(p.name for p in MEETINGS_MODULE.glob("*.py") if pair.search(p.read_text(encoding="utf-8")))
        assert offenders == [], f"these spell the vocabulary out instead of building it from MEETING_TYPES: {offenders}"


class TestTheImportPath:
    def test_the_keyword_classifier_can_reach_every_type(self):
        """A type the guesser can never return is one the import path cannot offer."""
        assert set(_TRANSCRIPT_BY_TYPE) == set(MEETING_TYPES), (
            "a type was added without a transcript fragment here, so nothing proves "
            "_infer_meeting_type can ever return it"
        )
        for meeting_type, transcript in _TRANSCRIPT_BY_TYPE.items():
            assert _infer_meeting_type(transcript) == meeting_type

    def test_an_unremarkable_transcript_still_lands_on_progress(self):
        assert _infer_meeting_type("Attendance taken, minutes of the last meeting agreed.") == "progress"

    def test_the_model_is_shown_the_whole_vocabulary(self):
        """The model can only answer with a type it was told about."""
        assert "__MEETING_TYPES__" not in _AI_MEETING_PROMPT, "the placeholder was never substituted"
        for meeting_type in MEETING_TYPES:
            assert meeting_type in _AI_MEETING_PROMPT


class TestTheFrontendSaysTheSame:
    def _api_ts(self) -> str:
        return (MEETINGS_FEATURE / "api.ts").read_text(encoding="utf-8")

    def test_the_typescript_list_matches_the_python_tuple_in_order(self):
        """Order matters: it is the order the pickers show, and the two must not drift."""
        block = re.search(r"export const MEETING_TYPES = \[(.*?)\] as const;", self._api_ts(), re.S)
        assert block, "api.ts no longer exports MEETING_TYPES as a const array"
        declared = tuple(re.findall(r"'([a-z_]+)'", block.group(1)))
        assert declared == tuple(MEETING_TYPES)

    def test_no_page_keeps_its_own_copy_of_the_list(self):
        """Two pickers used to hold two lists, so a type could reach one and not the other."""
        offenders = sorted(
            p.name
            for p in MEETINGS_FEATURE.glob("*.ts*")
            if p.name != "api.ts" and re.search(r"\bconst MEETING_TYPES\b", p.read_text(encoding="utf-8"))
        )
        assert offenders == [], f"these declare their own meeting type list instead of importing it: {offenders}"


class TestTheLocalesSayTheSame:
    """English fallback hides a missing key, so count files rather than screens.

    A type with no label renders under the English fallback in every language,
    which looks like a translation nobody got round to and is really a key that
    exists nowhere. The only way to see it is to open the files.
    """

    _KEY = re.compile(r'"meetings\.type_([a-z_]+)"\s*:')

    # Two files are short of the family on purpose. ``uz.ts`` is short of this
    # and much else because Uzbek translation was stopped deliberately, and
    # ``en-US.ts`` is an overlay over ``en.ts`` that only carries the words
    # American English renders differently, so a partial family is exactly what
    # it should hold. The set is closed and asserted below, so a third file
    # losing the family fails rather than joining a list of exceptions.
    _PARTIAL_BY_DESIGN = {"uz.ts", "en-US.ts"}

    def _families(self) -> dict[str, tuple[set[str], set[str]]]:
        found: dict[str, tuple[set[str], set[str]]] = {}
        for path in sorted(LOCALES.glob("*.ts")):
            names = set(self._KEY.findall(path.read_text(encoding="utf-8")))
            labels = {n for n in names if not n.endswith("_desc")}
            descriptions = {n[: -len("_desc")] for n in names if n.endswith("_desc")}
            found[path.name] = (labels, descriptions)
        return found

    def test_the_locale_directory_is_where_this_test_thinks_it_is(self):
        """Guarding the guard: a wrong path would make every check below vacuous."""
        assert LOCALES.is_dir() and MEETINGS_FEATURE.is_dir()
        assert len(list(LOCALES.glob("*.ts"))) > 30

    def test_english_carries_a_label_and_a_description_for_every_type(self):
        labels, descriptions = self._families()["en.ts"]
        assert labels >= set(MEETING_TYPES)
        assert descriptions >= set(MEETING_TYPES)

    def test_every_locale_that_speaks_the_family_speaks_all_of_it(self):
        incomplete = {
            name: sorted(set(MEETING_TYPES) - labels)
            for name, (labels, _) in self._families().items()
            if name not in self._PARTIAL_BY_DESIGN and not labels >= set(MEETING_TYPES)
        }
        assert incomplete == {}, f"these locales offer some meeting types and not others: {incomplete}"

    def test_a_label_never_ships_without_its_description(self):
        """The picker shows both, so half a pair is a card with a blank line under it."""
        lopsided = {
            name: sorted(labels ^ descriptions)
            for name, (labels, descriptions) in self._families().items()
            if labels != descriptions
        }
        assert lopsided == {}, f"these locales have a label and no description, or the reverse: {lopsided}"

    def test_the_files_that_do_not_carry_the_family_are_the_ones_we_know_about(self):
        """A closed set, so a locale quietly losing the family fails here."""
        without = {name for name, (labels, _) in self._families().items() if not labels >= set(MEETING_TYPES)}
        assert without == self._PARTIAL_BY_DESIGN

    def test_the_english_help_text_names_every_type_the_picker_offers(self):
        """The help text is prose, and prose goes stale without anything failing.

        Both of these sentences list the types by name. They are also what the
        forty translations are written from, so English drifting here drifts
        everywhere on the next translation pass.
        """
        text = (LOCALES / "en.ts").read_text(encoding="utf-8")
        for key in ("howto.meetings.how.1", "meetings.intro_more"):
            sentence = re.search(rf'"{re.escape(key)}"\s*:\s*"(.*?)(?<!\\)",\n', text, re.S)
            assert sentence, f"{key} is gone from en.ts"
            missing = [t for t in MEETING_TYPES if t not in sentence.group(1).lower()]
            assert missing == [], f"{key} does not mention {missing}"
