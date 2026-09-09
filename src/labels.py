"""
Chronological marker placement.

This module turns validated visit entries into a deterministic, editable
placement plan: where each visit's numbered marker sits (a geometry-safe
anchor point, never a blind centroid), which map it belongs on (the main
world map or a future regional inset), and whether it needs a manual nudge
or a leader line. It knows nothing about Matplotlib -- src/poster.py reads
this plan to actually draw.

Nothing here invents a visit number or a country. A visit that didn't
match a geographic entity (see src/matcher.py) never reaches this module,
because callers only pass already-`matched` entries.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point

from .matcher import normalize

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABEL_OFFSETS_PATH = PROJECT_ROOT / "data" / "label_offsets.json"

VALID_DISPLAY_TARGETS = {"main", "europe", "gulf", "caribbean", "pacific"}
DEFAULT_DISPLAY_TARGET = "main"

# How much a candidate pair of markers is allowed to encroach on each
# other's circle before it counts as a collision. >1.0 also catches
# "nearly touching" pairs, per the near-overlap requirement.
DEFAULT_OVERLAP_FACTOR = 1.3
DEFAULT_MARKER_RADIUS_POINTS = 7.0


def load_label_offsets(path: Path | None = None) -> dict[str, dict]:
    path = path or LABEL_OFFSETS_PATH
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        normalize(k): v
        for k, v in raw.items()
        if not k.startswith("_") and isinstance(v, dict)
    }


@dataclass
class PlacementEntry:
    visit_number: int
    source_name: str
    entity_ids: list[int]
    anchor_entity_id: int
    region: str | None
    anchor_lonlat: Point  # true geographic anchor, pre-offset, EPSG:4326
    display_target: str
    dx: float = 0.0  # degrees longitude, applied before projection
    dy: float = 0.0  # degrees latitude, applied before projection
    leader_line: bool = False
    scale: float = 1.0
    # Filled in by project_placements() for a specific render pass/CRS.
    x: float | None = None
    y: float | None = None
    true_x: float | None = None
    true_y: float | None = None


@dataclass
class CollisionPair:
    visit_a: int
    visit_b: int
    distance: float
    threshold: float


@dataclass
class MarkerReport:
    placements: list[PlacementEntry]
    collisions_before: list[CollisionPair]
    collisions_after: list[CollisionPair]
    adjustments: dict[int, tuple[float, float]] = field(default_factory=dict)
    marker_radius_data: float = 0.0  # data-unit radius collisions were checked against

    target_display: str = "main"

    def placements_for(self, target_display: str) -> list[PlacementEntry]:
        return [p for p in self.placements if p.display_target == target_display]

    @property
    def main_placements(self) -> list[PlacementEntry]:
        return self.placements_for("main")

    @property
    def target_placements(self) -> list[PlacementEntry]:
        """The placements actually drawn on this report's own render
        pass (main or whichever inset it was built for)."""
        return self.placements_for(self.target_display)

    def counts_by_display(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.placements:
            counts[p.display_target] = counts.get(p.display_target, 0) + 1
        return counts


def choose_anchor_entity(gdf: gpd.GeoDataFrame, entity_ids: list[int]) -> int:
    """Picks which entity's geometry anchors a (possibly composite) visit's
    marker: the single entity if there's only one, otherwise the
    largest-area part -- e.g. England for the UK, Antigua for Antigua &
    Barbuda -- so the marker lands somewhere substantial rather than on
    an arbitrarily-chosen small island."""
    if len(entity_ids) == 1:
        return entity_ids[0]
    return max(entity_ids, key=lambda eid: gdf.at[eid, "geometry"].area)


def compute_anchor_point(gdf: gpd.GeoDataFrame, entity_id: int) -> Point:
    """A point guaranteed to lie on the entity's own geometry -- unlike a
    centroid, which can fall outside a concave shape or in open ocean for
    an archipelago."""
    return gdf.at[entity_id, "geometry"].representative_point()


def build_placements(
    gdf: gpd.GeoDataFrame,
    mapped_entries,
    offsets: dict[str, dict] | None = None,
) -> list[PlacementEntry]:
    """Builds one PlacementEntry per visit record (per MappedEntry) -- a
    composite entity still gets exactly one marker for its one visit, and
    an entity that is also separately visited on its own (e.g. Scotland,
    alongside the United Kingdom) gets its own independent marker because
    it is its own MappedEntry."""
    if offsets is None:
        offsets = load_label_offsets()

    placements = []
    for entry in mapped_entries:
        anchor_id = choose_anchor_entity(gdf, entry.entity_ids)
        anchor_point = compute_anchor_point(gdf, anchor_id)

        cfg = offsets.get(normalize(entry.country_raw), {})
        display_target = cfg.get("display", DEFAULT_DISPLAY_TARGET)
        if display_target not in VALID_DISPLAY_TARGETS:
            raise ValueError(
                f"label_offsets.json: '{entry.country_raw}' has invalid "
                f"display target '{display_target}'"
            )
        # A per-display-target sub-object (e.g. "europe": {"dx": 8, ...})
        # overrides the flat top-level dx/dy/leader_line/scale, which stay
        # as a backward-compatible fallback for entries with only one
        # possible display target.
        region_cfg = cfg.get(display_target, {})
        if not isinstance(region_cfg, dict):
            region_cfg = {}
        dx = float(region_cfg.get("dx", cfg.get("dx", 0.0)))
        dy = float(region_cfg.get("dy", cfg.get("dy", 0.0)))
        if "leader_line" in region_cfg:
            leader_line = bool(region_cfg["leader_line"])
        elif "leader_line" in cfg:
            leader_line = bool(cfg["leader_line"])
        else:
            leader_line = bool(dx or dy)
        scale = float(region_cfg.get("scale", cfg.get("scale", 1.0)))

        placements.append(
            PlacementEntry(
                visit_number=entry.number,
                source_name=entry.country_raw,
                entity_ids=list(entry.entity_ids),
                anchor_entity_id=anchor_id,
                region=entry.region_raw,
                anchor_lonlat=anchor_point,
                display_target=display_target,
                dx=dx,
                dy=dy,
                leader_line=leader_line,
                scale=scale,
            )
        )
    return placements


def project_placements(placements: list[PlacementEntry], crs: str) -> list[PlacementEntry]:
    """Projects each placement's true anchor and offset (dx/dy applied in
    degrees, pre-projection) into the target CRS, filling x/y (final
    marker position) and true_x/true_y (unshifted geographic point, for
    leader lines). Mutates and returns the same list."""
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    for p in placements:
        lon, lat = p.anchor_lonlat.x, p.anchor_lonlat.y
        p.true_x, p.true_y = transformer.transform(lon, lat)
        p.x, p.y = transformer.transform(lon + p.dx, lat + p.dy)
    return placements


def detect_collisions(
    placements: list[PlacementEntry],
    marker_radius: float,
    overlap_factor: float = DEFAULT_OVERLAP_FACTOR,
) -> list[CollisionPair]:
    """Pairwise check of projected marker positions (x, y must already be
    set). O(n^2) is fine here -- at most a few hundred markers on any one
    map, not an optimizer, just a report."""
    collisions = []
    n = len(placements)
    for i in range(n):
        pi = placements[i]
        if pi.x is None:
            continue
        for j in range(i + 1, n):
            pj = placements[j]
            if pj.x is None:
                continue
            distance = math.hypot(pi.x - pj.x, pi.y - pj.y)
            threshold = (marker_radius * pi.scale + marker_radius * pj.scale) * overlap_factor
            if distance < threshold:
                collisions.append(
                    CollisionPair(
                        visit_a=pi.visit_number,
                        visit_b=pj.visit_number,
                        distance=distance,
                        threshold=threshold,
                    )
                )
    return collisions


def resolve_collisions(
    placements: list[PlacementEntry],
    marker_radius: float,
    overlap_factor: float = DEFAULT_OVERLAP_FACTOR,
    max_iterations: int = 30,
) -> tuple[list[CollisionPair], dict[int, tuple[float, float]]]:
    """Simple, deterministic separation: for each remaining collision, push
    the two markers directly apart along the line between their centers.
    Only markers with no manual dx/dy in the config are moved -- a manual
    placement always wins. This is intentionally basic (no cartographic
    optimizer): if it can't resolve a pair within max_iterations, the pair
    is left in the returned collision list for a human to fix via
    label_offsets.json.

    Returns (remaining_collisions, adjustments) where adjustments maps
    visit_number -> total (dx, dy) nudge applied, in the same data units
    as marker_radius.
    """
    by_visit = {p.visit_number: p for p in placements}
    adjustments: dict[int, tuple[float, float]] = {}

    for _ in range(max_iterations):
        collisions = detect_collisions(placements, marker_radius, overlap_factor)
        if not collisions:
            break

        moved_any = False
        for pair in collisions:
            pa = by_visit[pair.visit_a]
            pb = by_visit[pair.visit_b]
            a_pinned = bool(pa.dx or pa.dy)
            b_pinned = bool(pb.dx or pb.dy)
            if a_pinned and b_pinned:
                continue  # both manually placed -- leave as a reported collision

            vec_x = pb.x - pa.x
            vec_y = pb.y - pa.y
            dist = math.hypot(vec_x, vec_y)
            if dist < 1e-9:
                # Exactly coincident points -- nudge deterministically along +x.
                vec_x, vec_y, dist = 1.0, 0.0, 1.0
            needed = (pair.threshold - dist) / 2 + marker_radius * 0.05
            ux, uy = vec_x / dist, vec_y / dist

            if not a_pinned:
                pa.x -= ux * needed
                pa.y -= uy * needed
                prev = adjustments.get(pa.visit_number, (0.0, 0.0))
                adjustments[pa.visit_number] = (prev[0] - ux * needed, prev[1] - uy * needed)
                moved_any = True
            if not b_pinned:
                pb.x += ux * needed
                pb.y += uy * needed
                prev = adjustments.get(pb.visit_number, (0.0, 0.0))
                adjustments[pb.visit_number] = (prev[0] + ux * needed, prev[1] + uy * needed)
                moved_any = True

        if not moved_any:
            break

    remaining = detect_collisions(placements, marker_radius, overlap_factor)
    return remaining, adjustments


def marker_radius_for_figure(data_width: float, fig_width_inches: float, marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS) -> float:
    """Converts a fixed on-page marker radius (in points, i.e. constant
    visual size regardless of map scale) into the equivalent radius in map
    data units for a figure of the given width -- so collision detection
    matches what will actually be drawn."""
    points_per_data_unit = (fig_width_inches * 72) / data_width
    return marker_radius_points / points_per_data_unit


def build_marker_report(
    gdf: gpd.GeoDataFrame,
    mapped_entries,
    crs: str,
    fig_width_inches: float,
    data_width: float | None = None,
    target_display: str = "main",
    offsets: dict[str, dict] | None = None,
    marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS,
    overlap_factor: float = DEFAULT_OVERLAP_FACTOR,
) -> MarkerReport:
    """Builds the full placement plan for one render pass (the main map, or
    one regional inset): anchors, display assignment, projection into
    `crs`, and collision detection/resolution among the entries assigned
    to `target_display` -- the only ones actually drawn on this particular
    map.

    Only placements matching `target_display` are projected into `crs`,
    both because they're the only ones that matter here and because a
    regional inset's CRS (e.g. Mercator, which is singular at the poles)
    is not necessarily valid across the whole globe.

    `data_width` is the width of this map's own frame in `crs` units, used
    to size markers/collision radius consistently with what's actually
    drawn. For the whole-world main map this is the full reprojected
    extent; for an inset it must be the inset's configured frame width
    (see src/insets.py), not the whole world's -- pass it explicitly.
    Defaults to the full reprojected extent of `gdf` if omitted, which is
    only correct for the main map.
    """
    placements = build_placements(gdf, mapped_entries, offsets)
    target_placements = [p for p in placements if p.display_target == target_display]
    project_placements(target_placements, crs)

    if data_width is None:
        total_bounds = gdf.to_crs(crs).total_bounds
        data_width = total_bounds[2] - total_bounds[0]
    marker_radius = marker_radius_for_figure(data_width, fig_width_inches, marker_radius_points)

    collisions_before = detect_collisions(target_placements, marker_radius, overlap_factor)
    collisions_after, adjustments = resolve_collisions(target_placements, marker_radius, overlap_factor)

    return MarkerReport(
        placements=placements,
        collisions_before=collisions_before,
        collisions_after=collisions_after,
        adjustments=adjustments,
        target_display=target_display,
        marker_radius_data=marker_radius,
    )
