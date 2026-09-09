"""
Final export: production-quality vector A2 PDF and a high-resolution PNG.

Both are generated from a single `render_poster()` Figure -- built once,
saved twice -- so the PDF, the PNG, and the on-screen preview can never
drift apart from each other.
"""
from __future__ import annotations

import io

import matplotlib
import matplotlib.pyplot as plt

from .poster import render_poster
from .poster_layout import PosterLayout

PNG_EXPORT_DPI = 300

FONT_FAMILY_FALLBACK_NOTE = (
    "Uses Matplotlib's bundled DejaVu Sans/DejaVu Serif -- shipped with "
    "Matplotlib itself, not dependent on the user's system or any "
    "commercial font -- which cover the accented Latin characters this "
    "workbook uses (Turkiye, Cote d'Ivoire, Sao Tome and Principe, etc.)."
)


def _configure_vector_fonts() -> None:
    """Type 42 embeds real scalable TrueType outlines in the PDF (crisp at
    any zoom, text stays selectable/searchable) instead of Matplotlib's
    default Type 3 (bitmap-ish, poor for print). Safe to call repeatedly."""
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42


def build_export_figure(
    gdf,
    mapped_entries,
    missing_count: int = 0,
    layout: PosterLayout | None = None,
    insets=None,
    marker_reports=None,
    label_offsets: dict | None = None,
    debug_markers: bool = False,
):
    """Builds the exact poster composition used for both PDF and PNG
    export. A thin, explicitly-named wrapper around `render_poster` so
    export call sites read clearly."""
    return render_poster(
        gdf,
        mapped_entries,
        missing_count=missing_count,
        layout=layout,
        insets=insets,
        marker_reports=marker_reports,
        label_offsets=label_offsets,
        dpi=150,  # irrelevant to the PDF's vector output; PNG dpi is set at save time
        debug_markers=debug_markers,
    )


def save_pdf_bytes(fig) -> bytes:
    """Saves `fig` as a vector PDF (page size = the figure's own physical
    size in inches, i.e. true A2) and returns the raw bytes. Does not
    close `fig` -- the caller may still want to save a PNG from it."""
    _configure_vector_fonts()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="pdf")
    buffer.seek(0)
    return buffer.getvalue()


def save_png_bytes(fig, dpi: int = PNG_EXPORT_DPI) -> bytes:
    """Saves `fig` as a PNG at `dpi` and returns the raw bytes."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    buffer.seek(0)
    return buffer.getvalue()


def export_poster_pdf_and_png(
    gdf,
    mapped_entries,
    missing_count: int = 0,
    layout: PosterLayout | None = None,
    insets=None,
    marker_reports=None,
    label_offsets: dict | None = None,
    png_dpi: int = PNG_EXPORT_DPI,
    debug_markers: bool = False,
) -> tuple[bytes, bytes]:
    """Builds the poster once and returns (pdf_bytes, png_bytes) -- the
    PDF and PNG are guaranteed to show the exact same composition. Closes
    the figure before returning to free memory."""
    fig = build_export_figure(
        gdf,
        mapped_entries,
        missing_count=missing_count,
        layout=layout,
        insets=insets,
        marker_reports=marker_reports,
        label_offsets=label_offsets,
        debug_markers=debug_markers,
    )
    try:
        pdf_bytes = save_pdf_bytes(fig)
        png_bytes = save_png_bytes(fig, dpi=png_dpi)
    finally:
        plt.close(fig)
    return pdf_bytes, png_bytes


def export_poster_pdf(gdf, mapped_entries, missing_count: int = 0, **kwargs) -> bytes:
    """Convenience single-format export (see `export_poster_pdf_and_png`
    for generating both from one figure)."""
    fig = build_export_figure(gdf, mapped_entries, missing_count=missing_count, **kwargs)
    try:
        return save_pdf_bytes(fig)
    finally:
        plt.close(fig)


def export_poster_png(
    gdf, mapped_entries, missing_count: int = 0, dpi: int = PNG_EXPORT_DPI, **kwargs
) -> bytes:
    """Convenience single-format export (see `export_poster_pdf_and_png`
    for generating both from one figure)."""
    fig = build_export_figure(gdf, mapped_entries, missing_count=missing_count, **kwargs)
    try:
        return save_png_bytes(fig, dpi=dpi)
    finally:
        plt.close(fig)
