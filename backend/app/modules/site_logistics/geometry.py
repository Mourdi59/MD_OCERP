# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Small pure-Python polygon helpers for site areas (SPEC Decision 9).

Site areas are stored as GeoJSON ``Polygon`` objects, either in the project's
local site plan frame (metres) or in WGS84 (longitude, latitude). No PostGIS and
no shapely: the platform keeps PostgreSQL as its only required dependency, and a
site plan has a few dozen polygons, so plain arithmetic is fast enough.

Areas are computed with the shoelace formula. A WGS84 ring is projected onto a
local equirectangular plane around its own centroid first, which is accurate to
well under a percent at site scale (a few hundred metres).

Overlap is a boolean test (two polygons share interior area): edges cross, or a
vertex of one lies strictly inside the other. Touching along a shared boundary is
not an overlap, so two adjacent areas drawn edge to edge are fine.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

Point = tuple[float, float]

_EARTH_RADIUS_M = 6_371_008.8
_EPS = 1e-9


class GeometryError(ValueError):
    """The value is not a usable GeoJSON polygon."""


def _ring(geometry: dict[str, Any]) -> list[Point]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise GeometryError("geometry_not_polygon")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise GeometryError("geometry_without_ring")
    ring: list[Point] = []
    for pt in coords[0]:
        if not isinstance(pt, list | tuple) or len(pt) < 2:
            raise GeometryError("geometry_bad_point")
        try:
            ring.append((float(pt[0]), float(pt[1])))
        except (TypeError, ValueError) as exc:
            raise GeometryError("geometry_bad_point") from exc
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise GeometryError("geometry_too_few_points")
    return ring


def validate_polygon(geometry: dict[str, Any]) -> None:
    """Raise :class:`GeometryError` unless ``geometry`` is a GeoJSON polygon with an outer ring."""
    _ring(geometry)


def _project(ring: list[Point], frame: str) -> list[Point]:
    if frame != "wgs84":
        return ring
    lon0 = sum(p[0] for p in ring) / len(ring)
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    return [
        (
            math.radians(p[0] - lon0) * _EARTH_RADIUS_M * k,
            math.radians(p[1] - lat0) * _EARTH_RADIUS_M,
        )
        for p in ring
    ]


def polygon_area_m2(geometry: dict[str, Any], frame: str = "local") -> Decimal:
    """Area of the outer ring in square metres, rounded to 0.01 m2.

    Args:
        geometry: GeoJSON Polygon.
        frame: ``"local"`` (coordinates in metres) or ``"wgs84"`` (lon, lat).
    """
    ring = _project(_ring(geometry), frame)
    twice = 0.0
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        twice += x1 * y2 - x2 * y1
    return Decimal(str(round(abs(twice) / 2.0, 2)))


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Proper crossing only: segments that merely touch or run collinear do not count."""
    d1 = _orient(q1, q2, p1)
    d2 = _orient(q1, q2, p2)
    d3 = _orient(p1, p2, q1)
    d4 = _orient(p1, p2, q2)
    return ((d1 > _EPS and d2 < -_EPS) or (d1 < -_EPS and d2 > _EPS)) and (
        (d3 > _EPS and d4 < -_EPS) or (d3 < -_EPS and d4 > _EPS)
    )


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


def polygons_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when two polygons share interior area (shared edges alone do not count)."""
    ra, rb = _ring(a), _ring(b)
    for i in range(len(ra)):
        for j in range(len(rb)):
            if _segments_cross(ra[i], ra[(i + 1) % len(ra)], rb[j], rb[(j + 1) % len(rb)]):
                return True
    if any(_strictly_inside(p, rb) for p in ra) or any(_strictly_inside(p, ra) for p in rb):
        return True
    # Identical or edge-aligned rings: every vertex sits on the other's boundary.
    return _strictly_inside(_centroid(ra), rb) and _strictly_inside(_centroid(rb), ra)
