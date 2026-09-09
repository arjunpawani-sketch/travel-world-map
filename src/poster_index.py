"""
Chronological country/territory index layout: pure, Matplotlib-free logic
for turning the list of mapped visit records into balanced, strictly
chronological columns that fit a given page area. src/poster.py reads
this to actually draw text.

The index always uses the country/territory name exactly as entered in
the Excel sheet (never the matched geographic dataset's abbreviated name,
e.g. "Dem. Rep. Congo") and never an ISO code -- these are the traveller's
own records.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class IndexEntry:
    number: int
    name: str


def build_index_entries(mapped_entries) -> list[IndexEntry]:
    """One entry per mapped visit record, in chronological (visit number)
    order. `mapped_entries` is any iterable of objects exposing `.number`
    and `.country_raw` (see src.validation.MappedEntry)."""
    return [
        IndexEntry(number=m.number, name=m.country_raw)
        for m in sorted(mapped_entries, key=lambda m: m.number)
    ]


def choose_column_count(
    n_entries: int,
    index_height_in: float,
    index_width_in: float,
    font_size_pt: float,
    line_height_factor: float,
    min_column_width_in: float,
    column_gap_in: float,
) -> int:
    """Picks how many columns the index needs so that, read top-to-bottom
    then column-to-column, all `n_entries` fit within the index area at a
    genuinely readable font size -- rather than a fixed column count that
    would leave either awkward empty space or overflowing text as the
    Excel source grows."""
    if n_entries == 0:
        return 1
    row_height_in = (font_size_pt * line_height_factor) / 72.0
    max_rows_per_column = max(1, math.floor(index_height_in / row_height_in))
    columns_needed_for_height = math.ceil(n_entries / max_rows_per_column)

    max_columns_by_width = max(
        1,
        math.floor((index_width_in + column_gap_in) / (min_column_width_in + column_gap_in)),
    )
    return max(1, min(columns_needed_for_height, max_columns_by_width))


def build_index_columns(mapped_entries, num_columns: int) -> list[list[IndexEntry]]:
    """Splits the chronological entry list into `num_columns` near-equal,
    strictly chronological chunks -- column 1 holds the earliest visits,
    the last column the most recent, matching how someone would scan the
    poster (find a number on the map, then find it in roughly the
    corresponding column). Balanced (differs by at most one row between
    columns) rather than a fixed numeric range, since missing chronology
    numbers would otherwise leave uneven blank space in a fixed-range
    scheme."""
    entries = build_index_entries(mapped_entries)
    if not entries:
        return [[] for _ in range(num_columns)]

    n = len(entries)
    base, remainder = divmod(n, num_columns)
    columns = []
    start = 0
    for i in range(num_columns):
        size = base + (1 if i < remainder else 0)
        columns.append(entries[start : start + size])
        start += size
    return columns
