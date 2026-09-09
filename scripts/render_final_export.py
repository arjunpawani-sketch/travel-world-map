"""
Phase 6 final export script: generates the production PDF and PNG from the
bundled workbook, then runs the PDF quality checks described in the Phase
6 spec (page count, page size, embedded/extractable text, no obviously
missing content) and prints a report.
"""
import io
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pypdf import PdfReader

from src.export import export_poster_pdf_and_png
from src.geography import load_geodata
from src.matcher import CountryMatcher
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_PATH = OUTPUT_DIR / "travel_world_map_A2.pdf"
PNG_PATH = OUTPUT_DIR / "travel_world_map_A2.png"

A2_WIDTH_PT = 594 / 25.4 * 72
A2_HEIGHT_PT = 420 / 25.4 * 72
TOLERANCE_PT = 2.0

ACCENTED_NAMES_TO_CHECK = ["Türkiye", "Côte d'Ivoire", "São Tomé and Príncipe"]


def main():
    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)

    print(f"Mapped visit records: {report.mapped_count}")
    print(f"Missing chronological numbers: {report.missing_count}")
    print(f"Unresolved source locations: {len(report.unresolved)}")
    print()

    t0 = time.time()
    pdf_bytes, png_bytes = export_poster_pdf_and_png(
        gdf, report.mapped, missing_count=report.missing_count
    )
    elapsed = time.time() - t0

    OUTPUT_DIR.mkdir(exist_ok=True)
    PDF_PATH.write_bytes(pdf_bytes)
    PNG_PATH.write_bytes(png_bytes)

    print(f"Export time (PDF + PNG from one composition): {elapsed:.1f}s")
    print(f"PDF: {PDF_PATH}  ({len(pdf_bytes) / 1024:.0f} KB)")
    print(f"PNG: {PNG_PATH}  ({len(png_bytes) / (1024*1024):.1f} MB)")
    print()

    # --- PDF quality checks ---
    reader = PdfReader(io.BytesIO(pdf_bytes))
    print(f"PDF page count: {len(reader.pages)}  (expected 1)")
    page = reader.pages[0]
    mb = page.mediabox
    width_pt, height_pt = float(mb.width), float(mb.height)
    print(f"PDF page size: {width_pt:.2f} x {height_pt:.2f} pt")
    print(f"Expected A2 landscape: {A2_WIDTH_PT:.2f} x {A2_HEIGHT_PT:.2f} pt")
    width_ok = abs(width_pt - A2_WIDTH_PT) <= TOLERANCE_PT
    height_ok = abs(height_pt - A2_HEIGHT_PT) <= TOLERANCE_PT
    print(f"Page size matches A2 landscape within {TOLERANCE_PT}pt: {width_ok and height_ok}")

    text = page.extract_text() or ""
    text_no_ws = "".join(text.split())  # pypdf occasionally inserts a spurious
    # space when reconstructing text around a font-subset boundary (seen around
    # accented glyphs); this does not affect the rendered PDF/PNG (verified
    # visually), only pypdf's own text-reconstruction heuristic -- so presence
    # checks compare with whitespace stripped from both sides.

    print()
    print(f"Extracted text length: {len(text)} characters")
    print(f"Title count string present: {f'{report.mapped_count} countries and territories visited' in text}")
    print("Sample index entries present in extracted text (whitespace-normalized):")
    for probe in ["Iraq", "Venezuela", "205", "Democratic Republic of the Congo"]:
        print(f"  '{probe}': {''.join(probe.split()) in text_no_ws}")
    print("Accented names render as real extractable text, not missing-glyph boxes"
          " (whitespace-normalized -- see script comment on pypdf's own text-extraction quirk):")
    for name in ACCENTED_NAMES_TO_CHECK:
        print(f"  '{name}': {''.join(name.split()) in text_no_ws}")
    print(f"Missing-numbers note present: {'21 visit numbers currently unresolved' in text}")
    print(f"Footer present: {'Every journey tells a story' in text}")
    print(f"'Virgin Islands' NOT present (should be False): {'Virgin Islands' in text}")

    # --- PNG quality checks ---
    from PIL import Image

    png_img = Image.open(io.BytesIO(png_bytes))
    print()
    print(f"PNG dimensions: {png_img.size[0]} x {png_img.size[1]} px")
    print(f"PNG mode: {png_img.mode}")
    expected_w = round(23.3858 * 300)
    expected_h = round(16.5354 * 300)
    print(f"Expected ~{expected_w} x {expected_h} px at 300 dpi")
    aspect_pdf = width_pt / height_pt
    aspect_png = png_img.size[0] / png_img.size[1]
    print(f"Aspect ratio match (PDF vs PNG): {abs(aspect_pdf - aspect_png) < 0.01}")


if __name__ == "__main__":
    main()
