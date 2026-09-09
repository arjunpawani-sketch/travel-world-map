"""
Phase 4 review script: renders each regional inset, a 2x2 contact sheet
(development review only), and prints the stats needed to sanity check
the inset system before moving to Phase 5.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt

from src.geography import load_geodata
from src.insets import load_insets
from src.labels import build_marker_report
from src.matcher import CountryMatcher
from src.poster import COLOR_BACKGROUND, render_inset_map
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output"

INSET_WIDTH = 10.0
INSET_HEIGHT = 8.0
DPI = 220

FILE_NAMES = {
    "europe": "phase4_europe_inset.png",
    "gulf": "phase4_gulf_inset.png",
    "caribbean": "phase4_caribbean_inset.png",
    "pacific": "phase4_pacific_inset.png",
}


def main():
    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)
    insets = load_insets()

    OUTPUT_DIR.mkdir(exist_ok=True)

    figs = {}
    reports = {}
    for key, inset in insets.items():
        crs = inset.crs()
        from src.insets import compute_frame_xlim_ylim

        xlim, _ = compute_frame_xlim_ylim(inset, crs)
        data_width = xlim[1] - xlim[0]

        marker_report = build_marker_report(
            gdf,
            report.mapped,
            crs=crs,
            fig_width_inches=INSET_WIDTH,
            data_width=data_width,
            target_display=key,
        )
        fig = render_inset_map(
            gdf,
            report.mapped,
            inset,
            width=INSET_WIDTH,
            height=INSET_HEIGHT,
            dpi=DPI,
            marker_report=marker_report,
        )
        path = OUTPUT_DIR / FILE_NAMES[key]
        fig.savefig(path, facecolor=fig.get_facecolor())
        figs[key] = fig
        reports[key] = marker_report

        w_px, h_px = fig.get_size_inches() * fig.dpi
        print(f"=== {inset.title} ({key}) ===")
        print(f"  Projection: {inset.projection}  CRS: {crs}")
        print(f"  Bounds: lon[{inset.lon_min}, {inset.lon_max}] lat[{inset.lat_min}, {inset.lat_max}]"
              f"{' (wraps antimeridian, lon_0=' + str(inset.lon_0) + ')' if inset.wraps_antimeridian else ''}")
        placements = marker_report.target_placements
        print(f"  Markers: {len(placements)}")
        print(f"  Collisions before auto-resolve: {len(marker_report.collisions_before)}")
        for c in marker_report.collisions_before:
            print(f"    #{c.visit_a} <-> #{c.visit_b}  distance={c.distance:.0f}  threshold={c.threshold:.0f}")
        print(f"  Collisions remaining after auto-resolve: {len(marker_report.collisions_after)}")
        for c in marker_report.collisions_after:
            print(f"    #{c.visit_a} <-> #{c.visit_b}")
        print(f"  Auto-nudged markers: {len(marker_report.adjustments)}")
        manual = [p for p in placements if p.dx != 0 or p.dy != 0]
        leader_lines = [p for p in placements if p.leader_line and (p.dx or p.dy)]
        print(f"  Manual offsets configured: {len(manual)}")
        for p in manual:
            print(f"    #{p.visit_number} {p.source_name}: dx={p.dx} dy={p.dy} leader_line={p.leader_line}")
        print(f"  Leader lines drawn: {len(leader_lines)}")
        print(f"  Dimensions: {int(w_px)}x{int(h_px)} px at {fig.dpi} dpi ({INSET_WIDTH}x{INSET_HEIGHT} in)")
        print()

    # 2x2 contact sheet -- development review only, not the final poster.
    order = ["europe", "gulf", "caribbean", "pacific"]
    contact_fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=150)
    contact_fig.patch.set_facecolor(COLOR_BACKGROUND)
    for ax, key in zip(axes.flat, order):
        src_fig = figs[key]
        src_fig.canvas.draw()
        img = plt_image_from_figure(src_fig)
        ax.imshow(img)
        ax.set_axis_off()
        ax.set_title(insets[key].title, fontsize=10, family="serif")
    contact_path = OUTPUT_DIR / "phase4_insets_contact_sheet.png"
    contact_fig.tight_layout()
    contact_fig.savefig(contact_path, facecolor=contact_fig.get_facecolor())
    print(f"Contact sheet saved to: {contact_path}")

    total_markers = sum(len(r.target_placements) for r in reports.values())
    all_visit_numbers = set()
    for r in reports.values():
        all_visit_numbers.update(p.visit_number for p in r.target_placements)
    excel_numbers = {m.number for m in report.mapped}
    print()
    print(f"Total inset markers across all 4 insets: {total_markers}")
    print(f"All inset marker numbers exist in Excel chronology: {all_visit_numbers.issubset(excel_numbers)}")
    virgin_islands_present = any(
        "virgin" in p.source_name.lower()
        for r in reports.values()
        for p in r.target_placements
    )
    print(f"Virgin Islands appears in any inset (should be False): {virgin_islands_present}")
    missing_numbers_in_insets = all_visit_numbers.intersection(set(report.missing_numbers))
    print(f"Missing chronological numbers appearing as markers (should be empty): {missing_numbers_in_insets}")


def plt_image_from_figure(fig):
    import numpy as np

    fig.canvas.draw()
    buf = fig.canvas.buffer_rgba()
    w, h = fig.canvas.get_width_height()
    return np.asarray(buf, dtype=np.uint8).reshape(h, w, 4)


if __name__ == "__main__":
    main()
