import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.geography import load_geodata
from src.matcher import CountryMatcher

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"


@pytest.fixture(scope="session")
def gdf():
    return load_geodata()


@pytest.fixture(scope="session")
def matcher(gdf):
    return CountryMatcher(gdf)


@pytest.fixture(scope="session")
def default_workbook_path():
    return DEFAULT_WORKBOOK


@pytest.fixture(scope="session")
def default_export(gdf, matcher, default_workbook_path):
    """One real PDF+PNG export of the bundled workbook, shared across every
    test that just inspects a property of a standard export -- each export
    involves full geometry reprojection and collision resolution across 5
    panels (~40s), so tests that don't need a distinct input reuse this
    instead of re-exporting from scratch."""
    from src.export import export_poster_pdf_and_png
    from src.validation import build_validation_report

    report = build_validation_report(default_workbook_path, gdf, matcher)
    pdf_bytes, png_bytes = export_poster_pdf_and_png(
        gdf, report.mapped, missing_count=report.missing_count
    )
    return report, pdf_bytes, png_bytes
