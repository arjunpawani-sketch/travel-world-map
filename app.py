"""
Travel World Map -- V1 (Phases 1 through 6)

Excel upload -> parse -> normalize -> match against geographic data ->
validation summary -> full A2 poster preview (title, main map, regional
insets, chronological index, footer) -> download production-quality A2
PDF / high-resolution PNG. Development-only per-panel views (main map
alone, insets alone, marker debug info) are tucked behind a toggle, off
by default.
"""
from __future__ import annotations

import io
from pathlib import Path

import streamlit as st

from src.excel_parser import WorkbookFormatError
from src.export import export_poster_pdf_and_png
from src.geography import GeographicDataUnavailable, load_geodata
from src.insets import compute_frame_xlim_ylim, load_insets
from src.labels import build_marker_report
from src.matcher import CountryMatcher
from src.poster import ROBINSON_CRS, render_inset_map, render_poster, render_world_map
from src.poster_layout import load_poster_layout
from src.validation import build_validation_report

MAP_WIDTH_IN = 14
MAP_HEIGHT_IN = 7
INSET_WIDTH_IN = 7
INSET_HEIGHT_IN = 5.5
POSTER_PREVIEW_DPI = 100
EXPORT_PNG_DPI = 300

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = PROJECT_ROOT / "Country_Number_Index.xlsx"

st.set_page_config(page_title="Countries Visited", layout="wide")


@st.cache_resource(show_spinner="Loading geographic dataset (first run only)...")
def get_geodata():
    return load_geodata()


@st.cache_resource
def get_matcher(_gdf):
    return CountryMatcher(_gdf)


@st.cache_data(show_spinner="Generating print-quality A2 PDF + PNG (about 40 seconds)...")
def get_export_bytes(_gdf, workbook_bytes: bytes) -> tuple[bytes, bytes]:
    """Cached on the workbook's own bytes, so re-running this script for
    an unrelated widget interaction (e.g. toggling dev views) reuses the
    cached export instantly, but uploading a different/edited workbook
    always regenerates it -- never a stale PDF/PNG. `_gdf` is excluded
    from the cache key (leading underscore) since it's a fixed singleton
    for the process; only the workbook content should invalidate this."""
    local_matcher = get_matcher(_gdf)
    local_report = build_validation_report(io.BytesIO(workbook_bytes), _gdf, local_matcher)
    return export_poster_pdf_and_png(
        _gdf, local_report.mapped, missing_count=local_report.missing_count, png_dpi=EXPORT_PNG_DPI
    )


st.title("Countries Visited")
st.caption("Upload your Excel, or use the bundled one, to generate the poster and download it.")

uploaded = st.file_uploader("Upload a replacement .xlsx file", type=["xlsx"])
source = uploaded if uploaded is not None else DEFAULT_WORKBOOK

if uploaded is None:
    if not DEFAULT_WORKBOOK.exists():
        st.error(f"No workbook uploaded, and the bundled default was not found at {DEFAULT_WORKBOOK}.")
        st.stop()
    st.info(f"Using bundled workbook: {DEFAULT_WORKBOOK.name}")
    workbook_bytes = DEFAULT_WORKBOOK.read_bytes()
else:
    workbook_bytes = uploaded.getvalue()

try:
    gdf = get_geodata()
except GeographicDataUnavailable as exc:
    st.error(str(exc))
    st.stop()

matcher = get_matcher(gdf)

try:
    report = build_validation_report(source, gdf, matcher)
except WorkbookFormatError as exc:
    st.error(f"Could not read this workbook: {exc}")
    st.stop()

st.subheader("Validation summary")
for line in report.summary_lines():
    st.write(f"- {line}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"Mapped locations ({report.mapped_count})")
    st.dataframe(
        [
            {
                "Number": m.number,
                "Country/Territory (as entered)": m.country_raw,
                "Matched to": m.matched_value,
                "Match type": m.match_type,
                "Confidence": m.confidence,
            }
            for m in sorted(report.mapped, key=lambda m: m.number)
        ],
        width='stretch',
        hide_index=True,
    )

with col2:
    st.subheader(f"Unresolved names ({len(report.unresolved)})")
    if report.unresolved:
        st.dataframe(
            [
                {
                    "Number": u.number,
                    "Country/Territory (as entered)": u.country_raw,
                    "Status": u.status,
                    "Candidates": ", ".join(u.candidates) if u.candidates else "",
                }
                for u in sorted(report.unresolved, key=lambda u: u.number)
            ],
            width='stretch',
            hide_index=True,
        )
    else:
        st.write("None -- every named entry matched a geographic entity.")

st.divider()

st.subheader(f"Missing visit numbers ({report.missing_count})")
if report.missing_numbers:
    st.write(", ".join(str(n) for n in report.missing_numbers))
    st.caption(
        "These chronological numbers have no country/territory in the source "
        "Excel file. They are not guessed and will not appear on the poster "
        "until the workbook is updated."
    )
else:
    st.write("None.")

if report.duplicate_numbers:
    st.subheader(f"Duplicated visit numbers ({len(report.duplicate_numbers)})")
    for num, countries in sorted(report.duplicate_numbers.items()):
        st.write(f"- **{num}**: {', '.join(countries)}")

if report.duplicate_country_names:
    st.subheader(f"Countries/territories visited more than once ({len(report.duplicate_country_names)})")
    for name, nums in sorted(report.duplicate_country_names.items()):
        st.write(f"- **{name}**: visit numbers {', '.join(str(n) for n in nums)}")

if report.parsed.warnings:
    st.subheader(f"Row-level warnings from the Excel sheet ({len(report.parsed.warnings)})")
    for w in report.parsed.warnings:
        st.write(f"- {w}")

st.caption(
    f"Read sheet '{report.parsed.sheet_name}', header row {report.parsed.header_row}."
)

st.divider()

st.subheader("Poster preview")
st.caption(
    "Full A2 landscape composition -- title, main map, the four regional "
    "insets, the chronological index, and footer, all generated "
    "deterministically from the Excel source and geographic data."
)
layout = load_poster_layout()
with st.spinner("Composing poster..."):
    poster_fig = render_poster(
        gdf,
        report.mapped,
        missing_count=report.missing_count,
        layout=layout,
        dpi=POSTER_PREVIEW_DPI,
    )
st.pyplot(poster_fig, width='stretch')
st.caption(
    "Shown at reduced resolution for responsiveness -- the downloads below "
    "are full print quality."
)

pdf_bytes, export_png_bytes = get_export_bytes(gdf, workbook_bytes)

dl_col1, dl_col2 = st.columns(2)
with dl_col1:
    st.download_button(
        "Download A2 PDF",
        data=pdf_bytes,
        file_name="countries_visited_A2.pdf",
        mime="application/pdf",
        width='stretch',
    )
with dl_col2:
    st.download_button(
        "Download High-Resolution PNG",
        data=export_png_bytes,
        file_name="countries_visited_A2.png",
        mime="image/png",
        width='stretch',
    )

if report.unresolved:
    st.caption(
        f"Development note: {len(report.unresolved)} source location(s) remain "
        "geographically unresolved and are excluded from the poster above "
        "(not placed prominently on the poster itself yet) -- see the "
        "Unresolved names table earlier on this page."
    )

st.divider()

show_dev_views = st.toggle("Show development views", value=False)
if not show_dev_views:
    st.caption(
        "Per-panel main map, regional insets, and marker debug info are "
        "available under 'Show development views' above."
    )

if show_dev_views:
    st.subheader("Map preview")
    st.caption(
        "Numbered markers are shown only for visits assigned to the main map. "
        "Entries in dense/small clusters (Europe microstates and Balkans, the "
        "Gulf, the Eastern Caribbean, Pacific island nations) are intentionally "
        "routed to their regional inset instead of being crammed onto the "
        "world map -- see data/label_offsets.json."
    )
    debug_markers = st.toggle("Show marker debug information", value=False)

    with st.spinner("Computing marker placement..."):
        marker_report = build_marker_report(
            gdf, report.mapped, crs=ROBINSON_CRS, fig_width_inches=MAP_WIDTH_IN
        )
    with st.spinner("Rendering map..."):
        fig = render_world_map(
            gdf,
            report.mapped,
            width=MAP_WIDTH_IN,
            height=MAP_HEIGHT_IN,
            dpi=120,
            preview=True,
            show_markers=True,
            marker_report=marker_report,
            debug_markers=debug_markers,
        )
    st.pyplot(fig, width='stretch')

    if debug_markers:
        counts = marker_report.counts_by_display()
        st.write(
            f"- {len(marker_report.placements)} total markers "
            f"({counts.get('main', 0)} on main map; "
            f"{counts.get('europe', 0)} europe / {counts.get('gulf', 0)} gulf / "
            f"{counts.get('caribbean', 0)} caribbean / {counts.get('pacific', 0)} pacific)"
        )
        st.write(
            f"- Collisions detected before auto-resolve: {len(marker_report.collisions_before)}"
        )
        st.write(
            f"- Collisions remaining after auto-resolve: {len(marker_report.collisions_after)}"
        )
        st.write(f"- Markers auto-nudged to resolve a collision: {len(marker_report.adjustments)}")
        if marker_report.collisions_after:
            st.write("Unresolved collisions (red dashed lines on the map above):")
            for c in marker_report.collisions_after:
                st.write(f"  - #{c.visit_a} <-> #{c.visit_b}")
        st.caption(
            "Red x marks are true geographic anchor points; a leader line (if "
            "any) connects an anchor to its nudged marker."
        )

    png_buffer = io.BytesIO()
    fig.savefig(png_buffer, format="png", facecolor=fig.get_facecolor())
    st.download_button(
        "Download main map preview PNG (development inspection only)",
        data=png_buffer.getvalue(),
        file_name="travel_world_map_preview.png",
        mime="image/png",
    )

    st.divider()

    st.subheader("Regional insets preview")
    st.caption(
        "Development view -- each inset shown separately, not the final poster "
        "composition. Same visited/unvisited palette and marker engine as the "
        "main map; bounds and projection come from data/insets.json."
    )

    insets = load_insets()
    inset_cols = st.columns(2)
    for i, (key, inset) in enumerate(insets.items()):
        crs = inset.crs()
        xlim, _ = compute_frame_xlim_ylim(inset, crs)
        with st.spinner(f"Rendering {inset.title} inset..."):
            inset_marker_report = build_marker_report(
                gdf,
                report.mapped,
                crs=crs,
                fig_width_inches=INSET_WIDTH_IN,
                data_width=xlim[1] - xlim[0],
                target_display=key,
            )
            inset_fig = render_inset_map(
                gdf,
                report.mapped,
                inset,
                width=INSET_WIDTH_IN,
                height=INSET_HEIGHT_IN,
                dpi=110,
                marker_report=inset_marker_report,
                debug_markers=debug_markers,
            )
        with inset_cols[i % 2]:
            st.pyplot(inset_fig, width='stretch')
            if debug_markers:
                n = len(inset_marker_report.target_placements)
                st.write(
                    f"- {n} marker(s) -- "
                    f"{len(inset_marker_report.collisions_before)} collision(s) before, "
                    f"{len(inset_marker_report.collisions_after)} remaining after auto-resolve"
                )
                if inset_marker_report.collisions_after:
                    for c in inset_marker_report.collisions_after:
                        st.write(f"  - #{c.visit_a} <-> #{c.visit_b}")
