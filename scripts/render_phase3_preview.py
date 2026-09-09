"""
Phase 3 review script: builds the validation report + marker placement
plan from the bundled workbook, renders the world map with numbered
markers to output/phase3_world_map_markers_preview.png, and prints the
stats needed to sanity check the placement system before moving to
Phase 4.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.geography import load_geodata
from src.labels import build_marker_report
from src.matcher import CountryMatcher
from src.poster import ROBINSON_CRS, render_world_map
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "output" / "phase3_world_map_markers_preview.png"

FIG_WIDTH = 20.0
FIG_HEIGHT = 10.0
DPI = 220


def main():
    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)

    marker_report = build_marker_report(
        gdf, report.mapped, crs=ROBINSON_CRS, fig_width_inches=FIG_WIDTH
    )

    fig = render_world_map(
        gdf,
        report.mapped,
        width=FIG_WIDTH,
        height=FIG_HEIGHT,
        dpi=DPI,
        preview=False,
        show_markers=True,
        marker_report=marker_report,
    )
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    w_px, h_px = fig.get_size_inches() * fig.dpi

    counts = marker_report.counts_by_display()
    all_numbers_match = {p.visit_number for p in marker_report.placements} == {
        m.number for m in report.mapped
    }

    print(f"Total visit markers created: {len(marker_report.placements)}")
    print(f"Assigned to main map: {counts.get('main', 0)}")
    for region in ("europe", "gulf", "caribbean", "pacific"):
        print(f"Assigned to '{region}' inset (future): {counts.get(region, 0)}")

    print()
    print(f"Collisions detected before auto-resolve: {len(marker_report.collisions_before)}")
    for c in marker_report.collisions_before:
        print(f"  #{c.visit_a} <-> #{c.visit_b}  distance={c.distance:.0f}  threshold={c.threshold:.0f}")

    print()
    print(f"Collisions remaining after auto-resolve: {len(marker_report.collisions_after)}")
    for c in marker_report.collisions_after:
        print(f"  #{c.visit_a} <-> #{c.visit_b}  distance={c.distance:.0f}  threshold={c.threshold:.0f}")

    print()
    print(f"Auto-nudged markers: {len(marker_report.adjustments)}")
    for visit_number, (adx, ady) in sorted(marker_report.adjustments.items()):
        print(f"  #{visit_number}: nudged by ({adx:.0f}, {ady:.0f}) map units")

    print()
    manual_entries = [
        p for p in marker_report.placements if p.dx != 0 or p.dy != 0
    ]
    print(f"Entries with a manual offset already configured: {len(manual_entries)}")
    for p in manual_entries:
        print(f"  #{p.visit_number} {p.source_name}: dx={p.dx} dy={p.dy}")

    print()
    print(f"All marker numbers match Excel chronology exactly: {all_numbers_match}")

    print()
    print(f"Preview saved to: {OUTPUT_PATH}")
    print(f"Dimensions: {int(w_px)}x{int(h_px)} px at {fig.dpi} dpi ({FIG_WIDTH}x{FIG_HEIGHT} in)")


if __name__ == "__main__":
    main()
