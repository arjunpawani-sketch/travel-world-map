"""
End-to-end proof of the core promise: update the Excel, the map updates
automatically. Works entirely on a throwaway copy of the bundled
workbook (pytest's tmp_path, auto-cleaned) -- the real
Country_Number_Index.xlsx is never opened for writing, and its hash is
checked before/after to prove that.
"""
import hashlib
import io
import shutil

import openpyxl
from pypdf import PdfReader

from src.export import export_poster_pdf_and_png
from src.labels import build_placements
from src.matcher import CountryMatcher
from src.poster import get_visited_entity_ids
from src.validation import build_validation_report

NEW_ENTRY_NAME = "United States of America"


def _file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adding_one_new_entry_propagates_through_the_whole_pipeline(
    gdf, default_workbook_path, tmp_path
):
    original_hash_before = _file_hash(default_workbook_path)

    # 1. Work only on a throwaway copy.
    temp_workbook = tmp_path / "test_workbook_with_new_entry.xlsx"
    shutil.copy(default_workbook_path, temp_workbook)

    matcher = CountryMatcher(gdf)
    report_before = build_validation_report(default_workbook_path, gdf, matcher)
    highest_number_before = max(m.number for m in report_before.mapped)
    new_number = highest_number_before + 1
    assert not any(m.country_raw == NEW_ENTRY_NAME for m in report_before.mapped), (
        f"test fixture assumption broken: '{NEW_ENTRY_NAME}' is already in the "
        "bundled workbook, pick a different probe entry"
    )

    # 2. Add one clearly-supported new travel entry after the current max.
    wb = openpyxl.load_workbook(temp_workbook)
    ws = wb["Master List"]
    ws.append([new_number, NEW_ENTRY_NAME, "North America"])
    wb.save(temp_workbook)

    # 3. Run the full pipeline against the modified copy.
    report_after = build_validation_report(temp_workbook, gdf, matcher)

    # mapped count increases by exactly 1
    assert report_after.mapped_count == report_before.mapped_count + 1

    # new number appears in the mapped records, correctly matched
    new_entry = next((m for m in report_after.mapped if m.number == new_number), None)
    assert new_entry is not None, "new visit number did not appear in mapped records"
    assert new_entry.country_raw == NEW_ENTRY_NAME
    assert new_entry.matched_value == NEW_ENTRY_NAME
    assert new_entry.entity_ids  # resolved to real geometry

    # location highlights correctly (its entity is in the visited set)
    visited_ids = get_visited_entity_ids(report_after.mapped)
    assert set(new_entry.entity_ids).issubset(visited_ids)

    # a marker/placement is created for it
    placements = build_placements(gdf, report_after.mapped)
    matching_placements = [p for p in placements if p.visit_number == new_number]
    assert len(matching_placements) == 1
    assert matching_placements[0].source_name == NEW_ENTRY_NAME

    # nothing else about the existing chronology changed
    assert report_after.missing_count == report_before.missing_count
    assert len(report_after.unresolved) == len(report_before.unresolved)
    unchanged_numbers = {m.number for m in report_before.mapped}
    after_numbers = {m.number for m in report_after.mapped}
    assert unchanged_numbers.issubset(after_numbers)

    # 4. PDF/PNG export includes it.
    pdf_bytes, png_bytes = export_poster_pdf_and_png(
        gdf, report_after.mapped, missing_count=report_after.missing_count
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_no_ws = "".join((reader.pages[0].extract_text() or "").split())
    assert "".join(NEW_ENTRY_NAME.split()) in text_no_ws
    assert str(new_number) in text_no_ws
    assert f"{report_after.mapped_count}countriesandterritoriesvisited" in text_no_ws
    assert len(png_bytes) > 1000

    # 5. The original bundled workbook was never touched.
    original_hash_after = _file_hash(default_workbook_path)
    assert original_hash_after == original_hash_before
