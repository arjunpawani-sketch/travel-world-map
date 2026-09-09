from matplotlib.figure import Figure

from src.insets import (
    InsetConfig,
    compute_frame_xlim_ylim,
    filter_geodata_to_inset,
    load_insets,
)
from src.labels import build_marker_report
from src.poster import render_all_insets, render_inset_map
from src.validation import build_validation_report

EXPECTED_KEYS = {"europe", "gulf", "caribbean", "pacific"}


def test_each_configured_inset_loads_correctly():
    insets = load_insets()
    assert set(insets.keys()) == EXPECTED_KEYS
    for key, inset in insets.items():
        assert inset.key == key
        assert inset.title
        assert inset.projection in {"lcc", "mercator", "eqc"}


def test_deterministic_bounds_independent_of_visited_entries():
    """Bounds come only from data/insets.json, never from which entries
    happen to be visited -- loading twice must be identical."""
    a = load_insets()
    b = load_insets()
    for key in EXPECTED_KEYS:
        assert a[key].lon_min == b[key].lon_min
        assert a[key].lon_max == b[key].lon_max
        assert a[key].lat_min == b[key].lat_min
        assert a[key].lat_max == b[key].lat_max


def test_pacific_inset_wraps_antimeridian_with_explicit_lon_0():
    insets = load_insets()
    pacific = insets["pacific"]
    assert pacific.wraps_antimeridian
    assert pacific.lon_0 == 170


def test_frame_xlim_ylim_is_ordered_and_finite():
    insets = load_insets()
    for inset in insets.values():
        crs = inset.crs()
        xlim, ylim = compute_frame_xlim_ylim(inset, crs)
        assert xlim[0] < xlim[1]
        assert ylim[0] < ylim[1]


def test_correct_visit_entries_included_in_each_inset(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    from src.labels import build_placements

    placements = build_placements(gdf, report.mapped)
    by_display = {}
    for p in placements:
        by_display.setdefault(p.display_target, []).append(p.source_name)

    assert "Monaco" in by_display["europe"]
    assert "Bahrain" in by_display["gulf"]
    assert "Antigua and Barbuda" in by_display["caribbean"]
    assert "Tuvalu" in by_display["pacific"]
    assert set(by_display["europe"]) == {
        "Monaco", "San Marino", "Holy See / Vatican City", "Liechtenstein",
        "Andorra", "Malta", "Luxembourg", "Kosovo",
        "Albania", "Bosnia and Herzegovina", "Croatia", "Montenegro",
        "North Macedonia", "Serbia", "Slovenia",
    }
    assert set(by_display["gulf"]) == {"Bahrain", "Qatar", "Kuwait", "Cyprus", "Lebanon"}


def test_entries_do_not_appear_in_more_than_one_inset(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    from src.labels import build_placements

    placements = build_placements(gdf, report.mapped)
    seen = {}
    for p in placements:
        assert p.visit_number not in seen, (
            f"visit #{p.visit_number} appeared under both "
            f"{seen.get(p.visit_number)} and {p.display_target}"
        )
        seen[p.visit_number] = p.display_target


def test_chronological_numbers_preserved_in_each_inset(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    insets = load_insets()
    excel_numbers = {m.number for m in report.mapped}

    for key, inset in insets.items():
        crs = inset.crs()
        xlim, _ = compute_frame_xlim_ylim(inset, crs)
        marker_report = build_marker_report(
            gdf, report.mapped, crs=crs, fig_width_inches=10.0,
            data_width=xlim[1] - xlim[0], target_display=key,
        )
        numbers = {p.visit_number for p in marker_report.target_placements}
        assert numbers.issubset(excel_numbers)
        assert numbers.isdisjoint(set(report.missing_numbers))


def test_anchor_geometry_lies_within_relevant_context(gdf):
    insets = load_insets()
    monaco_id = gdf[gdf["NAME"] == "Monaco"].index[0]
    europe_ctx = filter_geodata_to_inset(gdf, insets["europe"], pad_deg=6.0)
    assert monaco_id in europe_ctx.index


def test_leader_line_config_defaults_and_override():
    from src.labels import build_placements

    class FakeEntry:
        def __init__(self, number, name, entity_id, region=None):
            self.number = number
            self.country_raw = name
            self.entity_ids = [entity_id]
            self.region_raw = region

    import geopandas as gpd
    from shapely.geometry import box

    fake_gdf = gpd.GeoDataFrame(
        {"NAME": ["Testland"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326"
    )
    offsets = {
        "testland": {
            "display": "europe",
            "europe": {"dx": 2.0, "dy": 1.0, "leader_line": True},
        }
    }
    placements = build_placements(fake_gdf, [FakeEntry(1, "Testland", 0)], offsets=offsets)
    assert placements[0].dx == 2.0
    assert placements[0].leader_line is True

    offsets_no_flag = {"testland": {"display": "europe", "europe": {"dx": 2.0, "dy": 0.0}}}
    placements2 = build_placements(fake_gdf, [FakeEntry(1, "Testland", 0)], offsets=offsets_no_flag)
    assert placements2[0].leader_line is True  # defaults True when dx/dy nonzero


def test_collision_detection_within_inset(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    insets = load_insets()
    caribbean = insets["caribbean"]
    crs = caribbean.crs()
    xlim, _ = compute_frame_xlim_ylim(caribbean, crs)
    marker_report = build_marker_report(
        gdf, report.mapped, crs=crs, fig_width_inches=10.0,
        data_width=xlim[1] - xlim[0], target_display="caribbean",
    )
    # Just needs to run without error and produce a well-formed (possibly
    # empty) report -- the real Caribbean data has a known close pair
    # (Dominica/Guadeloupe) that should auto-resolve.
    assert isinstance(marker_report.collisions_before, list)
    assert marker_report.collisions_after == []


def test_render_inset_map_returns_valid_figure(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    insets = load_insets()
    fig = render_inset_map(gdf, report.mapped, insets["europe"], width=6, height=5, dpi=72)
    assert isinstance(fig, Figure)
    # Map axes + a separate title-strip axes (see split_bottom_strip) so
    # the title can never overlap a marker near the frame's bottom edge.
    assert len(fig.axes) == 2


def test_render_all_insets_returns_all_four(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    figs = render_all_insets(gdf, report.mapped, width=4, height=3, dpi=72)
    assert set(figs.keys()) == EXPECTED_KEYS
    for fig in figs.values():
        assert isinstance(fig, Figure)


def test_inset_rendering_does_not_mutate_source_geographic_data(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    insets = load_insets()
    original_columns = list(gdf.columns)
    original_len = len(gdf)
    original_wkb = gdf.geometry.apply(lambda g: g.wkb).tolist()

    render_inset_map(gdf, report.mapped, insets["gulf"], width=6, height=5, dpi=72)

    assert list(gdf.columns) == original_columns
    assert len(gdf) == original_len
    assert gdf.geometry.apply(lambda g: g.wkb).tolist() == original_wkb
