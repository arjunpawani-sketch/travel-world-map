"""
Regional inset configuration: fixed cartographic bounds, projection choice
per inset, and the geometry helpers needed to crop/frame a world
GeoDataFrame consistently for one inset.

Bounds are deliberately explicit and file-based (data/insets.json), not
derived from whichever entries happen to be visited -- an updated Excel
file should never make an inset's framing jump around. See that file's
_comment/_projection_notes for the reasoning behind each choice.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import unary_union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSETS_CONFIG_PATH = PROJECT_ROOT / "data" / "insets.json"

VALID_PROJECTIONS = {"lcc", "mercator", "eqc"}


@dataclass
class InsetConfig:
    key: str
    title: str
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    projection: str = "lcc"
    lon_0: float | None = None  # required (and used) when the frame wraps the antimeridian

    @property
    def wraps_antimeridian(self) -> bool:
        return self.lon_min > self.lon_max

    @property
    def center_lon(self) -> float:
        if self.lon_0 is not None:
            return self.lon_0
        if self.wraps_antimeridian:
            raise ValueError(
                f"Inset '{self.key}' wraps the antimeridian (lon_min > lon_max) "
                "but has no explicit lon_0 -- add one to data/insets.json."
            )
        return (self.lon_min + self.lon_max) / 2

    @property
    def center_lat(self) -> float:
        return (self.lat_min + self.lat_max) / 2

    def crs(self) -> str:
        if self.projection not in VALID_PROJECTIONS:
            raise ValueError(
                f"Inset '{self.key}' has unknown projection '{self.projection}' "
                f"(expected one of {sorted(VALID_PROJECTIONS)})"
            )
        lon_0 = self.center_lon
        lat_0 = self.center_lat
        if self.projection == "lcc":
            lat_range = self.lat_max - self.lat_min
            sp1 = self.lat_min + lat_range / 6
            sp2 = self.lat_max - lat_range / 6
            return (
                f"+proj=lcc +lat_1={sp1} +lat_2={sp2} +lat_0={lat_0} "
                f"+lon_0={lon_0} +datum=WGS84 +units=m +no_defs"
            )
        if self.projection == "mercator":
            return f"+proj=merc +lon_0={lon_0} +datum=WGS84 +units=m +no_defs"
        # eqc (Plate Carrée)
        return f"+proj=eqc +lat_ts={lat_0} +lon_0={lon_0} +datum=WGS84 +units=m +no_defs"

    def bbox_polygons(self, pad_deg: float = 0.0):
        """One or two lon/lat boxes (two only when the frame wraps the
        antimeridian) covering this inset's configured bounds, for
        filtering which geographic entities are relevant context."""
        lat_min = max(self.lat_min - pad_deg, -90)
        lat_max = min(self.lat_max + pad_deg, 90)
        if not self.wraps_antimeridian:
            return [box(self.lon_min - pad_deg, lat_min, self.lon_max + pad_deg, lat_max)]
        return [
            box(self.lon_min - pad_deg, lat_min, 180, lat_max),
            box(-180, lat_min, self.lon_max + pad_deg, lat_max),
        ]

    def unwrap_lon(self, lon: float) -> float:
        """Shifts `lon` to whichever representative value is closest to
        this inset's central meridian -- e.g. for the Pacific inset
        (lon_0=170), a raw -174.5 (Kiribati) becomes 185.5, staying on the
        correct, continuous side of the frame instead of jumping across."""
        lon_0 = self.center_lon
        return lon_0 + (((lon - lon_0 + 180) % 360) - 180)


def load_insets(path: Path | None = None) -> dict[str, InsetConfig]:
    path = path or INSETS_CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    configs = {}
    for key, cfg in raw.items():
        if key.startswith("_"):
            continue
        configs[key] = InsetConfig(
            key=key,
            title=cfg["title"],
            lon_min=cfg["lon_min"],
            lon_max=cfg["lon_max"],
            lat_min=cfg["lat_min"],
            lat_max=cfg["lat_max"],
            projection=cfg.get("projection", "lcc"),
            lon_0=cfg.get("lon_0"),
        )
    return configs


def filter_geodata_to_inset(gdf, inset: InsetConfig, pad_deg: float = 6.0):
    """Entities intersecting the inset's bounds (padded, for surrounding
    geographic context), without mutating `gdf`."""
    combined = unary_union(inset.bbox_polygons(pad_deg))
    mask = gdf.geometry.intersects(combined)
    return gdf[mask]


def compute_frame_xlim_ylim(inset: InsetConfig, crs: str, edge_pad_fraction: float = 0.03):
    """Projects a densified boundary of the inset's configured lon/lat
    rectangle into `crs` and returns ((xmin, xmax), (ymin, ymax)) -- robust
    to projection curvature and to an antimeridian-wrapping frame, since it
    samples many boundary points rather than just the four corners."""
    lon_min_u = inset.unwrap_lon(inset.lon_min)
    lon_max_u = inset.unwrap_lon(inset.lon_max)
    if lon_min_u > lon_max_u:
        lon_max_u += 360

    lons = np.linspace(lon_min_u, lon_max_u, 60)
    lats = np.linspace(inset.lat_min, inset.lat_max, 60)

    pts_lon = list(lons) + list(lons) + [lon_min_u] * len(lats) + [lon_max_u] * len(lats)
    pts_lat = (
        [inset.lat_min] * len(lons)
        + [inset.lat_max] * len(lons)
        + list(lats)
        + list(lats)
    )

    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = transformer.transform(pts_lon, pts_lat)
    xs, ys = np.array(xs), np.array(ys)

    x_pad = (xs.max() - xs.min()) * edge_pad_fraction
    y_pad = (ys.max() - ys.min()) * edge_pad_fraction
    return (xs.min() - x_pad, xs.max() + x_pad), (ys.min() - y_pad, ys.max() + y_pad)
