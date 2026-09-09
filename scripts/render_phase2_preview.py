"""
Phase 2 review script: builds the validation report from the bundled
workbook and renders the world map preview to
output/phase2_world_map_preview.png, printing the stats needed to sanity
check geographic correctness before moving to Phase 3.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.geography import load_geodata
from src.matcher import CountryMatcher
from src.poster import get_visited_entity_ids, render_world_map
from src.validation import build_validation_report

DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "output" / "phase2_world_map_preview.png"


def main():
    gdf = load_geodata()
    matcher = CountryMatcher(gdf)
    report = build_validation_report(DEFAULT_WORKBOOK, gdf, matcher)

    visited_ids = get_visited_entity_ids(report.mapped)
    missing_geometry = [eid for eid in visited_ids if eid not in gdf.index]

    fig = render_world_map(gdf, report.mapped, width=16, height=8, dpi=200, preview=False)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())

    w_px, h_px = fig.get_size_inches() * fig.dpi

    print(f"Mapped entries (visit records): {report.mapped_count}")
    print(f"Distinct geographic entities highlighted: {len(visited_ids)}")
    print(f"Entities lacking drawable geometry: {len(missing_geometry)} {missing_geometry}")
    print(f"Preview saved to: {OUTPUT_PATH}")
    print(f"Dimensions: {int(w_px)}x{int(h_px)} px at {fig.dpi} dpi ({fig.get_size_inches()[0]}x{fig.get_size_inches()[1]} in)")

    # Spot-check specific known entries requested for QA.
    spot_check_names = [
        "Iraq", "Oman", "United Arab Emirates", "Monaco", "Australia",
        "Greenland", "Hong Kong", "Macao",
    ]
    by_matched_value = {}
    for m in report.mapped:
        by_matched_value.setdefault(m.matched_value, []).append(m)
    print()
    print("Spot-check (name -> matched? -> entity_ids):")
    for name in spot_check_names:
        hits = [m for m in report.mapped if name.lower() in (m.matched_value or "").lower() or name.lower() in m.country_raw.lower()]
        if hits:
            for h in hits:
                print(f"  {name}: FOUND as visit #{h.number} '{h.country_raw}' -> {h.matched_value} (entity_ids={h.entity_ids})")
        else:
            print(f"  {name}: not present in this workbook's mapped entries")

    uk_entries = [m for m in report.mapped if m.match_type == "composite"]
    print()
    print("Composite entries rendered:")
    for m in uk_entries:
        print(f"  #{m.number} {m.country_raw} -> {m.matched_value} (entity_ids={m.entity_ids})")


if __name__ == "__main__":
    main()
