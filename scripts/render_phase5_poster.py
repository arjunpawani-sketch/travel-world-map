"""
Phase 5 review script: builds the validation report + full marker
placement plan from the bundled workbook, renders the complete A2 poster
composition to output/phase5_a2_poster_preview.png, and prints the stats
needed to sanity check it before moving to Phase 6.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.geography import load_geodata
from src.insets import compute_frame_xlim_ylim, load_insets
from src.labels import build_marker_report
from src.matcher import CountryMatcher
from src.poster import ROBINSON_CRS, render_poster
from src.poster_index import build_index_columns, choose_column_count
from src.poster_layout import load_poster_layout
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "output" / "phase5_a2_poster_preview.png"

DPI = 250


def main():
    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)
    layout = load_poster_layout()
    insets = load_insets()

    # Build every marker report up front (same inputs render_poster would
    # use internally) so the printed stats are guaranteed to match what's
    # actually drawn.
    marker_reports = {
        "main": build_marker_report(
            gdf, report.mapped, crs=ROBINSON_CRS,
            fig_width_inches=layout.main_map.width * layout.page_width_in,
            target_display="main", marker_radius_points=layout.typography.main_marker_radius_points,
        )
    }
    for key, inset in insets.items():
        crs = inset.crs()
        xlim, _ = compute_frame_xlim_ylim(inset, crs)
        rect = layout.inset_rects()[key]
        marker_reports[key] = build_marker_report(
            gdf, report.mapped, crs=crs,
            fig_width_inches=rect.width * layout.page_width_in,
            data_width=xlim[1] - xlim[0], target_display=key,
            marker_radius_points=layout.typography.inset_marker_radius_points,
        )

    fig = render_poster(
        gdf,
        report.mapped,
        missing_count=report.missing_count,
        insets=insets,
        layout=layout,
        marker_reports=marker_reports,
        dpi=DPI,
    )
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    w_px, h_px = fig.get_size_inches() * fig.dpi

    # --- Stats ---
    print(f"Page size: {layout.page_width_mm}mm x {layout.page_height_mm}mm "
          f"({layout.page_width_in:.4f}in x {layout.page_height_in:.4f}in)")
    print(f"Preview dimensions: {int(w_px)}x{int(h_px)} px at {DPI} dpi")
    print()

    print("Revised display counts:")
    for key in ["main"] + list(insets.keys()):
        n = len(marker_reports[key].target_placements)
        print(f"  {key}: {n}")
    total = sum(len(marker_reports[k].target_placements) for k in marker_reports)
    print(f"  TOTAL: {total}  (mapped_count from validation: {report.mapped_count})")
    print()

    print("Collisions per panel (before -> after auto-resolve):")
    any_collisions_remaining = False
    for key, mr in marker_reports.items():
        print(f"  {key}: {len(mr.collisions_before)} -> {len(mr.collisions_after)}")
        if mr.collisions_after:
            any_collisions_remaining = True
            for c in mr.collisions_after:
                print(f"    UNRESOLVED: #{c.visit_a} <-> #{c.visit_b}")
    if not any_collisions_remaining:
        print("  No unresolved collisions in any panel.")
    print()

    # Index stats
    typo = layout.typography
    index_zone = layout.index
    index_width_in = index_zone.width * layout.page_width_in
    index_height_in = index_zone.height * layout.page_height_in * 0.94
    num_columns = choose_column_count(
        n_entries=report.mapped_count,
        index_height_in=index_height_in,
        index_width_in=index_width_in,
        font_size_pt=typo.index_font_size,
        line_height_factor=typo.index_line_height_factor,
        min_column_width_in=layout.index_min_column_width * layout.page_width_in,
        column_gap_in=layout.index_column_gap * layout.page_width_in,
    )
    columns = build_index_columns(report.mapped, num_columns)
    print(f"Index: {report.mapped_count} entries in {num_columns} columns")
    print(f"  column sizes: {[len(c) for c in columns]}")
    all_numbers = [e.number for col in columns for e in col]
    print(f"  strictly increasing overall: {all_numbers == sorted(all_numbers)}")
    print(f"  no duplicates: {len(all_numbers) == len(set(all_numbers))}")
    print(f"  matches mapped_count exactly: {len(all_numbers) == report.mapped_count}")

    # Longest names, for wrapping assessment
    longest = sorted(report.mapped, key=lambda m: len(m.country_raw), reverse=True)[:8]
    print()
    print("Longest country/territory names in the index (for wrapping check):")
    for m in longest:
        print(f"  #{m.number} '{m.country_raw}' ({len(m.country_raw)} chars)")

    print()
    print(f"Virgin Islands present in mapped/index: "
          f"{any('virgin' in m.country_raw.lower() for m in report.mapped)}")
    print(f"Missing numbers count (unresolved note): {report.missing_count}")

    print()
    print(f"Poster saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
