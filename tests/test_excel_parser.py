import pytest

from src.excel_parser import WorkbookFormatError, parse_workbook

KNOWN_ENTRIES = {
    1: "Iraq",
    4: "Oman",
    5: "United Arab Emirates",
    6: "United Kingdom",
    9: "Monaco",
    22: "Australia",
}


def test_parses_bundled_workbook(default_workbook_path):
    result = parse_workbook(default_workbook_path)
    assert result.sheet_name == "Master List"
    assert len(result.records) == 184


def test_known_entries_present(default_workbook_path):
    result = parse_workbook(default_workbook_path)
    by_number = {r.number: r.country_raw for r in result.records}
    for number, expected_country in KNOWN_ENTRIES.items():
        assert by_number[number] == expected_country


def test_chronological_numbers_preserved_exactly(default_workbook_path):
    """Numbers must never be renumbered/compacted -- gaps stay gaps."""
    result = parse_workbook(default_workbook_path)
    numbers = [r.number for r in result.records]
    assert 7 not in numbers  # known-missing number stays absent
    assert 205 == max(numbers)  # highest known number preserved, not clamped
    assert numbers == sorted(numbers)  # source order is already chronological


def test_missing_workbook_columns_raise_friendly_error(tmp_path):
    import openpyxl

    bad_path = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Foo", "Bar"])
    ws.append([1, "nonsense"])
    wb.save(bad_path)

    with pytest.raises(WorkbookFormatError):
        parse_workbook(bad_path)


def test_row_with_number_but_no_country_is_flagged_not_crashed(tmp_path):
    import openpyxl

    path = tmp_path / "partial.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Number", "Country / Territory", "Region(s)"])
    ws.append([1, "Iraq", "Middle East & Asia"])
    ws.append([2, None, None])

    wb.save(path)

    result = parse_workbook(path)
    assert len(result.records) == 1
    assert any("2" in w for w in result.warnings)
