import io

from PIL import Image
from pypdf import PdfReader

from src.export import export_poster_pdf_and_png
from src.validation import build_validation_report

A2_WIDTH_PT = 594 / 25.4 * 72
A2_HEIGHT_PT = 420 / 25.4 * 72
PT_TOLERANCE = 2.0

ACCENTED_NAMES = ["Türkiye", "Côte d'Ivoire", "São Tomé and Príncipe"]


def _normalize(s: str) -> str:
    """pypdf occasionally inserts a spurious space when reconstructing
    text around a font-subset boundary near an accented glyph -- this is
    a text-extraction quirk, not a rendering defect (verified visually
    against the actual PNG/PDF), so comparisons strip all whitespace."""
    return "".join(s.split())


def test_pdf_export_produces_bytes(default_export):
    _, pdf_bytes, _ = default_export
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_has_exactly_one_page(default_export):
    _, pdf_bytes, _ = default_export
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


def test_pdf_page_dimensions_match_a2_landscape(default_export):
    _, pdf_bytes, _ = default_export
    reader = PdfReader(io.BytesIO(pdf_bytes))
    mb = reader.pages[0].mediabox
    assert abs(float(mb.width) - A2_WIDTH_PT) <= PT_TOLERANCE
    assert abs(float(mb.height) - A2_HEIGHT_PT) <= PT_TOLERANCE


def test_png_export_produces_valid_image(default_export):
    _, _, png_bytes = default_export
    img = Image.open(io.BytesIO(png_bytes))
    img.verify()  # raises if the PNG is corrupt


def test_png_dimensions_and_aspect_ratio_correct(default_export):
    _, _, png_bytes = default_export
    img = Image.open(io.BytesIO(png_bytes))
    expected_w = round(23.3858 * 300)
    expected_h = round(16.5354 * 300)
    assert abs(img.size[0] - expected_w) <= 2
    assert abs(img.size[1] - expected_h) <= 2
    expected_aspect = A2_WIDTH_PT / A2_HEIGHT_PT
    actual_aspect = img.size[0] / img.size[1]
    assert abs(expected_aspect - actual_aspect) < 0.01


def test_export_title_count_is_dynamic_not_hardcoded(default_export):
    report, pdf_bytes, _ = default_export
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()
    assert f"{report.mapped_count} countries and territories visited" in text


def test_export_index_matches_current_mapped_records(default_export):
    report, pdf_bytes, _ = default_export
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_no_ws = _normalize(reader.pages[0].extract_text())

    # Spot-check first, last, and a middle chronological entry.
    sample = sorted(report.mapped, key=lambda m: m.number)
    for m in [sample[0], sample[len(sample) // 2], sample[-1]]:
        assert _normalize(m.country_raw) in text_no_ws, m.country_raw

    for name in ACCENTED_NAMES:
        if any(m.country_raw == name for m in report.mapped):
            assert _normalize(name) in text_no_ws


def test_pdf_has_embedded_fonts(default_export):
    _, pdf_bytes, _ = default_export
    # Type 42 (TrueType) embedding leaves a recognizable marker in the raw PDF.
    assert b"/FontFile2" in pdf_bytes or b"TrueType" in pdf_bytes


def test_uploaded_workbook_bytes_propagate_into_export(gdf, default_workbook_path, matcher):
    """Simulates the Streamlit upload path: parsing straight from bytes
    (not the default file path) still flows through to the export. Uses a
    reduced DPI -- this test is about the data path, not image quality,
    which is already covered by `default_export`."""
    workbook_bytes = default_workbook_path.read_bytes()
    report = build_validation_report(io.BytesIO(workbook_bytes), gdf, matcher)
    pdf_bytes, _ = export_poster_pdf_and_png(
        gdf, report.mapped, missing_count=report.missing_count, png_dpi=72
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()
    assert f"{report.mapped_count} countries and territories visited" in text
