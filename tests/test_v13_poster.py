"""
V1.3-specific poster rendering tests: the extra confirmed-visited
highlighting (no numbered marker), Antarctica not affecting the hero
map's framing, and the border-visibility fix.
"""
import numpy as np

from src.poster import (
    COLOR_BORDER_UNVISITED,
    COLOR_BORDER_VISITED,
    render_world_map,
)
from src.reconciliation import build_merged_reconciliation
from src.validation import build_validation_report


def _merged(gdf, default_workbook_path, matcher):
    old_report = build_validation_report(default_workbook_path, gdf, matcher)
    return build_merged_reconciliation(old_report, matcher)


def test_antarctica_resolves_and_is_in_pending_entity_ids(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    antarctica = next((e for e in merged.entries if e.name == "Antarctica"), None)
    assert antarctica is not None
    assert antarctica.entity_ids
    assert set(antarctica.entity_ids).issubset(merged.pending_entity_ids())


def test_antarctica_does_not_change_hero_map_framing(gdf, default_workbook_path, matcher):
    """The main map's frame is always the full world's Robinson bounds,
    independent of which entities happen to be highlighted -- adding
    Antarctica to extra_visited_entity_ids must not change the axes
    limits at all."""
    merged = _merged(gdf, default_workbook_path, matcher)

    fig_without = render_world_map(gdf, merged.numbered_entries, width=8, height=4, dpi=72)
    ax_without = fig_without.axes[0]
    xlim_without, ylim_without = ax_without.get_xlim(), ax_without.get_ylim()

    fig_with = render_world_map(
        gdf,
        merged.numbered_entries,
        width=8,
        height=4,
        dpi=72,
        extra_visited_entity_ids=merged.pending_entity_ids(),
    )
    ax_with = fig_with.axes[0]
    xlim_with, ylim_with = ax_with.get_xlim(), ax_with.get_ylim()

    assert np.allclose(xlim_without, xlim_with)
    assert np.allclose(ylim_without, ylim_with)


def test_pending_entities_highlighted_without_numbered_marker(gdf, default_workbook_path, matcher):
    """Confirmed-visited-but-chronology-pending geography gets the gold
    fill (via extra_visited_entity_ids) but never a Circle marker, since
    markers are only ever built from the old-source mapped entries
    (chronologically known) -- exactly as the real render pipeline does
    (see scripts/render_v13_export.py and app.py, which build markers
    from `old_report.mapped`, not from `ReconciledEntry` objects, and
    pass `extra_visited_entity_ids` purely for highlighting). Adding the
    ~21 pending entity ids to the highlight set must not add a single
    extra Circle patch to the rendered map."""
    from src.poster import get_visited_entity_ids

    old_report = build_validation_report(default_workbook_path, gdf, matcher)
    merged = build_merged_reconciliation(old_report, matcher)
    numbered_ids = get_visited_entity_ids(old_report.mapped)
    pending_ids = merged.pending_entity_ids()
    assert pending_ids, "fixture assumption: there should be pending entries"
    assert pending_ids - numbered_ids, "pending entities must add NEW highlighted geography"

    fig_without = render_world_map(
        gdf, old_report.mapped, width=8, height=4, dpi=72, show_markers=True,
    )
    fig_with = render_world_map(
        gdf,
        old_report.mapped,
        width=8,
        height=4,
        dpi=72,
        show_markers=True,
        extra_visited_entity_ids=pending_ids,
    )
    patches_without = len(fig_without.axes[0].patches)
    patches_with = len(fig_with.axes[0].patches)
    assert patches_without > 0, "fixture assumption: main map should have some numbered markers"
    assert patches_with == patches_without


def test_border_colors_are_distinct_and_visited_is_darker(gdf, default_workbook_path, matcher):
    """The approved V1.3 visual change: visited-country borders must be a
    distinctly different (darker) color from unvisited ones, and fills
    must remain unchanged from V1.2."""
    from src.poster import COLOR_UNVISITED, COLOR_VISITED

    assert COLOR_BORDER_VISITED != COLOR_BORDER_UNVISITED

    def _hex_to_luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        return 0.299 * r + 0.587 * g + 0.114 * b

    assert _hex_to_luminance(COLOR_BORDER_VISITED) < _hex_to_luminance(COLOR_BORDER_UNVISITED)
    # Fills unchanged from V1.2.
    assert COLOR_VISITED == "#B8933E"
    assert COLOR_UNVISITED == "#E4DCC9"


def test_border_rendering_present_on_main_map(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    fig = render_world_map(gdf, report.mapped, width=8, height=4, dpi=72, show_markers=False)
    ax = fig.axes[0]
    assert len(ax.collections) >= 2  # visited + unvisited polygon collections

    from matplotlib.colors import to_hex

    edge_colors_seen = set()
    for coll in ax.collections:
        edgecolors = coll.get_edgecolor()
        if len(edgecolors):
            edge_colors_seen.add(to_hex(edgecolors[0]))
    assert to_hex(COLOR_BORDER_VISITED) in edge_colors_seen
    assert to_hex(COLOR_BORDER_UNVISITED) in edge_colors_seen
