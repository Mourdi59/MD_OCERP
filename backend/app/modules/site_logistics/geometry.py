# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Small pure-Python polygon helpers for site areas (SPEC Decision 9).

Site areas are stored as GeoJSON ``Polygon`` objects, either in the project's
local site plan frame (metres) or in WGS84 (longitude, latitude). No PostGIS and
no shapely: the platform keeps PostgreSQL as its only required dependency, and a
site plan has a few dozen polygons, so plain arithmetic is fast enough.

Areas are computed with the shoelace formula: the outer ring minus its holes. A
WGS84 ring is projected onto a local equirectangular plane around its own
centroid first, which is accurate to well under a percent at site scale (a few
hundred metres). Coordinates are bounded on the way in, so an area always fits
its ``Numeric(14, 2)`` column.

Overlap is a boolean test on the outer rings (two polygons share interior area).
Each edge is cut where it meets the other polygon's boundary and the middle of
every piece is tested, so rectangles that share boundary lines are caught too.
Touching along a shared boundary is not an overlap: two adjacent areas drawn
edge to edge are fine. Holes are not subtracted in the overlap test, so an area
drawn inside another area's hole is reported; the finding is a warning.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

Point = tuple[float, float]

_EARTH_RADIUS_M = 6_371_008.8
_EPS = 1e-9
# A local frame may be a national grid (northings of several million metres).
MAX_LOCAL_COORDINATE_M = 1e7
# What Numeric(14, 2) holds, with room to spare: a million square kilometres.
MAX_AREA_M2 = 1e12


class GeometryError(ValueError):
    """The value is not a usable GeoJSON polygon."""


def _point(pt: Any, frame: str) -> Point:
    if not isinstance(pt, list | tuple) or len(pt) < 2:
        raise GeometryError("geometry_bad_point")
    if isinstance(pt[0], bool) or isinstance(pt[1], bool):
        raise GeometryError("geometry_bad_point")
    try:
        x, y = float(pt[0]), float(pt[1])
    except (TypeError, ValueError, OverflowError) as exc:
        raise GeometryError("geometry_bad_point") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise GeometryError("geometry_bad_point")
    if frame == "wgs84":
        if abs(x) > 180 or abs(y) > 90:
            raise GeometryError("geometry_out_of_range")
    elif abs(x) > MAX_LOCAL_COORDINATE_M or abs(y) > MAX_LOCAL_COORDINATE_M:
        raise GeometryError("geometry_out_of_range")
    return (x, y)


def _one_ring(raw: Any, frame: str) -> list[Point]:
    if not isinstance(raw, list):
        raise GeometryError("geometry_without_ring")
    ring = [_point(pt, frame) for pt in raw]
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise GeometryError("geometry_too_few_points")
    return ring


def _rings(geometry: Any, frame: str = "local") -> list[list[Point]]:
    """The outer ring followed by the holes, validated and bounded."""
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise GeometryError("geometry_not_polygon")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise GeometryError("geometry_without_ring")
    return [_one_ring(raw, frame) for raw in coords]


def _ring(geometry: Any, frame: str = "local") -> list[Point]:
    return _rings(geometry, frame)[0]


def _project(ring: list[Point], frame: str, origin: Point | None = None) -> list[Point]:
    """Metres around ``origin``: a plain shift in the local frame, equirectangular for WGS84."""
    x0, y0 = origin if origin is not None else _centroid(ring)
    if frame != "wgs84":
        return [(p[0] - x0, p[1] - y0) for p in ring]
    k = math.cos(math.radians(y0))
    return [(math.radians(p[0] - x0) * _EARTH_RADIUS_M * k, math.radians(p[1] - y0) * _EARTH_RADIUS_M) for p in ring]


def _shoelace(ring: list[Point]) -> float:
    twice = 0.0
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        twice += x1 * y2 - x2 * y1
    return abs(twice) / 2.0


def polygon_area_m2(geometry: dict[str, Any], frame: str = "local") -> Decimal:
    """Area of the outer ring minus its holes in square metres, rounded to 0.01 m2.

    Args:
        geometry: GeoJSON Polygon.
        frame: ``"local"`` (coordinates in metres) or ``"wgs84"`` (lon, lat).

    Raises:
        GeometryError: not a polygon, a coordinate out of range, holes larger than
            the outer ring, or an area beyond what the column stores.
    """
    rings = _rings(geometry, frame)
    origin = _centroid(rings[0])
    outer = _shoelace(_project(rings[0], frame, origin))
    holes = sum(_shoelace(_project(r, frame, origin)) for r in rings[1:])
    area = outer - holes
    if area < 0:
        raise GeometryError("geometry_bad_hole")
    if not math.isfinite(area) or area >= MAX_AREA_M2:
        raise GeometryError("geometry_too_large")
    return Decimal(str(round(area, 2)))


def validate_polygon(geometry: dict[str, Any], frame: str = "local") -> None:
    """Raise :class:`GeometryError` unless ``geometry`` is a storable GeoJSON polygon of ``frame``."""
    polygon_area_m2(geometry, frame)


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    if abs(_orient(a, b, p)) > _EPS:
        return False
    return min(a[0], b[0]) - _EPS <= p[0] <= max(a[0], b[0]) + _EPS and (
        min(a[1], b[1]) - _EPS <= p[1] <= max(a[1], b[1]) + _EPS
    )


def _strictly_inside(p: Point, ring: list[Point]) -> bool:
    """Ray casting; a point on the boundary is not inside."""
    n = len(ring)
    for i in range(n):
        if _on_segment(p, ring[i], ring[(i + 1) % n]):
            return False
    inside = False
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]):
            x_cross = x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1)
            if p[0] < x_cross:
                inside = not inside
    return inside


def _centroid(ring: list[Point]) -> Point:
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def _param(p: Point, a: Point, b: Point) -> float:
    """Where ``p`` (on the line through ``a`` and ``b``) sits along ``a -> b``: 0 at ``a``, 1 at ``b``."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)


def _cuts(a: Point, b: Point, other: list[Point]) -> list[float]:
    """Parameters in (0, 1) where segment ``a -> b`` meets the boundary of ``other``."""
    out: list[float] = []
    n = len(other)
    for j in range(n):
        q1, q2 = other[j], other[(j + 1) % n]
        for q in (q1, q2):
            if _on_segment(q, a, b):
                out.append(_param(q, a, b))
        d1, d2 = _orient(a, b, q1), _orient(a, b, q2)
        if (d1 > _EPS and d2 < -_EPS) or (d1 < -_EPS and d2 > _EPS):
            # The line through a, b separates q1 from q2: where does q1 -> q2 cross it?
            u = d1 / (d1 - d2)
            cross = (q1[0] + u * (q2[0] - q1[0]), q1[1] + u * (q2[1] - q1[1]))
            out.append(_param(cross, a, b))
    return [t for t in out if _EPS < t < 1 - _EPS]


def _boundary_enters(ring: list[Point], other: list[Point]) -> bool:
    """True when a piece of ``ring``'s boundary runs through the interior of ``other``."""
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if abs(a[0] - b[0]) <= _EPS and abs(a[1] - b[1]) <= _EPS:
            continue
        stops = sorted({0.0, 1.0, *_cuts(a, b, other)})
        for t1, t2 in zip(stops, stops[1:], strict=False):
            mid = (t1 + t2) / 2.0
            if _strictly_inside((a[0] + mid * (b[0] - a[0]), a[1] + mid * (b[1] - a[1])), other):
                return True
    return False


def _interior_point(ring: list[Point]) -> Point | None:
    """A point strictly inside a simple ring: the middle of the first span of a scanline."""
    ys = sorted({p[1] for p in ring})
    for low, high in zip(ys, ys[1:], strict=False):
        if high - low <= _EPS:
            continue
        y = (low + high) / 2.0
        xs = []
        n = len(ring)
        for i in range(n):
            (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        if len(xs) >= 2 and xs[1] - xs[0] > _EPS:
            return ((xs[0] + xs[1]) / 2.0, y)
    return None


def polygons_overlap(a: dict[str, Any], b: dict[str, Any], frame: str = "local") -> bool:
    """True when the outer rings of two polygons share interior area (shared edges alone do not count).

    Either a piece of one boundary runs through the other's interior, or neither
    does and the two cover the same region, in which case any interior point of
    one is inside the other.
    """
    ra, rb = _ring(a, frame), _ring(b, frame)
    origin = _centroid(ra)
    ra, rb = _project(ra, frame, origin), _project(rb, frame, origin)
    if _boundary_enters(ra, rb) or _boundary_enters(rb, ra):
        return True
    inner = _interior_point(ra)
    return inner is not None and _strictly_inside(inner, rb)
