"""
V1.3 export script: reconciles Country_Number_Index.xlsx (authoritative
for chronology) against reconciliation.csv (authoritative for the
expanded confirmed-visited universe), renders the merged poster, and
writes it to NEW paths -- output/travel_world_map_A2_v13.pdf/.png --
without touching the existing V1.2 output/travel_world_map_A2.pdf/.png,
so the two can be compared before anything is replaced.
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
from src.labels import build_marker_report
from src.matcher import CountryMatcher
from src.poster import ROBINSON_CRS
from src.reconciliation import build_merged_reconciliation
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_PATH = OUTPUT_DIR / "travel_world_map_A2_v13.pdf"
PNG_PATH = OUTPUT_DIR / "travel_world_map_A2_v13.png"
V12_PDF_PATH = OUTPUT_DIR / "travel_world_map_A2.pdf"  # must remain untouched

A2_WIDTH_PT = 594 / 25.4 * 72
A2_HEIGHT_PT = 420 / 25.4 * 72
ROBINSON_ASPECT = 1.9882194046419828  # measured from the actual reprojected geodata


def main():
    v12_hash_before = None
    if V12_PDF_PATH.exists():
        import hashlib

        v12_hash_before = hashlib.sha256(V12_PDF_PATH.read_bytes()).hexdigest()

    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    old_report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)
    merged = build_merged_reconciliation(old_report, matcher)

    pending_names = [e.name for e in merged.pending_entries]
    extra_entity_ids = merged.pending_entity_ids()

    print(f"Old-source chronologically numbered: {old_report.mapped_count}")
    print(f"Old-source unresolved: {len(old_report.unresolved)}")
    print(f"reconciliation.csv record count: {merged.csv_record_count}")
    print(f"Merged confirmed-visited count: {merged.confirmed_visited_count}")
    print(f"Chronologically numbered: {merged.numbered_count}")
    print(f"Chronology pending: {merged.pending_count}")
    print(f"Geographically unresolved (either source): {merged.geographically_unresolved_count}")
    print()

    # Verify hero-map framing is unaffected by the extra highlighted geography.
    from src.insets import compute_frame_xlim_ylim, load_insets
    from src.poster_layout import load_poster_layout

    layout = load_poster_layout()
    map_h_mm = layout.main_map.height * layout.page_height_mm
    map_w_mm = min(layout.main_map.width * layout.page_width_mm, map_h_mm * ROBINSON_ASPECT)
    print(f"Hero map effective size: {map_w_mm:.1f}mm x {map_h_mm:.1f}mm "
          f"({map_w_mm / layout.page_width_mm * 100:.1f}% of page width)")
    print(f"main_map zone (unchanged from V1.2): y={layout.main_map.y} height={layout.main_map.height}")
    print()

    marker_reports = {
        "main": build_marker_report(
            gdf, old_report.mapped, crs=ROBINSON_CRS,
            fig_width_inches=layout.main_map.width * layout.page_width_in,
            target_display="main", marker_radius_points=layout.typography.main_marker_radius_points,
        )
    }
    insets = load_insets()
    for key, inset in insets.items():
        crs = inset.crs()
        xlim, _ = compute_frame_xlim_ylim(inset, crs)
        rect = layout.inset_rects()[key]
        marker_reports[key] = build_marker_report(
            gdf, old_report.mapped, crs=crs,
            fig_width_inches=rect.width * layout.page_width_in,
            data_width=xlim[1] - xlim[0], target_display=key,
            marker_radius_points=layout.typography.inset_marker_radius_points,
        )
    total_collisions_after = sum(len(mr.collisions_after) for mr in marker_reports.values())
    print(f"Marker collisions remaining after auto-resolve (all panels): {total_collisions_after}")
    print()

    t0 = time.time()
    pdf_bytes, png_bytes = export_poster_pdf_and_png(
        gdf,
        old_report.mapped,
        missing_count=old_report.missing_count,
        layout=layout,
        insets=insets,
        marker_reports=marker_reports,
        visited_count=merged.confirmed_visited_count,
        extra_visited_entity_ids=extra_entity_ids,
        pending_names=pending_names,
    )
    elapsed = time.time() - t0

    OUTPUT_DIR.mkdir(exist_ok=True)
    PDF_PATH.write_bytes(pdf_bytes)
    PNG_PATH.write_bytes(png_bytes)
    print(f"Export time: {elapsed:.1f}s")
    print(f"PDF: {PDF_PATH} ({len(pdf_bytes)/1024:.0f} KB)")
    print(f"PNG: {PNG_PATH} ({len(png_bytes)/(1024*1024):.1f} MB)")
    print()

    reader = PdfReader(io.BytesIO(pdf_bytes))
    print(f"PDF page count: {len(reader.pages)} (expected 1)")
    mb = reader.pages[0].mediabox
    width_ok = abs(float(mb.width) - A2_WIDTH_PT) <= 2.0
    height_ok = abs(float(mb.height) - A2_HEIGHT_PT) <= 2.0
    print(f"PDF page size: {float(mb.width):.2f} x {float(mb.height):.2f} pt "
          f"(matches A2: {width_ok and height_ok})")

    text = reader.pages[0].extract_text() or ""
    text_no_ws = "".join(text.split())
    print(f"Title count string present: {f'{merged.confirmed_visited_count}countriesandterritoriesvisited' in text_no_ws}")
    print(f"Israel present in extracted text: {'Israel' in text}")
    print(f"Pending-list line present: {'chronologypending' in text_no_ws.lower()}")
    for name in ["Canada", "UnitedStates", "Antarctica", "Belgium", "Palestine"]:
        print(f"  pending name '{name}' present: {name in text_no_ws}")

    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes))
    print()
    print(f"PNG dimensions: {img.size[0]} x {img.size[1]} px")

    if v12_hash_before is not None:
        import hashlib

        v12_hash_after = hashlib.sha256(V12_PDF_PATH.read_bytes()).hexdigest()
        print()
        print(f"V1.2 PDF unchanged: {v12_hash_after == v12_hash_before}")


if __name__ == "__main__":
    main()
