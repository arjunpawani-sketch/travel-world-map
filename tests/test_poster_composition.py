from matplotlib.figure import Figure

from src.poster import render_poster
from src.poster_index import build_index_columns, choose_column_count
from src.poster_layout import load_poster_layout
from src.validation import build_validation_report

BALKAN_NAMES = {
    "Albania", "Bosnia and Herzegovina", "Croatia", "Montenegro",
    "North Macedonia", "Serbia", "Slovenia",
}


def _index_entries(mapped_entries, layout):
    typo = layout.typography
    index_width_in = layout.index.width * layout.page_width_in
    index_height_in = layout.index.height * layout.page_height_in * 0.94
    num_columns = choose_column_count(
        n_entries=len(mapped_entries),
        index_height_in=index_height_in,
        index_width_in=index_width_in,
        font_size_pt=typo.index_font_size,
        line_height_factor=typo.index_line_height_factor,
        min_column_width_in=layout.index_min_column_width * layout.page_width_in,
        column_gap_in=layout.index_column_gap * layout.page_width_in,
    )
    columns = build_index_columns(mapped_entries, num_columns)
    return [entry for col in columns for entry in col], num_columns


def test_every_mapped_visit_appears_exactly_once_in_index(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    layout = load_poster_layout()
    entries, _ = _index_entries(report.mapped, layout)

    index_numbers = [e.number for e in entries]
    expected_numbers = {m.number for m in report.mapped}

    assert len(index_numbers) == len(set(index_numbers))  # no duplicates
    assert set(index_numbers) == expected_numbers  # nothing dropped, nothing invented
    assert len(entries) == report.mapped_count


def test_index_numbers_remain_strictly_chronological(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    layout = load_poster_layout()
    entries, _ = _index_entries(report.mapped, layout)
    numbers = [e.number for e in entries]
    assert numbers == sorted(numbers)


def test_missing_chronology_not_fabricated_in_index(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    layout = load_poster_layout()
    entries, _ = _index_entries(report.mapped, layout)
    index_numbers = {e.number for e in entries}
    assert index_numbers.isdisjoint(set(report.missing_numbers))


def test_unresolved_virgin_islands_not_in_index_or_map(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    layout = load_poster_layout()
    entries, _ = _index_entries(report.mapped, layout)
    assert all("virgin" not in e.name.lower() for e in entries)
    assert any("virgin" in u.country_raw.lower() for u in report.unresolved)  # still tracked as unresolved


def test_balkan_records_assigned_to_europe_inset(gdf, default_workbook_path, matcher):
    from src.labels import build_placements

    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    by_name = {p.source_name: p.display_target for p in placements}
    for name in BALKAN_NAMES:
        assert by_name[name] == "europe", f"{name} should be routed to the Europe inset"


def test_mapped_record_total_unchanged_after_balkan_reassignment(gdf, default_workbook_path, matcher):
    from src.labels import build_placements

    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    assert len(placements) == report.mapped_count
    assert {p.visit_number for p in placements} == {m.number for m in report.mapped}


def test_no_visit_appears_in_two_display_targets(gdf, default_workbook_path, matcher):
    from src.labels import build_placements

    report = build_validation_report(default_workbook_path, gdf, matcher)
    placements = build_placements(gdf, report.mapped)
    seen = {}
    for p in placements:
        assert p.visit_number not in seen
        seen[p.visit_number] = p.display_target


def test_title_count_equals_valid_mapped_record_count(gdf, default_workbook_path, matcher):
    """The poster's subtitle count must be len(mapped_entries), never a
    hard-coded number, and must be unaffected by display-target changes
    (e.g. the Balkan reassignment only moves *where* a visit is drawn)."""
    report = build_validation_report(default_workbook_path, gdf, matcher)
    assert report.mapped_count == len(report.mapped)
    assert report.mapped_count == 183


def test_poster_renderer_returns_valid_figure(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    fig = render_poster(gdf, report.mapped, missing_count=report.missing_count, dpi=60)
    assert isinstance(fig, Figure)
    # title + main map + 4 insets*2 (map+title strip) + index + footer = 12
    assert len(fig.axes) == 12


def test_poster_renderer_does_not_mutate_source_geographic_data(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    original_columns = list(gdf.columns)
    original_len = len(gdf)
    original_wkb = gdf.geometry.apply(lambda g: g.wkb).tolist()

    render_poster(gdf, report.mapped, missing_count=report.missing_count, dpi=60)

    assert list(gdf.columns) == original_columns
    assert len(gdf) == original_len
    assert gdf.geometry.apply(lambda g: g.wkb).tolist() == original_wkb
