from matplotlib.figure import Figure

from src.labels import (
    DEFAULT_DISPLAY_TARGET,
    build_marker_report,
    build_placements,
    detect_collisions,
    load_label_offsets,
    resolve_collisions,
)
from src.poster import ROBINSON_CRS, render_world_map
from src.validation import build_validation_report


def test_representative_point_lies_within_geometry(gdf, matcher):
    result = matcher.match("Italy")
    entity_id = result.entity_ids[0]
    geometry = gdf.at[entity_id, "geometry"]
    point = geometry.representative_point()
    assert geometry.contains(point) or geometry.intersects(point)


def test_visit_numbers_preserved_in_placements(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    expected_numbers = {m.number for m in report.mapped}
    actual_numbers = {p.visit_number for p in placements}
    assert actual_numbers == expected_numbers


def test_composite_gets_exactly_one_marker_per_visit_record(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)

    uk_placements = [p for p in placements if p.visit_number == 6]
    assert len(uk_placements) == 1
    assert len(uk_placements[0].entity_ids) == 4  # composite's parts, one marker


def test_scotland_visit_stays_independent_of_uk_composite(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)

    uk = next(p for p in placements if p.visit_number == 6)
    scotland = next(p for p in placements if p.visit_number == 124)

    assert uk.source_name == "United Kingdom"
    assert scotland.source_name == "Scotland"
    assert scotland.entity_ids == [gdf[gdf["NAME"] == "Scotland"].index[0]]
    # Two distinct markers for two distinct chronological visits.
    assert uk.visit_number != scotland.visit_number


def test_virgin_islands_produces_a_placement_with_its_original_number(gdf, default_workbook_path, matcher):
    """Now that 'Virgin Islands' resolves (reconciliation.csv confirmed it
    as the U.S. Virgin Islands), its original old chronological number
    (110) must be preserved exactly -- not renumbered, not dropped."""
    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    vi_placements = [p for p in placements if "virgin" in p.source_name.lower()]
    assert len(vi_placements) == 1
    assert vi_placements[0].visit_number == 110


def test_label_offsets_config_loads():
    offsets = load_label_offsets()
    assert "monaco" in offsets
    assert offsets["monaco"]["display"] == "europe"
    assert "_comment" not in offsets
    assert "_fields" not in offsets


def test_display_assignment_defaults_to_main_and_honors_config(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    by_name = {p.source_name: p for p in placements}

    assert by_name["Iraq"].display_target == DEFAULT_DISPLAY_TARGET
    assert by_name["Monaco"].display_target == "europe"
    assert by_name["Bahrain"].display_target == "gulf"
    assert by_name["Antigua and Barbuda"].display_target == "caribbean"
    assert by_name["Tuvalu"].display_target == "pacific"


def test_collision_detection_identifies_deliberate_overlap():
    import geopandas as gpd
    from shapely.geometry import box

    fake_gdf = gpd.GeoDataFrame(
        {"NAME": ["A", "B", "C"]},
        geometry=[box(0, 0, 1, 1), box(0.9, 0, 1.9, 1), box(50, 50, 51, 51)],
        crs="EPSG:4326",
    )

    class FakeEntry:
        def __init__(self, number, name, entity_id, region=None):
            self.number = number
            self.country_raw = name
            self.entity_ids = [entity_id]
            self.region_raw = region

    entries = [FakeEntry(1, "A", 0), FakeEntry(2, "B", 1), FakeEntry(3, "C", 2)]
    placements = build_placements(fake_gdf, entries, offsets={})
    for p in placements:
        p.x, p.y = p.anchor_lonlat.x, p.anchor_lonlat.y  # skip projection for this synthetic test

    collisions = detect_collisions(placements, marker_radius=1.0, overlap_factor=1.0)
    pairs = {(c.visit_a, c.visit_b) for c in collisions}
    assert (1, 2) in pairs  # A and B are close together -- deliberate overlap
    assert (1, 3) not in pairs  # C is far away -- no collision
    assert (2, 3) not in pairs


def test_resolve_collisions_separates_deliberately_overlapping_pair():
    import geopandas as gpd
    from shapely.geometry import box

    fake_gdf = gpd.GeoDataFrame(
        {"NAME": ["A", "B"]},
        geometry=[box(0, 0, 1, 1), box(0.1, 0, 1.1, 1)],
        crs="EPSG:4326",
    )

    class FakeEntry:
        def __init__(self, number, name, entity_id):
            self.number = number
            self.country_raw = name
            self.entity_ids = [entity_id]
            self.region_raw = None

    entries = [FakeEntry(1, "A", 0), FakeEntry(2, "B", 1)]
    placements = build_placements(fake_gdf, entries, offsets={})
    for p in placements:
        p.x, p.y = p.anchor_lonlat.x, p.anchor_lonlat.y

    remaining, adjustments = resolve_collisions(placements, marker_radius=1.0, overlap_factor=1.0)
    assert remaining == []
    assert len(adjustments) > 0


def test_marker_report_matches_excel_chronology_exactly(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    marker_report = build_marker_report(gdf, report.mapped, crs=ROBINSON_CRS, fig_width_inches=16.0)
    assert {p.visit_number for p in marker_report.placements} == {m.number for m in report.mapped}
    # 21 known-missing numbers must never appear as a marker.
    missing = set(report.missing_numbers)
    assert missing.isdisjoint({p.visit_number for p in marker_report.placements})


def test_renderer_returns_valid_figure_with_markers(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    fig = render_world_map(
        gdf, report.mapped, width=8, height=4, dpi=72, preview=True, show_markers=True
    )
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    # Base polygons (visited/unvisited) as plotted collections.
    assert len(ax.collections) >= 2
    # Markers are drawn as Circle patches (see src/poster.py), sized in
    # true data units so they exactly match collision detection.
    assert len(ax.patches) > 0
