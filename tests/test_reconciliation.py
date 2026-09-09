from src.reconciliation import build_merged_reconciliation

NEW_19_COUNTRIES = {
    "Antarctica", "Tunisia", "Afghanistan", "Kazakhstan", "Canada", "Russia",
    "Panama", "Georgia", "Libya", "United States", "Cabo Verde", "Algeria",
    "Philippines", "Costa Rica", "Nepal", "Togo", "Saint Lucia", "Tajikistan",
    "Mexico",
}

MISSING_NUMBERS = {7, 23, 46, 67, 71, 74, 82, 83, 96, 105, 106, 107, 131, 147, 155, 190, 192, 193, 196, 198, 202}


def _merged(gdf, default_workbook_path, matcher):
    from src.validation import build_validation_report

    old_report = build_validation_report(default_workbook_path, gdf, matcher)
    return build_merged_reconciliation(old_report, matcher)


def test_merged_unique_confirmed_visited_count(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    # Calculated, not assumed: 184 old-source (Virgin Islands now resolves)
    # + 19 clean new-only + Belgium + Palestine (both fixed via composite).
    assert merged.confirmed_visited_count == 205
    assert merged.confirmed_visited_count == len(merged.entries)


def test_headline_count_equals_merged_confirmed_visited(gdf, default_workbook_path, matcher):
    """No double-counting, no gaps: numbered + pending must equal the total."""
    merged = _merged(gdf, default_workbook_path, matcher)
    assert merged.numbered_count + merged.pending_count == merged.confirmed_visited_count


def test_geographically_unresolved_is_empty_after_fixes(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    assert merged.geographically_unresolved_count == 0
    assert merged.unresolved == []


def test_israel_retained_from_old_source_and_flagged_internally(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    israel = next((e for e in merged.entries if e.name == "Israel"), None)
    assert israel is not None, "Israel must not be silently removed"
    assert israel.chronology_known is True
    assert israel.visit_number == 77  # unchanged, established old number
    assert israel.source_old_index is True
    assert israel.source_reconciliation is False  # absent from reconciliation.csv
    assert israel.internal_note is not None
    assert "absent from latest reconciliation source" in israel.internal_note


def test_us_virgin_islands_resolves_and_keeps_old_number(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    vi_entries = [e for e in merged.entries if "virgin" in e.name.lower()]
    assert len(vi_entries) == 1
    vi = vi_entries[0]
    assert vi.chronology_known is True
    assert vi.visit_number == 110  # old chronological number preserved
    assert vi.matched_value == "U.S. Virgin Is."
    assert vi.source_old_index is True
    assert vi.source_reconciliation is True  # confirmed by both sources now


def test_british_virgin_islands_not_substituted(matcher):
    result = matcher.match("Virgin Islands")
    assert result.matched_value == "U.S. Virgin Is."
    assert result.matched_value != "British Virgin Is."


def test_belgium_composite_geometry(gdf, matcher):
    result = matcher.match("Belgium")
    assert result.status == "matched"
    assert result.match_type == "composite"
    names = set(gdf.loc[result.entity_ids, "NAME"])
    assert names == {"Flemish", "Walloon", "Brussels"}


def test_belgium_is_one_pending_entry_not_multiple(gdf, default_workbook_path, matcher):
    """Composite geometry must not create multiple visit records."""
    merged = _merged(gdf, default_workbook_path, matcher)
    belgium_entries = [e for e in merged.entries if e.name == "Belgium"]
    assert len(belgium_entries) == 1
    assert belgium_entries[0].chronology_known is False
    assert belgium_entries[0].visit_number is None


def test_palestine_handling(gdf, default_workbook_path, matcher):
    """Palestine is unioned from real, unmodified Gaza + West Bank
    polygons (both already ADMIN=Palestine in the dataset) -- no boundary
    redraw, no sovereignty metadata change, and Israel's own polygon is
    untouched (checked via entity_ids never overlapping)."""
    result = matcher.match("Palestine")
    assert result.status == "matched"
    assert result.match_type == "composite"
    names = set(gdf.loc[result.entity_ids, "NAME"])
    assert names == {"Gaza", "West Bank"}

    israel_result = matcher.match("Israel")
    assert set(israel_result.entity_ids).isdisjoint(set(result.entity_ids))

    merged = _merged(gdf, default_workbook_path, matcher)
    palestine_entries = [e for e in merged.entries if e.name == "Palestine"]
    assert len(palestine_entries) == 1
    assert palestine_entries[0].chronology_known is False


def test_all_19_new_countries_included_as_confirmed_visited(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    confirmed_names = {e.name for e in merged.entries}
    missing = NEW_19_COUNTRIES - confirmed_names
    assert not missing, f"new countries not confirmed-visited: {missing}"
    for name in NEW_19_COUNTRIES:
        entry = next(e for e in merged.entries if e.name == name)
        assert entry.confirmed_visited is True
        assert entry.source_reconciliation is True


def test_no_new_country_receives_a_fabricated_chronology_number(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    for name in NEW_19_COUNTRIES | {"Belgium", "Palestine"}:
        entry = next(e for e in merged.entries if e.name == name)
        assert entry.chronology_known is False
        assert entry.visit_number is None


def test_21_old_gaps_remain_unresolved(gdf, default_workbook_path, matcher):
    from src.validation import build_validation_report

    old_report = build_validation_report(default_workbook_path, gdf, matcher)
    assert set(old_report.missing_numbers) == MISSING_NUMBERS
    assert old_report.missing_count == 21
    merged = _merged(gdf, default_workbook_path, matcher)
    numbered = {e.visit_number for e in merged.numbered_entries}
    assert numbered.isdisjoint(MISSING_NUMBERS)


def test_known_chronology_preserved_exactly(gdf, default_workbook_path, matcher):
    """Every pre-existing old visit number must still point to the same
    country after the merge -- none renumbered."""
    from src.validation import build_validation_report

    old_report = build_validation_report(default_workbook_path, gdf, matcher)
    merged = _merged(gdf, default_workbook_path, matcher)
    old_by_number = {m.number: m.country_raw for m in old_report.mapped}
    merged_by_number = {e.visit_number: e.name for e in merged.numbered_entries}
    assert old_by_number == merged_by_number


def test_pending_entries_have_real_geometry(gdf, default_workbook_path, matcher):
    merged = _merged(gdf, default_workbook_path, matcher)
    for e in merged.pending_entries:
        assert e.entity_ids
        for eid in e.entity_ids:
            geom = gdf.at[eid, "geometry"]
            assert geom is not None and not geom.is_empty
