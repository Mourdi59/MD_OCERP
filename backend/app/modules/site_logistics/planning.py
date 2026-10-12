# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the logistics plan (SPEC section 4): no ORM, no database, stdlib only.

The service enforces these at write time, the validation rules and the readiness
provider read them, and the unit tests pin them. Everything that is a number is
Decimal; everything that is a moment is a timezone-aware datetime.

Time of day, weekday and calendar date are properties of the SITE's wall clock,
not of whatever offset a datetime happens to carry (PostgreSQL hands every
``timestamptz`` back in UTC). Every rule that reads one takes the site time zone
and converts first; none of them has a default zone, so a caller cannot forget.

State machines are plain transition tables. Each ``*_FSM`` maps a state to the
states it may move to; :func:`can_move` is the one check.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal
from typing import Any

# ── State machines ─────────────────────────────────────────────────────────

STAGE_FSM: dict[str, tuple[str, ...]] = {
    "planned": ("active",),
    "active": ("closed",),
    "closed": (),
}
MEDIA_FSM: dict[str, tuple[str, ...]] = {
    "identified": ("requested",),
    "requested": ("offered", "identified"),
    "offered": ("contracted", "requested"),
    "contracted": ("connected",),
    "connected": ("disconnected",),
    "disconnected": (),
}
TRANSPORT_FSM: dict[str, tuple[str, ...]] = {
    "planned": ("permit_pending", "scheduled", "cancelled"),
    "permit_pending": ("scheduled", "planned", "cancelled"),
    "scheduled": ("in_transit", "permit_pending", "cancelled"),
    "in_transit": ("arrived",),
    "arrived": ("closed",),
    "closed": (),
    "cancelled": (),
}
PERMIT_FSM: dict[str, tuple[str, ...]] = {
    "draft": ("applied",),
    "applied": ("granted", "refused"),
    "granted": ("expired",),
    "refused": (),
    "expired": (),
}
CUSTOMS_FSM: dict[str, tuple[str, ...]] = {
    "open": ("documents_complete",),
    "documents_complete": ("declared", "open"),
    "declared": ("cleared", "held"),
    "held": ("declared", "cleared"),
    "cleared": ("closed",),
    "closed": (),
}
CUSTOMS_DOCUMENT_FSM: dict[str, tuple[str, ...]] = {
    "missing": ("received",),
    "received": ("verified", "missing"),
    "verified": ("received",),
}
COMPLAINT_FSM: dict[str, tuple[str, ...]] = {
    "received": ("acknowledged",),
    "acknowledged": ("action_taken", "closed"),
    "action_taken": ("closed",),
    "closed": (),
}

TRANSPORT_STATES = tuple(TRANSPORT_FSM)
PERMIT_STATES = tuple(PERMIT_FSM)
MEDIA_STATES = tuple(MEDIA_FSM)
CUSTOMS_STATES = tuple(CUSTOMS_FSM)
COMPLAINT_STATES = tuple(COMPLAINT_FSM)
STAGE_STATES = tuple(STAGE_FSM)
CUSTOMS_DOCUMENT_STATES = tuple(CUSTOMS_DOCUMENT_FSM)
FLOW_MODES = ("stock", "just_in_time", "kanban", "direct_install")


def can_move(fsm: Mapping[str, Sequence[str]], current: str, target: str) -> bool:
    """True when ``fsm`` allows ``current -> target``."""
    return target in fsm.get(current, ())


# ── Time of day ────────────────────────────────────────────────────────────


def hhmm(value: str | None) -> int | None:
    """``"HH:MM"`` to minutes after midnight; ``None`` when missing or malformed."""
    if not value or not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def site_zone(name: str | None) -> tzinfo | None:
    """The IANA zone ``name``, or ``None`` when it is unset or unknown."""
    from zoneinfo import ZoneInfo

    if not name or not isinstance(name, str):
        return None
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        return None


def local(moment: datetime, tz: tzinfo) -> datetime:
    """``moment`` on the site's wall clock.

    Raises:
        ValueError: on a naive datetime, which names no instant.
    """
    if moment.tzinfo is None:
        raise ValueError("naive datetime has no site time")
    return moment.astimezone(tz)


def _at(day: date, minutes: int, tz: tzinfo) -> datetime:
    return datetime(day.year, day.month, day.day, minutes // 60, minutes % 60, tzinfo=tz)


def _occurrences(
    start_hhmm: str, end_hhmm: str, around: datetime, until: datetime, tz: tzinfo
) -> list[tuple[datetime, datetime]]:
    """Daily occurrences on the site clock of a time range (overnight when end <= start) touching ``[around, until]``."""
    s, e = hhmm(start_hhmm), hhmm(end_hhmm)
    if s is None or e is None or s == e:
        return []
    around, until = local(around, tz), local(until, tz)
    out = []
    day = around.date() - timedelta(days=1)
    while day <= until.date():
        begin = _at(day, s, tz)
        finish = _at(day + timedelta(days=1), e, tz) if e <= s else _at(day, e, tz)
        out.append((begin, finish))
        day += timedelta(days=1)
    return out


def within_hours(open_hhmm: str | None, close_hhmm: str | None, start: datetime, end: datetime, tz: tzinfo) -> bool:
    """``[start, end]`` lies inside one site day's ``open .. close``; unset or senseless hours restrict nothing."""
    o, c = hhmm(open_hhmm), hhmm(close_hhmm)
    if o is None or c is None or c <= o:
        return True
    s, e = local(start, tz), local(end, tz)
    if s.date() != e.date():
        return False
    return s.hour * 60 + s.minute >= o and e.hour * 60 + e.minute <= c


def narrower_hours(gate: tuple[str | None, str | None], concept: tuple[str | None, str | None] | None) -> tuple:
    """Rule 12: concept delivery hours apply only where they are narrower than the gate's.

    Returns the effective ``(open, close)``: the later opening and the earlier closing.
    """
    if not concept or hhmm(concept[0]) is None or hhmm(concept[1]) is None:
        return gate
    g_open, g_close = hhmm(gate[0]), hhmm(gate[1])
    c_open, c_close = hhmm(concept[0]), hhmm(concept[1])
    if g_open is None or g_close is None:
        return concept
    open_ = concept[0] if c_open > g_open else gate[0]  # type: ignore[operator]
    close = concept[1] if c_close < g_close else gate[1]  # type: ignore[operator]
    return (open_, close)


# ── Rule 1 to 4: area balance ──────────────────────────────────────────────


@dataclass(frozen=True)
class AllocationFact:
    site_area_id: str
    area_kind: str
    allocated_m2: Decimal
    area_m2: Decimal | None = None
    geometry: dict[str, Any] | None = None
    frame: str = "local"


@dataclass
class AreaBalance:
    site_total_m2: Decimal
    counted_m2: Decimal
    difference_m2: Decimal
    difference_pct: Decimal | None
    closed: bool
    by_group: dict[str, Decimal] = field(default_factory=dict)
    by_kind: dict[str, Decimal] = field(default_factory=dict)
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_total_m2": str(self.site_total_m2),
            "counted_m2": str(self.counted_m2),
            "difference_m2": str(self.difference_m2),
            "difference_pct": None if self.difference_pct is None else str(self.difference_pct),
            "closed": self.closed,
            "by_group": {k: str(v) for k, v in self.by_group.items()},
            "by_kind": {k: str(v) for k, v in self.by_kind.items()},
            "reason": self.reason,
        }


def area_balance(
    allocations: Iterable[AllocationFact],
    kinds: Mapping[str, Any],
    tolerance_pct: Decimal,
    site_total_fallback_m2: Decimal | None = None,
) -> AreaBalance:
    """Rule 1: the counted allocations of a stage add up to the site total within tolerance.

    ``kinds`` maps an area kind code to an object with ``counts_in_balance`` and
    ``balance_group``. The site total is the stage's ``site_total`` allocation; a
    stage without one falls back to the declared site area (``site_total_fallback_m2``).
    """
    rows = list(allocations)
    site_total = sum((a.allocated_m2 for a in rows if a.area_kind == "site_total"), Decimal("0"))
    if site_total == 0 and site_total_fallback_m2:
        site_total = site_total_fallback_m2
    by_group: dict[str, Decimal] = {}
    by_kind: dict[str, Decimal] = {}
    counted = Decimal("0")
    for a in rows:
        if a.area_kind == "site_total":
            continue
        kind = kinds.get(a.area_kind)
        by_kind[a.area_kind] = by_kind.get(a.area_kind, Decimal("0")) + a.allocated_m2
        if kind is None or not kind.counts_in_balance:
            continue
        counted += a.allocated_m2
        by_group[kind.balance_group] = by_group.get(kind.balance_group, Decimal("0")) + a.allocated_m2
    diff = counted - site_total
    if site_total <= 0:
        return AreaBalance(site_total, counted, diff, None, False, by_group, by_kind, "no_site_total")
    pct = (abs(diff) * Decimal("100") / site_total).quantize(Decimal("0.01"))
    closed = abs(diff) * Decimal("100") <= tolerance_pct * site_total
    return AreaBalance(site_total, counted, diff, pct, closed, by_group, by_kind, None if closed else "not_closed")


def allocation_exceeds_area(allocated_m2: Decimal, area_m2: Decimal | None) -> bool:
    """Rule 2: an allocation larger than its area. An area of unknown size cannot be exceeded."""
    return area_m2 is not None and allocated_m2 > area_m2


def overlapping_pairs(allocations: Sequence[AllocationFact]) -> list[tuple[str, str]]:
    """Rule 2: pairs of areas of one stage, different kinds, whose polygons overlap."""
    from app.modules.site_logistics.geometry import GeometryError, polygons_overlap

    out = []
    for i, a in enumerate(allocations):
        for b in allocations[i + 1 :]:
            if a.site_area_id == b.site_area_id or a.area_kind == b.area_kind:
                continue
            if a.area_kind == "site_total" or b.area_kind == "site_total":
                continue
            if not a.geometry or not b.geometry or a.frame != b.frame:
                continue
            try:
                if polygons_overlap(a.geometry, b.geometry, a.frame):
                    out.append((a.site_area_id, b.site_area_id))
            except GeometryError:
                continue
    return out


def stage_gaps(allocation_kinds: Iterable[str]) -> list[str]:
    """Rule 3: the finding codes of an active stage without storage or site setup."""
    kinds = set(allocation_kinds)
    out = []
    if not kinds & {"storage", "laydown"}:
        out.append("stage_without_storage")
    if "site_setup" not in kinds:
        out.append("stage_without_site_setup")
    return out


# ── Rule 5 and 6: heavy loads and permits ──────────────────────────────────

# Vehicle field -> gate / load-class field. A vehicle needs at most the gate's value.
LOAD_FIELDS: tuple[tuple[str, str], ...] = (
    ("axle_load_t", "max_axle_load_t"),
    ("gross_weight_t", "max_gross_t"),
    ("height_m", "max_height_m"),
    ("width_m", "max_width_m"),
    ("length_m", "max_length_m"),
    ("turning_radius_m", "turning_radius_m"),
)
_CLASS_FIELDS = {
    "max_axle_load_t": "axle_load_t",
    "max_gross_t": "gross_weight_t",
    "max_height_m": "max_height_m",
    "max_width_m": "max_width_m",
    "max_length_m": "max_length_m",
    "turning_radius_m": "turning_radius_m",
}


def limits_from_class(load_class: Any) -> dict[str, Decimal | None]:
    """A catalogue load class in the gate's limit vocabulary."""
    return {gate_f: getattr(load_class, cls_f, None) for gate_f, cls_f in _CLASS_FIELDS.items()}


def exceeded_limits(vehicle: Mapping[str, Any], limits: Mapping[str, Any]) -> list[str]:
    """Vehicle fields that exceed a set of limits; an unset limit or value is not exceeded."""
    out = []
    for v_field, l_field in LOAD_FIELDS:
        value, limit = vehicle.get(v_field), limits.get(l_field)
        if value is None or limit is None:
            continue
        if Decimal(str(value)) > Decimal(str(limit)):
            out.append(v_field)
    return out


def limits_unknown(limits: Mapping[str, Any]) -> bool:
    """Rule 5: a gate with no load or dimension limit set at all."""
    return all(limits.get(l_field) is None for _v, l_field in LOAD_FIELDS)


def is_heavy(
    vehicle: Mapping[str, Any],
    class_limits: Mapping[str, Mapping[str, Any]],
    *,
    chosen: str | None = None,
    always_heavy: bool = False,
) -> bool:
    """Rule 6: derived, never stored.

    Heavy when the transport kind says so, or the vehicle exceeds the load class
    chosen for it. Without a choice it is measured against the most permissive
    class: heavy only when no class of the catalogue admits it. Exceeding one
    class while another admits the vehicle (42 t against a 40 t and a 44 t
    class) is not heavy. A catalogue without load classes makes nothing heavy;
    the gate limits are rule 5.
    """
    if always_heavy:
        return True
    if chosen is not None and chosen in class_limits:
        return bool(exceeded_limits(vehicle, class_limits[chosen]))
    if not class_limits:
        return False
    return all(exceeded_limits(vehicle, limits) for limits in class_limits.values())


def window_in_allowed(windows: Sequence[Mapping[str, Any]] | None, start: datetime, end: datetime, tz: tzinfo) -> bool:
    """Rule 6: ``[start, end]`` lies inside one occurrence of one allowed window, on the site clock.

    A window is ``{"weekdays": [0..6], "from": "HH:MM", "to": "HH:MM"}`` (Monday 0, the
    site weekday the occurrence starts on); ``to <= from`` is an overnight window
    that ends the next day. No windows means the permit sets no time restriction.
    """
    if not windows:
        return True
    for w in windows:
        weekdays = set(w.get("weekdays") or range(7))
        for occ_start, occ_end in _occurrences(str(w.get("from")), str(w.get("to")), start, end, tz):
            if occ_start.weekday() in weekdays and occ_start <= start and end <= occ_end:
                return True
    return False


def permit_covers(permit: Mapping[str, Any], start: datetime, end: datetime, tz: tzinfo) -> bool:
    """Rule 6: a granted permit whose validity covers the window and whose windows contain it.

    Validity is in site dates: a window that starts at 00:30 site time on the first
    valid day is covered, whatever day that instant is in UTC.
    """
    if permit.get("state") != "granted":
        return False
    vf, vt = permit.get("valid_from"), permit.get("valid_to")
    if vf is not None and local(start, tz).date() < vf:
        return False
    if vt is not None and local(end, tz).date() > vt:
        return False
    return window_in_allowed(permit.get("allowed_windows"), start, end, tz)


def covering_permit(
    permits: Sequence[Mapping[str, Any]],
    start: datetime | None,
    end: datetime | None,
    kinds: Iterable[str],
    tz: tzinfo,
) -> Mapping[str, Any] | None:
    """The first granted permit of one of ``kinds`` that covers ``[start, end]``, else ``None``."""
    if start is None or end is None:
        return None
    wanted = set(kinds)
    return next(
        (p for p in permits if p.get("permit_kind") in wanted and permit_covers(p, start, end, tz)),
        None,
    )


def heavy_permit_standing(permits: Sequence[Mapping[str, Any]], kinds: Iterable[str]) -> str:
    """Where a heavy transport stands with the authority: ``granted``, ``applied`` or ``missing``.

    Only ``granted`` lets the transport run. An application is work in progress:
    the authority may still refuse it or change the route.
    """
    wanted = set(kinds)
    states = {p.get("state") for p in permits if p.get("permit_kind") in wanted}
    if "granted" in states:
        return "granted"
    return "applied" if "applied" in states else "missing"


def heavy_permit_finding(
    permits: Sequence[Mapping[str, Any]],
    start: datetime | None,
    end: datetime | None,
    kinds: Iterable[str],
    tz: tzinfo,
) -> str | None:
    """Rule 6 for one heavy transport: ``None`` or ``heavy_without_permit`` / ``window_outside_permit``."""
    relevant = [p for p in permits if p.get("permit_kind") in set(kinds)]
    granted = [p for p in relevant if p.get("state") == "granted"]
    if not granted:
        return "heavy_without_permit"
    if start is None or end is None:
        return "window_outside_permit"
    return None if any(permit_covers(p, start, end, tz) for p in granted) else "window_outside_permit"


def permit_expiry(valid_to: date | None, today: date, warn_days: int) -> str:
    """Rule 7: ``ok``, ``expiring`` (within ``warn_days``) or ``expired`` (past ``valid_to``)."""
    if valid_to is None:
        return "ok"
    if valid_to < today:
        return "expired"
    if (valid_to - today).days <= warn_days:
        return "expiring"
    return "ok"


# ── Rule 8 to 10: media ────────────────────────────────────────────────────


def media_required(demands: Iterable[tuple[Decimal, Decimal]], reserve_pct: Decimal) -> Decimal:
    """Rule 8: sum(peak * simultaneity) * (1 + reserve)."""
    base = sum((peak * factor for peak, factor in demands), Decimal("0"))
    return (base * (Decimal("1") + reserve_pct / Decimal("100"))).quantize(Decimal("0.001"))


def media_short(required: Decimal, contracted: Decimal | None) -> bool:
    """Rule 8: required capacity above the contracted one. Nothing contracted is short when anything is needed."""
    return required > (contracted or Decimal("0"))


def media_late(state: str, promised_on: date | None, stage_start: date | None, today: date) -> bool:
    """Rule 10: a connection a stage needs, not contracted, promised after the stage starts.

    No promise date is late only once the stage has started; before that it is an open item.
    """
    if state in ("contracted", "connected") or stage_start is None:
        return False
    if promised_on is not None:
        return promised_on > stage_start
    return stage_start <= today


# ── Rule 11: just in time ──────────────────────────────────────────────────


def jit_finding(window_start: date, takt_start: date | None, buffer_days: int) -> str | None:
    """Rule 11: ``jit_too_early`` (more than ``buffer_days`` before the takt start), ``jit_late`` (after it).

    ``window_start`` is the SITE date of the delivery window.
    """
    if takt_start is None:
        return None
    if window_start > takt_start:
        return "jit_late"
    if (takt_start - window_start).days > buffer_days:
        return "jit_too_early"
    return None


# ── Rule 13: quiet hours ───────────────────────────────────────────────────


def quiet_hours_conflict(quiet: Sequence[str] | None, start: datetime, end: datetime, tz: tzinfo) -> bool:
    """Rule 13: ``[start, end)`` touches the site's quiet hours ``(from, to)``, overnight when ``to <= from``."""
    if not quiet or len(quiet) != 2:
        return False
    return any(o_start < end and start < o_end for o_start, o_end in _occurrences(quiet[0], quiet[1], start, end, tz))


def starts_per_hour(starts: Iterable[datetime], tz: tzinfo) -> dict[datetime, int]:
    """Rule 12: how many movements start within each site clock hour."""
    counts: dict[datetime, int] = {}
    for start in starts:
        hour = local(start, tz).replace(minute=0, second=0, microsecond=0)
        counts[hour] = counts.get(hour, 0) + 1
    return counts


# ── Rule 14 to 17: customs ─────────────────────────────────────────────────


def hs_code_valid(code: str | None, min_digits: int) -> bool:
    """Rule 14: digits only, between ``min_digits`` and 10 long."""
    return bool(code) and code.isdigit() and min_digits <= len(code) <= 10  # type: ignore[union-attr]


SEA_MODES = ("sea", "inland_waterway")


def sea_only_mismatch(incoterm: Any, transport_mode: str | None) -> bool:
    """Rule 14: a sea-only incoterm on a case shipped by another mode."""
    return bool(getattr(incoterm, "sea_only", False)) and bool(transport_mode) and transport_mode not in SEA_MODES


def required_documents(
    direction: str,
    incoterm: Any,
    rules: Iterable[Any],
    transport_mode: str | None = None,
    preferential: bool = False,
) -> list[str]:
    """Rule 15: the documents our side needs, read from the catalogue's document rules.

    We are the buyer on an import and the seller on an export. A rule with
    ``clearance`` applies when the incoterm gives that clearance to our side, so
    an EXW import needs the export declaration (the buyer clears export) and a DDP
    export the import declaration (the seller clears import). An unknown incoterm
    assigns no clearance: those rules are left out and the case reports
    ``incoterm_unknown``. The order is the catalogue's.
    """
    ours = "buyer" if direction == "import" else "seller"
    docs: list[str] = []
    for rule in rules:
        if direction not in rule.directions:
            continue
        if rule.clearance is not None and getattr(incoterm, f"{rule.clearance}_clearance_by", None) != ours:
            continue
        if rule.modes and transport_mode not in rule.modes:
            continue
        if rule.preferential_only and not preferential:
            continue
        if rule.kind not in docs:
            docs.append(rule.kind)
    return docs


def declarant_matches(direction: str, incoterm: Any, declarant_party: str | None) -> bool:
    """Rule 16: on an import the declarant is the party the incoterm assigns import clearance to."""
    if direction != "import" or not declarant_party or incoterm is None:
        return True
    return declarant_party == getattr(incoterm, "import_clearance_by", declarant_party)


def missing_required(documents: Iterable[Mapping[str, Any]]) -> list[str]:
    """Rule 15: kinds of required documents still ``missing``."""
    return [str(d.get("kind")) for d in documents if d.get("required") and d.get("state") == "missing"]


# ── Rule 18: neighbour complaints ──────────────────────────────────────────


def complaint_overdue(state: str, response_due: date | None, today: date) -> bool:
    """Rule 18: past ``response_due`` and still not acknowledged."""
    return state == "received" and response_due is not None and today > response_due


def json_safe(value: Any) -> Any:
    """Make a value storable in a JSON column: dates ISO, Decimal as str, UUID as str, tuples as lists."""
    import uuid as _uuid

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [json_safe(v) for v in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, _uuid.UUID):
        return str(value)
    return value
