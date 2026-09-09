"""
Poster rendering layer.

This module draws the geographic map(s) -- and, from Phase 5 on, the full
A2 poster composition -- that make up the final deliverable. It knows
nothing about Streamlit and nothing about Excel; it only takes already-
validated geographic entities and an already-computed marker placement
plan (src/labels.py) and produces Matplotlib figures.

Phase 2 scope: an accurate world map that distinguishes visited vs.
unvisited land.
Phase 3 scope: chronological numbered markers for entries assigned to the
main map, with optional leader lines and a debug overlay.
Phase 4 scope: regional inset maps (Europe, Gulf & Eastern Mediterranean,
Caribbean & Central America, Oceania & Pacific) using fixed cartographic
bounds and a projection appropriate to each (src/insets.py), reusing the
exact same marker engine, palette, and config as the main map.
Phase 5 scope: `render_poster` composes the main map, all four insets, a
title, a chronological index, and a footer onto one true-A2-sized figure
(src/poster_layout.py, src/poster_index.py) -- still no PDF export.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless rendering, safe for Streamlit and scripts

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from .insets import InsetConfig, compute_frame_xlim_ylim, filter_geodata_to_inset, load_insets
from .labels import DEFAULT_MARKER_RADIUS_POINTS, MarkerReport, build_marker_report
from .poster_index import build_index_columns, choose_column_count
from .poster_layout import PosterLayout, load_poster_layout

ROBINSON_CRS = "+proj=robin +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"

# Palette -- warm, restrained, "old-world travel poster", not a GIS dashboard.
COLOR_BACKGROUND = "#F4EEE1"  # warm ivory / parchment
COLOR_UNVISITED = "#E4DCC9"  # light warm grey / cream
COLOR_VISITED = "#B8933E"  # restrained antique gold

# V1.3: split into two border weights/colors so adjacent visited (gold)
# countries stop visually merging into one block -- the fill colors
# themselves are unchanged. Visited borders are a dark antique bronze,
# distinctly darker than the gold fill; unvisited borders keep the
# original subtle warm tone, kept slightly lighter than visited borders
# as specified.
COLOR_BORDER_VISITED = "#5A4420"  # dark antique bronze -- visible against gold fill
COLOR_BORDER_UNVISITED = "#9C8F72"  # thin, subtle warm border (unchanged from V1.2)
BORDER_LINEWIDTH_VISITED = 0.45
BORDER_LINEWIDTH_UNVISITED = 0.3

COLOR_MARKER_FILL = "#FBF7EC"  # ivory / parchment
COLOR_MARKER_BORDER = "#9C7A24"  # antique gold
COLOR_MARKER_TEXT = "#3B2F1E"  # dark, warm-toned (not pure black)
COLOR_LEADER_LINE = "#8C6D1F"
COLOR_DEBUG_ANCHOR = "#B4383E"
COLOR_DEBUG_COLLISION = "#B4383E"
COLOR_TITLE = "#3B2F1E"
COLOR_RULE = "#9C7A24"
COLOR_MUTED_TEXT = "#6B5F4E"

# Degrees of surrounding geography to keep beyond an inset's configured
# frame, so the crop doesn't destroy geographic context right at the edge.
INSET_CONTEXT_PAD_DEG = 6.0

# Fraction of a standalone inset figure's height reserved for its title
# strip (dead space below the map, never overlapping plotted content).
# render_poster uses PosterLayout.inset_title_height_frac instead.
DEFAULT_INSET_TITLE_HEIGHT_FRAC = 0.1

PENDING_LIST_FONT_SIZE = 7.0  # smaller than the missing-numbers note (8.5pt) -- most secondary text on the poster

MARKER_FONT_SIZE_FACTOR = 0.8  # marker number font size = radius_points * this
# A fixed-radius circle can't grow with the number inside it, so a 3-digit
# visit number (up to 205) is shrunk to keep the glyphs within its own
# circle -- otherwise adjacent markers' numbers visually run together even
# though the circles themselves don't overlap.
DIGIT_FONT_SCALE = {1: 1.0, 2: 1.0, 3: 0.72}


def get_visited_entity_ids(mapped_entries) -> set[int]:
    """Flattens the entity_ids of every mapped entry (composites contribute
    more than one id) into a single set of geographic entity ids to
    highlight. `mapped_entries` is any iterable of objects exposing an
    `entity_ids: list[int]` attribute (see src.validation.MappedEntry)."""
    visited: set[int] = set()
    for entry in mapped_entries:
        visited.update(entry.entity_ids)
    return visited


def split_visited_unvisited(
    geodata: gpd.GeoDataFrame, visited_entity_ids: set[int]
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Splits geodata into (visited, unvisited) subsets by index, without
    modifying geodata itself."""
    mask = geodata.index.isin(visited_entity_ids)
    return geodata[mask], geodata[~mask]


def _plot_base_map(ax, geodata: gpd.GeoDataFrame, visited_ids: set[int]) -> None:
    """Draws the shared visited/unvisited polygon styling. Used by both the
    main map and every inset so they always look like the same system.
    Visited-country borders are drawn distinctly darker than unvisited
    ones so adjacent gold countries don't visually merge into one block."""
    visited_gdf, unvisited_gdf = split_visited_unvisited(geodata, visited_ids)
    if not unvisited_gdf.empty:
        unvisited_gdf.plot(
            ax=ax,
            color=COLOR_UNVISITED,
            edgecolor=COLOR_BORDER_UNVISITED,
            linewidth=BORDER_LINEWIDTH_UNVISITED,
        )
    if not visited_gdf.empty:
        visited_gdf.plot(
            ax=ax,
            color=COLOR_VISITED,
            edgecolor=COLOR_BORDER_VISITED,
            linewidth=BORDER_LINEWIDTH_VISITED,
        )


def _draw_markers(ax, placements, marker_radius_points, marker_radius_data, debug: bool, collisions_after):
    """Draws markers as Circle patches sized directly in data units from
    `marker_radius_data` -- the exact radius the collision system checked
    against (see MarkerReport.marker_radius_data) -- rather than
    Matplotlib's scatter(s=...), whose `s` is marker *area* in points^2,
    not diameter^2; using it naively renders circles ~13% larger than
    intended and silently eats the collision-resolution safety margin."""
    for p in placements:
        if p.leader_line and (p.dx or p.dy):
            ax.plot(
                [p.true_x, p.x],
                [p.true_y, p.y],
                color=COLOR_LEADER_LINE,
                linewidth=0.6,
                zorder=9,
                solid_capstyle="round",
            )

    for p in placements:
        ax.add_patch(
            Circle(
                (p.x, p.y),
                radius=marker_radius_data * p.scale,
                facecolor=COLOR_MARKER_FILL,
                edgecolor=COLOR_MARKER_BORDER,
                linewidth=1.0,
                zorder=10,
            )
        )
        digits = len(str(p.visit_number))
        digit_factor = DIGIT_FONT_SCALE.get(digits, DIGIT_FONT_SCALE[max(DIGIT_FONT_SCALE)])
        ax.annotate(
            str(p.visit_number),
            (p.x, p.y),
            ha="center",
            va="center",
            fontsize=marker_radius_points * MARKER_FONT_SIZE_FACTOR * digit_factor * p.scale,
            fontweight="bold",
            color=COLOR_MARKER_TEXT,
            zorder=11,
        )

    if debug:
        if placements:
            ax.scatter(
                [p.true_x for p in placements],
                [p.true_y for p in placements],
                s=6,
                color=COLOR_DEBUG_ANCHOR,
                marker="x",
                linewidth=0.8,
                zorder=12,
            )
        by_visit = {p.visit_number: p for p in placements}
        for c in collisions_after:
            pa, pb = by_visit.get(c.visit_a), by_visit.get(c.visit_b)
            if pa is None or pb is None:
                continue
            ax.plot(
                [pa.x, pb.x],
                [pa.y, pb.y],
                color=COLOR_DEBUG_COLLISION,
                linewidth=1.2,
                linestyle="--",
                zorder=13,
            )


def _render_main_map_onto_ax(
    ax,
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    fig_width_inches: float,
    show_markers: bool = True,
    marker_report: MarkerReport | None = None,
    label_offsets: dict | None = None,
    marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS,
    debug_markers: bool = False,
    extra_visited_entity_ids: set[int] | None = None,
) -> MarkerReport | None:
    """Draws the main world map's polygons and (optionally) markers onto an
    existing Axes. Shared by `render_world_map` (its own figure) and
    `render_poster` (one panel of the full composition) so the two never
    drift apart.

    `extra_visited_entity_ids`, if given, is unioned into the highlighted
    (gold) set on top of whatever `mapped_entries` implies -- e.g. visits
    confirmed by reconciliation.csv but without an established
    chronological number, which should be highlighted as visited without
    ever getting a numbered marker (those come only from `mapped_entries`,
    unaffected by this parameter)."""
    visited_ids = get_visited_entity_ids(mapped_entries)
    if extra_visited_entity_ids:
        visited_ids = visited_ids | set(extra_visited_entity_ids)
    projected = geodata.to_crs(ROBINSON_CRS)
    _plot_base_map(ax, projected, visited_ids)

    if show_markers:
        if marker_report is None:
            marker_report = build_marker_report(
                geodata,
                mapped_entries,
                crs=ROBINSON_CRS,
                fig_width_inches=fig_width_inches,
                target_display="main",
                offsets=label_offsets,
                marker_radius_points=marker_radius_points,
            )
        _draw_markers(
            ax,
            marker_report.target_placements,
            marker_radius_points,
            marker_report.marker_radius_data,
            debug_markers,
            marker_report.collisions_after,
        )

    ax.set_axis_off()
    ax.set_aspect("equal")
    return marker_report


def render_world_map(
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    width: float = 16.0,
    height: float = 8.0,
    dpi: int = 150,
    preview: bool = True,
    show_markers: bool = False,
    marker_report: MarkerReport | None = None,
    label_offsets: dict | None = None,
    marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS,
    debug_markers: bool = False,
    extra_visited_entity_ids: set[int] | None = None,
) -> Figure:
    """
    Renders the main world map: visited entities in antique gold, unvisited
    land in light cream, on a warm parchment background. Robinson
    projection.

    `geodata` is never mutated -- a reprojected copy is used internally.
    `mapped_entries` is any iterable of objects exposing `entity_ids`
    (typically `ValidationReport.mapped`, a list of MappedEntry).

    `show_markers=True` draws chronological numbered markers for every
    visit assigned to the main map (see src/labels.py); entries assigned
    to a regional inset are intentionally not drawn here -- see
    `render_inset_map`. Pass an already-built `marker_report` to reuse one
    computed elsewhere (e.g. to print stats) instead of rebuilding it;
    otherwise one is built internally from `label_offsets` (or the on-disk
    default). `debug_markers=True` additionally overlays true anchor
    points and any unresolved collisions. `extra_visited_entity_ids`
    highlights additional confirmed-visited geography with no numbered
    marker (see `_render_main_map_onto_ax`).

    `preview=True` uses a lower default DPI suitable for on-screen review;
    pass `preview=False` with a higher `dpi` for print-quality output in
    later phases.
    """
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor(COLOR_BACKGROUND)
    ax.set_facecolor(COLOR_BACKGROUND)

    _render_main_map_onto_ax(
        ax,
        geodata,
        mapped_entries,
        fig_width_inches=width,
        show_markers=show_markers,
        marker_report=marker_report,
        label_offsets=label_offsets,
        marker_radius_points=marker_radius_points,
        debug_markers=debug_markers,
        extra_visited_entity_ids=extra_visited_entity_ids,
    )

    fig.tight_layout(pad=0)
    return fig


def _render_inset_onto_ax(
    ax,
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    inset: InsetConfig,
    fig_width_inches: float,
    show_markers: bool = True,
    marker_report: MarkerReport | None = None,
    label_offsets: dict | None = None,
    marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS,
    debug_markers: bool = False,
    show_title: bool = True,
    title_font_size: float = 11,
    title_ax=None,
    extra_visited_entity_ids: set[int] | None = None,
) -> MarkerReport | None:
    """Draws one regional inset's polygons and markers onto an existing
    Axes, and its title into a *separate* `title_ax` when given. Shared by
    `render_inset_map` and `render_poster`.

    The title is deliberately drawn outside the map's own plotted data
    area (in `title_ax`, dead space reserved by the caller -- see
    PosterLayout.Zone.split_bottom_strip) rather than overlaid on the map
    near its edge, so it can never collide with a marker that happens to
    sit near the frame's bottom -- e.g. Malta on the Europe inset. If
    `title_ax` is omitted, falls back to drawing inside `ax` itself for
    simple standalone use. `extra_visited_entity_ids` -- see
    `_render_main_map_onto_ax`."""
    crs = inset.crs()
    context_gdf = filter_geodata_to_inset(geodata, inset, pad_deg=INSET_CONTEXT_PAD_DEG)
    projected = context_gdf.to_crs(crs)

    xlim, ylim = compute_frame_xlim_ylim(inset, crs)
    data_width = xlim[1] - xlim[0]

    visited_ids = get_visited_entity_ids(mapped_entries)
    if extra_visited_entity_ids:
        visited_ids = visited_ids | set(extra_visited_entity_ids)
    _plot_base_map(ax, projected, visited_ids)

    if show_markers:
        if marker_report is None:
            marker_report = build_marker_report(
                geodata,
                mapped_entries,
                crs=crs,
                fig_width_inches=fig_width_inches,
                data_width=data_width,
                target_display=inset.key,
                offsets=label_offsets,
                marker_radius_points=marker_radius_points,
            )
        _draw_markers(
            ax,
            marker_report.target_placements,
            marker_radius_points,
            marker_report.marker_radius_data,
            debug_markers,
            marker_report.collisions_after,
        )

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_axis_off()
    ax.set_aspect("equal")

    if show_title:
        if title_ax is not None:
            title_ax.axis("off")
            title_ax.text(
                0.5, 0.5, inset.title,
                transform=title_ax.transAxes,
                ha="center", va="center",
                fontsize=title_font_size, fontweight="bold",
                family="serif", color=COLOR_TITLE,
            )
        else:
            ax.text(
                0.5, 0.02, inset.title,
                transform=ax.transAxes,
                ha="center", va="bottom",
                fontsize=title_font_size, fontweight="bold",
                family="serif", color=COLOR_TITLE,
            )

    return marker_report


def render_inset_map(
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    inset: InsetConfig,
    width: float = 8.0,
    height: float = 6.0,
    dpi: int = 150,
    show_markers: bool = True,
    marker_report: MarkerReport | None = None,
    label_offsets: dict | None = None,
    marker_radius_points: float = DEFAULT_MARKER_RADIUS_POINTS,
    debug_markers: bool = False,
    show_title: bool = True,
    extra_visited_entity_ids: set[int] | None = None,
) -> Figure:
    """
    Renders one regional inset map: the same visited/unvisited palette and
    marker engine as `render_world_map`, cropped to `inset`'s fixed
    cartographic bounds and projected with the CRS `inset` specifies (see
    src/insets.py). Only markers whose `display_target` equals `inset.key`
    are drawn -- e.g. the Europe inset never draws a main-map marker.

    `geodata` is never mutated. Bounds are read from `inset`, not derived
    from whichever entries happen to be visited, so an updated Excel file
    changes what's highlighted without changing the frame.
    """
    fig = plt.figure(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor(COLOR_BACKGROUND)

    title_h = DEFAULT_INSET_TITLE_HEIGHT_FRAC if show_title else 0.0
    ax = fig.add_axes([0.0, title_h, 1.0, 1.0 - title_h])
    ax.set_facecolor(COLOR_BACKGROUND)
    title_ax = fig.add_axes([0.0, 0.0, 1.0, title_h]) if show_title else None

    _render_inset_onto_ax(
        ax,
        geodata,
        mapped_entries,
        inset,
        fig_width_inches=width,
        show_markers=show_markers,
        marker_report=marker_report,
        label_offsets=label_offsets,
        marker_radius_points=marker_radius_points,
        debug_markers=debug_markers,
        show_title=show_title,
        title_ax=title_ax,
        extra_visited_entity_ids=extra_visited_entity_ids,
    )

    return fig


def render_all_insets(
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    insets: dict[str, InsetConfig] | None = None,
    width: float = 8.0,
    height: float = 6.0,
    dpi: int = 150,
    label_offsets: dict | None = None,
    debug_markers: bool = False,
    extra_visited_entity_ids: set[int] | None = None,
) -> dict[str, Figure]:
    """Renders every configured inset (data/insets.json by default) and
    returns {inset_key: Figure}."""
    if insets is None:
        insets = load_insets()
    return {
        key: render_inset_map(
            geodata,
            mapped_entries,
            inset,
            width=width,
            height=height,
            dpi=dpi,
            label_offsets=label_offsets,
            debug_markers=debug_markers,
            extra_visited_entity_ids=extra_visited_entity_ids,
        )
        for key, inset in insets.items()
    }


def _draw_title_block(ax, mapped_count: int, typo) -> None:
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(
        0.5, 0.62, "COUNTRIES VISITED",
        ha="center", va="center",
        fontsize=typo.title_font_size, fontweight="bold",
        family=typo.title_font_family, color=COLOR_TITLE,
    )
    ax.text(
        0.5, 0.28, f"{mapped_count} countries and territories visited",
        ha="center", va="center",
        fontsize=typo.subtitle_font_size,
        family=typo.body_font_family, color=COLOR_TITLE,
    )
    ax.text(
        0.5, 0.03, "Numbered chronologically",
        ha="center", va="center",
        fontsize=typo.secondary_font_size, style="italic",
        family=typo.body_font_family, color=COLOR_MUTED_TEXT,
    )
    ax.axhline(0.17, color=COLOR_RULE, linewidth=0.8, xmin=0.38, xmax=0.62)


def _draw_index_block(ax, mapped_entries, layout: PosterLayout, missing_count: int) -> int:
    """Draws the chronological index into `ax` (its own 0-1 axes
    coordinate space). Returns the number of columns used."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    typo = layout.typography
    index_zone = layout.index
    index_width_in = index_zone.width * layout.page_width_in
    index_height_in = index_zone.height * layout.page_height_in
    reserved_bottom_fraction = layout.index_missing_note_reserved_fraction  # room for the missing-numbers note
    usable_height_in = index_height_in * (1 - reserved_bottom_fraction)

    n = len(mapped_entries)
    num_columns = choose_column_count(
        n_entries=n,
        index_height_in=usable_height_in,
        index_width_in=index_width_in,
        font_size_pt=typo.index_font_size,
        line_height_factor=typo.index_line_height_factor,
        min_column_width_in=layout.index_min_column_width * layout.page_width_in,
        column_gap_in=layout.index_column_gap * layout.page_width_in,
    )
    columns = build_index_columns(mapped_entries, num_columns)

    gap_frac = layout.index_column_gap / index_zone.width if index_zone.width else 0
    col_width_frac = (1 - gap_frac * (num_columns - 1)) / num_columns

    row_height_axesfrac = (typo.index_font_size * typo.index_line_height_factor / 72.0) / (
        index_height_in
    )

    for col_idx, column in enumerate(columns):
        x = col_idx * (col_width_frac + gap_frac)
        y = 1.0
        for entry in column:
            y -= row_height_axesfrac
            ax.text(
                x, y, str(entry.number),
                ha="right", va="top",
                fontsize=typo.index_font_size, fontweight="bold",
                family=typo.body_font_family, color=COLOR_VISITED,
                transform=ax.transAxes,
            )
            ax.text(
                x + 0.012, y, entry.name,
                ha="left", va="top",
                fontsize=typo.index_font_size,
                family=typo.body_font_family, color=COLOR_TITLE,
                transform=ax.transAxes,
            )

    if missing_count:
        ax.text(
            0.5, 0.02,
            f"{missing_count} chronological numbers (within 1-205) remain unresolved in source records.",
            ha="center", va="bottom",
            fontsize=typo.missing_note_font_size, style="italic",
            family=typo.body_font_family, color=COLOR_MUTED_TEXT,
            transform=ax.transAxes,
        )

    return num_columns


def _draw_footer_block(ax, typo, pending_names: list[str] | None = None) -> None:
    """`pending_names`, if given, adds one small, clearly-secondary line
    listing confirmed-visited places whose chronological position isn't
    established yet -- see PENDING_LIST_FONT_SIZE. Placed within the
    footer zone's existing physical size (not changing V1.2's layout
    proportions); only the footer's own internal spacing shifts slightly
    to make room."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    main_line_y = 0.55 if pending_names else 0.35
    ax.axhline(0.85, color=COLOR_RULE, linewidth=0.6, xmin=0.42, xmax=0.58)
    ax.text(
        0.5, main_line_y, "Every journey tells a story.",
        ha="center", va="center",
        fontsize=typo.footer_font_size, style="italic",
        family=typo.title_font_family, color=COLOR_MUTED_TEXT,
    )

    if pending_names:
        names_text = ", ".join(sorted(pending_names)) + "."
        ax.text(
            0.5, 0.12,
            f"Additional confirmed visits, chronology pending: {names_text}",
            ha="center", va="center",
            fontsize=PENDING_LIST_FONT_SIZE, style="italic",
            family=typo.body_font_family, color=COLOR_MUTED_TEXT,
        )


def render_poster(
    geodata: gpd.GeoDataFrame,
    mapped_entries,
    missing_count: int = 0,
    insets: dict[str, InsetConfig] | None = None,
    layout: PosterLayout | None = None,
    label_offsets: dict | None = None,
    marker_reports: dict[str, MarkerReport] | None = None,
    dpi: float = 150,
    debug_markers: bool = False,
    visited_count: int | None = None,
    extra_visited_entity_ids: set[int] | None = None,
    pending_names: list[str] | None = None,
) -> Figure:
    """
    Composes the full A2 landscape poster: title, main world map, the four
    regional insets, the chronological country/territory index, and a
    footer -- all on one true-physical-size Matplotlib figure (see
    data/poster_layout.json for exact dimensions and zone placement).

    `geodata` is never mutated. `mapped_entries` is the full list of valid
    CHRONOLOGICALLY-NUMBERED visit records (typically
    `ValidationReport.mapped`) -- every numbered marker and every index
    entry comes from this list, never hard-coded.

    `visited_count`, if given, overrides the title's "N countries and
    territories visited" figure -- e.g. a merged confirmed-visited count
    that includes entries with no established chronology yet. Defaults to
    `len(mapped_entries)` when omitted (V1.2 behavior, unchanged).

    `extra_visited_entity_ids`, if given, additionally highlights that
    geography as visited (gold fill) on the main map and every inset,
    without drawing a numbered marker for it -- see
    `_render_main_map_onto_ax`.

    `pending_names`, if given, adds a small, clearly secondary
    "Additional confirmed visits, chronology pending" line to the footer
    -- see `_draw_footer_block`. None of this changes the V1.2 zone sizes
    (title/main_map/insets_row/index/footer stay exactly as configured in
    data/poster_layout.json).

    `missing_count` (typically `ValidationReport.missing_count`) drives
    the small "N chronological numbers unresolved" note; pass 0 to omit
    it.

    Pass `marker_reports` (a dict with keys "main", "europe", "gulf",
    "caribbean", "pacific") to reuse already-built reports -- e.g. so a
    caller can print collision stats that are guaranteed to match exactly
    what's drawn -- otherwise each panel builds its own internally.
    """
    layout = layout or load_poster_layout()
    insets = insets if insets is not None else load_insets()
    marker_reports = marker_reports or {}
    typo = layout.typography

    fig = plt.figure(figsize=(layout.page_width_in, layout.page_height_in), dpi=dpi)
    fig.patch.set_facecolor(COLOR_BACKGROUND)

    mapped_list = list(mapped_entries)
    title_count = visited_count if visited_count is not None else len(mapped_list)

    title_ax = fig.add_axes(layout.title.as_rect())
    _draw_title_block(title_ax, title_count, typo)

    main_ax = fig.add_axes(layout.main_map.as_rect())
    main_ax.set_facecolor(COLOR_BACKGROUND)
    _render_main_map_onto_ax(
        main_ax,
        geodata,
        mapped_list,
        fig_width_inches=layout.main_map.width * layout.page_width_in,
        marker_report=marker_reports.get("main"),
        label_offsets=label_offsets,
        marker_radius_points=typo.main_marker_radius_points,
        debug_markers=debug_markers,
        extra_visited_entity_ids=extra_visited_entity_ids,
    )

    inset_rects = layout.inset_rects()
    for key in layout.inset_order:
        rect = inset_rects[key]
        map_zone, title_zone = rect.split_bottom_strip(layout.inset_title_height_frac)
        ax = fig.add_axes(map_zone.as_rect())
        ax.set_facecolor(COLOR_BACKGROUND)
        title_ax = fig.add_axes(title_zone.as_rect())
        _render_inset_onto_ax(
            ax,
            geodata,
            mapped_list,
            insets[key],
            fig_width_inches=rect.width * layout.page_width_in,
            marker_report=marker_reports.get(key),
            label_offsets=label_offsets,
            marker_radius_points=typo.inset_marker_radius_points,
            debug_markers=debug_markers,
            title_font_size=typo.inset_title_font_size,
            title_ax=title_ax,
            extra_visited_entity_ids=extra_visited_entity_ids,
        )

    index_ax = fig.add_axes(layout.index.as_rect())
    _draw_index_block(index_ax, mapped_list, layout, missing_count)

    footer_ax = fig.add_axes(layout.footer.as_rect())
    _draw_footer_block(footer_ax, typo, pending_names=pending_names)

    return fig
