"""
Poster composition layout: loads data/poster_layout.json into typed,
editable settings. Physical page size, zone rectangles, and typography
sizes live in that file, not scattered as magic numbers through
src/poster.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTER_LAYOUT_PATH = PROJECT_ROOT / "data" / "poster_layout.json"

MM_PER_INCH = 25.4


@dataclass
class Zone:
    """A rectangle in Matplotlib figure-fraction coordinates, origin at
    the bottom-left of the page (Matplotlib's native convention)."""
    x: float
    y: float
    width: float
    height: float

    def as_rect(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]

    def split_bottom_strip(self, strip_height_frac: float) -> tuple["Zone", "Zone"]:
        """Splits into (main_zone, bottom_strip_zone), the strip being the
        bottom `strip_height_frac` of this zone's own height -- e.g. to
        reserve dead space for a title so it can never overlap plotted
        content, regardless of what the data looks like."""
        strip_height = self.height * strip_height_frac
        strip = Zone(x=self.x, y=self.y, width=self.width, height=strip_height)
        main = Zone(x=self.x, y=self.y + strip_height, width=self.width, height=self.height - strip_height)
        return main, strip


@dataclass
class Typography:
    title_font_size: float = 40
    subtitle_font_size: float = 17
    secondary_font_size: float = 12
    inset_title_font_size: float = 13
    index_font_size: float = 7.6
    index_line_height_factor: float = 1.55
    footer_font_size: float = 10.5
    missing_note_font_size: float = 8.5
    main_marker_radius_points: float = 8.5
    inset_marker_radius_points: float = 8.0
    title_font_family: str = "serif"
    body_font_family: str = "sans-serif"


@dataclass
class PosterLayout:
    page_width_mm: float
    page_height_mm: float
    title: Zone
    main_map: Zone
    insets_row: Zone
    index: Zone
    footer: Zone
    inset_width_weights: dict[str, float]
    inset_gap: float
    inset_order: list[str]
    inset_title_height_frac: float
    typography: Typography
    index_column_gap: float
    index_min_column_width: float
    index_missing_note_reserved_fraction: float = 0.06

    @property
    def page_width_in(self) -> float:
        return self.page_width_mm / MM_PER_INCH

    @property
    def page_height_in(self) -> float:
        return self.page_height_mm / MM_PER_INCH

    def inset_rects(self) -> dict[str, Zone]:
        """Splits the insets_row zone into one rect per inset, widths
        weighted by inset_width_weights, left-to-right in inset_order."""
        n = len(self.inset_order)
        total_gap = self.inset_gap * (n - 1)
        content_width = self.insets_row.width - total_gap
        total_weight = sum(self.inset_width_weights.get(k, 1.0) for k in self.inset_order)

        rects = {}
        x = self.insets_row.x
        for key in self.inset_order:
            weight = self.inset_width_weights.get(key, 1.0)
            width = content_width * (weight / total_weight)
            rects[key] = Zone(x=x, y=self.insets_row.y, width=width, height=self.insets_row.height)
            x += width + self.inset_gap
        return rects


def _zone_from_dict(raw: dict, margins: dict, page_width: float = 1.0) -> Zone:
    left = margins["left"]
    right = margins["right"]
    width = 1.0 - left - right
    return Zone(x=left, y=raw["y"], width=width, height=raw["height"])


def load_poster_layout(path: Path | None = None) -> PosterLayout:
    path = path or POSTER_LAYOUT_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    margins = raw["margins"]
    zones = raw["zones"]

    return PosterLayout(
        page_width_mm=raw["page"]["width_mm"],
        page_height_mm=raw["page"]["height_mm"],
        title=_zone_from_dict(zones["title"], margins),
        main_map=_zone_from_dict(zones["main_map"], margins),
        insets_row=_zone_from_dict(zones["insets_row"], margins),
        index=_zone_from_dict(zones["index"], margins),
        footer=_zone_from_dict(zones["footer"], margins),
        inset_width_weights=raw["inset_width_weights"],
        inset_gap=raw["inset_gap"],
        inset_order=raw["inset_order"],
        inset_title_height_frac=raw["inset_title_height_frac"],
        typography=Typography(**raw["typography"]),
        index_column_gap=raw["index_column_gap"],
        index_min_column_width=raw["index_min_column_width"],
        index_missing_note_reserved_fraction=raw.get("index_missing_note_reserved_fraction", 0.06),
    )
