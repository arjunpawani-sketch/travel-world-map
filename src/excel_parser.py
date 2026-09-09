"""
Parses the traveller's Excel workbook into a plain list of visit records.

The workbook is the single source of truth for chronological visit numbers.
This module never invents, guesses, or fills in data -- it only reads what
is there and reports, via warnings, anything that looks malformed so the
caller can surface it in the validation screen instead of crashing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Union

import openpyxl

# Header cells are matched case-insensitively against these patterns.
NUMBER_HEADER_PATTERNS = ("number",)
COUNTRY_HEADER_PATTERNS = ("country", "territory")
REGION_HEADER_PATTERNS = ("region",)

# Sheet name is matched case-insensitively against this substring, in order.
PREFERRED_SHEET_NAME_PATTERNS = ("master list", "master")

MAX_HEADER_SCAN_ROWS = 15


class WorkbookFormatError(Exception):
    """Raised when the workbook does not look like a usable visit list."""


@dataclass
class VisitRecord:
    number: int
    country_raw: str
    region_raw: str | None
    source_row: int  # 1-indexed Excel row, for error messages


@dataclass
class ParsedWorkbook:
    records: list[VisitRecord]
    sheet_name: str
    header_row: int
    warnings: list[str] = field(default_factory=list)


def _find_sheet_name(sheet_names: list[str]) -> str:
    lower = {name.lower(): name for name in sheet_names}
    for pattern in PREFERRED_SHEET_NAME_PATTERNS:
        for lower_name, original in lower.items():
            if pattern in lower_name:
                return original
    # Fall back to the first sheet.
    return sheet_names[0]


def _matches_any(cell_value: object, patterns: tuple[str, ...]) -> bool:
    if not isinstance(cell_value, str):
        return False
    lowered = cell_value.strip().lower()
    return any(p in lowered for p in patterns)


def _find_header_row(rows: list[tuple]) -> tuple[int, int, int, int | None]:
    """
    Scans the first few rows for one containing Number / Country / Region
    headers. Returns (header_row_index_0based, number_col, country_col, region_col).
    region_col may be None if no region column is found (region is optional).
    """
    for row_idx, row in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        number_col = None
        country_col = None
        region_col = None
        for col_idx, cell in enumerate(row):
            if number_col is None and _matches_any(cell, NUMBER_HEADER_PATTERNS):
                number_col = col_idx
            if country_col is None and _matches_any(cell, COUNTRY_HEADER_PATTERNS):
                country_col = col_idx
            if region_col is None and _matches_any(cell, REGION_HEADER_PATTERNS):
                region_col = col_idx
        if (
            number_col is not None
            and country_col is not None
            and number_col != country_col
            and region_col != number_col
            and region_col != country_col
        ):
            return row_idx, number_col, country_col, region_col

    raise WorkbookFormatError(
        "Could not find a header row with 'Number' and 'Country / Territory' "
        "columns in the first "
        f"{MAX_HEADER_SCAN_ROWS} rows. Please check the workbook has these "
        "column headers somewhere near the top of the sheet."
    )


def parse_workbook(source: Union[str, Path, BinaryIO]) -> ParsedWorkbook:
    """
    Parses an Excel workbook of chronological visit entries.

    `source` may be a file path or a file-like object (e.g. a Streamlit
    UploadedFile), so this works for both the bundled default file and a
    user-uploaded replacement.
    """
    try:
        wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    except Exception as exc:
        raise WorkbookFormatError(
            f"This file could not be read as an Excel workbook ({exc}). "
            "Please upload a valid .xlsx file."
        ) from exc

    if not wb.sheetnames:
        raise WorkbookFormatError("The workbook has no sheets.")

    sheet_name = _find_sheet_name(wb.sheetnames)
    ws = wb[sheet_name]
    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        raise WorkbookFormatError(f"The '{sheet_name}' sheet is empty.")

    header_idx, number_col, country_col, region_col = _find_header_row(all_rows)

    records: list[VisitRecord] = []
    warnings: list[str] = []

    for offset, row in enumerate(all_rows[header_idx + 1 :]):
        excel_row = header_idx + 1 + offset + 1  # 1-indexed for humans

        number_val = row[number_col] if number_col < len(row) else None
        country_val = row[country_col] if country_col < len(row) else None
        region_val = (
            row[region_col] if region_col is not None and region_col < len(row) else None
        )

        if number_val is None and (country_val is None or str(country_val).strip() == ""):
            continue  # blank row, skip silently

        if country_val is not None and str(country_val).strip() == "":
            country_val = None

        if number_val is None:
            warnings.append(
                f"Row {excel_row}: has a country/territory ('{country_val}') "
                "but no visit number -- skipped. Fix this in the source Excel file."
            )
            continue

        try:
            number = int(number_val)
        except (TypeError, ValueError):
            warnings.append(
                f"Row {excel_row}: visit number '{number_val}' is not a whole "
                "number -- skipped. Fix this in the source Excel file."
            )
            continue

        if country_val is None:
            warnings.append(
                f"Row {excel_row}: visit number {number} has no country/territory "
                "name -- treated as a missing entry."
            )
            continue

        region_str = str(region_val).strip() if region_val is not None else None

        records.append(
            VisitRecord(
                number=number,
                country_raw=str(country_val).strip(),
                region_raw=region_str,
                source_row=excel_row,
            )
        )

    return ParsedWorkbook(
        records=records,
        sheet_name=sheet_name,
        header_row=header_idx + 1,
        warnings=warnings,
    )
