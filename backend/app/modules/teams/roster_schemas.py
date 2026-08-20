# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""API schemas for the project roster.

The roster answers "who is on this job" the way a site manager would: a name, a
firm, a trade, a role, the dates they are here, the share of their time we have
been promised, and the tickets that have to be in date for them to work. A
roster line grants nothing - see :mod:`app.modules.teams.models` for why that is
kept separate from team membership.

Three kinds of person share one shape
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A line links to a platform user, or to an address-book contact, or to neither.
``source`` on the response says which, so the UI can offer "assign work to them"
only where that is possible, and ``display_name`` is always present so no line
ever renders as an id.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.teams.roster_vocab import (
    ROSTER_TRADES,
    SITE_ROLES,
    is_known_site_role,
    is_known_trade,
)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: Nobody is on a job for a century, and an open-ended row is expressed by
#: leaving the date empty rather than by typing a far-future one. The bound
#: stops a fat-fingered year turning into a permanent "still on site" line.
MAX_ROSTER_YEARS = 25


def _clean(value: str, field: str) -> str:
    """Strip a free-text value and reject control-character junk.

    Mirrors ``schemas._reject_unsafe_string``: the message embeds a stable
    ``teams.validation.*`` key so the frontend can localise a 422 without
    parsing the English half.
    """
    if _CONTROL_CHAR_RE.search(value):
        raise ValueError(f"[teams.validation.{field}.control_characters] {field} contains control characters")
    return value.strip()


class CertificationEntry(BaseModel):
    """One ticket or competency held by a person on the roster.

    ``kind`` is free text on purpose. The card that lets somebody onto site is
    named differently in every jurisdiction, and a closed list would either be
    wrong outside the countries we thought of or grow into a catalogue nobody
    maintains. ``valid_until`` is the field that has to be machine-readable,
    because that is the one a rule checks.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    kind: str = Field(..., min_length=1, max_length=120)
    number: str = Field(default="", max_length=120)
    issued_by: str = Field(default="", max_length=255)
    valid_until: date | None = None

    @field_validator("kind", "number", "issued_by")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return _clean(v, "certification")

    def is_expired(self, on: date) -> bool:
        """True when this ticket had already run out on ``on``."""
        return self.valid_until is not None and self.valid_until < on


class RosterMemberBase(BaseModel):
    """Fields shared by the create and update shapes."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    team_id: UUID | None = None
    company_name: str = Field(default="", max_length=255)
    trade: str = Field(default="", max_length=32)
    site_role: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=50)
    starts_on: date | None = None
    ends_on: date | None = None
    allocation_percent: int | None = Field(default=None, ge=0, le=100)
    certifications: list[CertificationEntry] = Field(default_factory=list, max_length=40)
    resource_id: UUID | None = None
    notes: str = Field(default="", max_length=2000)

    @field_validator("company_name", "email", "phone", "notes")
    @classmethod
    def _sanitize_text(cls, v: str) -> str:
        return _clean(v, "roster")

    @field_validator("trade")
    @classmethod
    def _known_trade(cls, v: str) -> str:
        value = v.strip()
        if not is_known_trade(value):
            raise ValueError(f"[teams.validation.trade.unknown] '{value}' is not a trade this platform records")
        return value

    @field_validator("site_role")
    @classmethod
    def _known_site_role(cls, v: str) -> str:
        value = v.strip()
        if not is_known_site_role(value):
            raise ValueError(f"[teams.validation.site_role.unknown] '{value}' is not a site role this platform records")
        return value

    @model_validator(mode="after")
    def _dates_agree(self) -> RosterMemberBase:
        """An end before the start describes nobody, and a 25-year stay is a typo."""
        if self.starts_on and self.ends_on:
            if self.ends_on < self.starts_on:
                raise ValueError("[teams.validation.roster.window_reversed] The end date falls before the start date")
            if (self.ends_on - self.starts_on).days > MAX_ROSTER_YEARS * 366:
                raise ValueError(
                    f"[teams.validation.roster.window_too_long] "
                    f"A roster line cannot span more than {MAX_ROSTER_YEARS} years"
                )
        return self


class RosterMemberCreate(RosterMemberBase):
    """Put one person on the project roster.

    Give a ``user_id``, or a ``contact_id``, or neither with a
    ``display_name``. The service fills the name (and the firm, and the contact
    details) from the linked row when it can, so the common path is picking
    somebody the platform already knows rather than retyping them.
    """

    user_id: UUID | None = None
    contact_id: UUID | None = None
    display_name: str = Field(default="", max_length=255)
    #: Also give this person access to the project. Only meaningful for a
    #: platform user, and only honoured for a caller who may change project
    #: access - the roster itself grants nothing.
    grant_project_access: bool = False
    #: The team role to use when ``grant_project_access`` is set.
    access_role: str = Field(default="member", max_length=50)

    @field_validator("display_name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return _clean(v, "display_name")

    @model_validator(mode="after")
    def _one_link_at_most(self) -> RosterMemberCreate:
        if self.user_id is not None and self.contact_id is not None:
            raise ValueError("[teams.validation.roster.two_links] A roster line names a user or a contact, not both")
        if self.user_id is None and self.contact_id is None and not self.display_name:
            raise ValueError("[teams.validation.roster.no_name] Pick somebody the platform knows, or type a name")
        return self


class RosterBulkCreate(BaseModel):
    """Add several people to the roster in one call.

    The "add people" drawer is a multi-select, so the whole selection lands as
    one request and one refresh. Bounded at 100 because a project roster is a
    site, not an import.
    """

    model_config = ConfigDict(extra="ignore")

    members: list[RosterMemberCreate] = Field(min_length=1, max_length=100)


class RosterMemberUpdate(RosterMemberBase):
    """Change one roster line. Only the fields present in the request are written."""

    display_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    # The base class defaults every field, so an update has to be read through
    # ``model_fields_set`` rather than by testing for None - otherwise clearing
    # a date and never mentioning it would be the same request.
    @field_validator("display_name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = _clean(v, "display_name")
        if not cleaned:
            raise ValueError("[teams.validation.display_name.blank] display_name must not be blank")
        return cleaned

    def assigned_fields(self) -> dict[str, Any]:
        """The columns this update actually names, ready to write."""
        payload: dict[str, Any] = {}
        for name in self.model_fields_set:
            if name not in _UPDATABLE_FIELDS:
                continue
            value = getattr(self, name)
            payload[name] = [c.model_dump(mode="json") for c in value] if name == "certifications" else value
        return payload


_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "team_id",
        "display_name",
        "company_name",
        "trade",
        "site_role",
        "email",
        "phone",
        "starts_on",
        "ends_on",
        "allocation_percent",
        "certifications",
        "resource_id",
        "notes",
        "is_active",
    }
)


class CertificationState(CertificationEntry):
    """A ticket as read back, with the one thing a reader needs precomputed."""

    expired: bool = False
    #: Days until expiry; negative once it has passed, null when open-ended.
    days_remaining: int | None = None


class RosterMemberResponse(BaseModel):
    """One roster line, resolved for display."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    team_id: UUID | None = None
    team_name: str = ""
    user_id: UUID | None = None
    contact_id: UUID | None = None
    resource_id: UUID | None = None
    #: ``user`` / ``contact`` / ``manual`` - see ``roster_vocab.ROSTER_SOURCES``.
    source: str = "manual"
    display_name: str = ""
    company_name: str = ""
    trade: str = ""
    trade_label: str = ""
    site_role: str = ""
    site_role_label: str = ""
    email: str = ""
    phone: str = ""
    starts_on: date | None = None
    ends_on: date | None = None
    allocation_percent: int | None = None
    certifications: list[CertificationState] = Field(default_factory=list)
    notes: str = ""
    is_active: bool = True
    #: True when this person also holds project access through a team
    #: membership. A roster line never creates that on its own.
    has_project_access: bool = False
    #: True when the linked user account has been deactivated. The line stays,
    #: because the person may still be on site with a paper induction.
    user_is_inactive: bool = False
    #: True when today falls outside ``starts_on`` .. ``ends_on``.
    off_window: bool = False
    #: How many tickets on this line have run out.
    expired_certification_count: int = 0


class RosterMemberListResponse(BaseModel):
    """One page of the roster plus the size of the whole set.

    ``total`` is the number of roster lines matching the filters, not the
    length of ``items``. A caller holding fewer rows than ``total`` is holding
    a page and can ask for the rest; a caller deciding whether a project has
    anybody on it has to test ``total == 0`` with no filters applied, because
    a filtered zero means "nobody matched", not "nobody is here".

    The total costs no query. The service resolves and sorts every matched row
    in Python before it slices, so it is holding the whole filtered set and
    ``len()`` of it is exact - there is nothing here for a COUNT to add.
    """

    items: list[RosterMemberResponse] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


class RosterTradeCount(BaseModel):
    """Headcount for one trade or one role, for the roster summary."""

    key: str
    label: str
    count: int


class RosterSummary(BaseModel):
    """What the roster adds up to, so the screen can lead with the answer."""

    project_id: UUID
    headcount: int = 0
    active_headcount: int = 0
    company_count: int = 0
    #: People on the roster who hold no project access. Not a fault - most of a
    #: site has no login - but it is the number that explains an empty inbox.
    without_access_count: int = 0
    #: Project members who are not on the roster at all.
    unrostered_member_count: int = 0
    expired_certification_count: int = 0
    off_window_count: int = 0
    by_trade: list[RosterTradeCount] = Field(default_factory=list)
    by_site_role: list[RosterTradeCount] = Field(default_factory=list)


class RosterCandidate(BaseModel):
    """Somebody the platform already knows, offered for the roster."""

    #: The user id or the contact id, depending on ``source``.
    id: UUID
    source: str
    name: str
    email: str = ""
    phone: str = ""
    company_name: str = ""
    #: Already on this project's roster - shown ticked and not addable twice.
    on_roster: bool = False
    #: Already holds project access (users only).
    has_project_access: bool = False


class RosterCandidateListResponse(BaseModel):
    """One page of candidates plus how many people actually matched.

    ``total`` is a real count: two COUNT queries over the same filters the page
    query uses, summed. It is deliberately not ``len(items)``, because the two
    searches behind this list apply their limit in the database, so the rows
    held here are already cut short and their length would state a wrong number
    with confidence - worse than the bare array this replaced, which at least
    said nothing.

    ``offset`` is always 0 and no offset can be requested. See
    :meth:`RosterService.list_candidates` for why a merged list of two
    independently ordered sources cannot serve a second page honestly.
    """

    items: list[RosterCandidate] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


class RosterVocabularyEntry(BaseModel):
    """One entry of a roster vocabulary, with its English source label."""

    key: str
    label: str
    supervisory: bool = False


class RosterVocabularyResponse(BaseModel):
    """The closed vocabularies a roster line is written in."""

    trades: list[RosterVocabularyEntry] = Field(default_factory=list)
    site_roles: list[RosterVocabularyEntry] = Field(default_factory=list)


def roster_vocabulary() -> RosterVocabularyResponse:
    """The trade and site-role catalogues, in display order."""
    return RosterVocabularyResponse(
        trades=[RosterVocabularyEntry(key=t.key, label=t.label) for t in ROSTER_TRADES],
        site_roles=[RosterVocabularyEntry(key=r.key, label=r.label, supervisory=r.supervisory) for r in SITE_ROLES],
    )
