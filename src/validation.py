"""
Runs the Excel parser + geographic matcher together and packages the
results into a validation report: what's mapped, what's missing, what
failed to match, and anything duplicated or otherwise worth a human's
attention before the poster is generated.

Nothing here fabricates data. A missing visit number stays missing. An
unmatched name stays unmatched. The poster generator (later phases) is
expected to only draw entries with status == "matched".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Union

import geopandas as gpd

from .excel_parser import ParsedWorkbook, VisitRecord, parse_workbook
from .matcher import CountryMatcher, MatchResult


@dataclass
class MappedEntry:
    number: int
    country_raw: str
    region_raw: str | None
    entity_ids: list[int]
    matched_value: str
    match_type: str
    confidence: float | None


@dataclass
class UnresolvedEntry:
    number: int
    country_raw: str
    region_raw: str | None
    status: str  # "unmatched" | "ambiguous"
    candidates: list[str] | None


@dataclass
class ValidationReport:
    parsed: ParsedWorkbook
    mapped: list[MappedEntry] = field(default_factory=list)
    unresolved: list[UnresolvedEntry] = field(default_factory=list)
    missing_numbers: list[int] = field(default_factory=list)
    duplicate_numbers: dict[int, list[str]] = field(default_factory=dict)
    duplicate_country_names: dict[str, list[int]] = field(default_factory=dict)

    @property
    def mapped_count(self) -> int:
        return len(self.mapped)

    @property
    def unmatched_count(self) -> int:
        return sum(1 for u in self.unresolved if u.status == "unmatched")

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for u in self.unresolved if u.status == "ambiguous")

    @property
    def missing_count(self) -> int:
        return len(self.missing_numbers)

    @property
    def highest_number(self) -> int:
        all_numbers = [r.number for r in self.parsed.records]
        return max(all_numbers) if all_numbers else 0

    def summary_lines(self) -> list[str]:
        lines = [
            f"{self.mapped_count} mapped locations",
            f"{self.missing_count} chronological numbers missing a country name",
            f"{self.unmatched_count} unrecognized country/territory name(s)",
            f"{self.ambiguous_count} ambiguous geographic match(es)",
        ]
        if self.duplicate_numbers:
            lines.append(f"{len(self.duplicate_numbers)} duplicated visit number(s)")
        if self.duplicate_country_names:
            lines.append(
                f"{len(self.duplicate_country_names)} country/territory name(s) visited more than once"
            )
        if self.parsed.warnings:
            lines.append(f"{len(self.parsed.warnings)} row-level warning(s) from the Excel sheet")
        return lines


def build_validation_report(
    source: Union[str, Path, BinaryIO],
    gdf: gpd.GeoDataFrame,
    matcher: CountryMatcher | None = None,
) -> ValidationReport:
    parsed = parse_workbook(source)
    if matcher is None:
        matcher = CountryMatcher(gdf)

    report = ValidationReport(parsed=parsed)

    seen_numbers: dict[int, list[VisitRecord]] = {}
    seen_countries: dict[str, list[int]] = {}
    for record in parsed.records:
        seen_numbers.setdefault(record.number, []).append(record)
        seen_countries.setdefault(record.country_raw, []).append(record.number)

    report.duplicate_numbers = {
        num: [r.country_raw for r in recs]
        for num, recs in seen_numbers.items()
        if len(recs) > 1
    }
    report.duplicate_country_names = {
        name: nums for name, nums in seen_countries.items() if len(nums) > 1
    }

    for record in parsed.records:
        result: MatchResult = matcher.match(record.country_raw)
        if result.status == "matched":
            report.mapped.append(
                MappedEntry(
                    number=record.number,
                    country_raw=record.country_raw,
                    region_raw=record.region_raw,
                    entity_ids=result.entity_ids,
                    matched_value=result.matched_value,
                    match_type=result.match_type,
                    confidence=result.confidence,
                )
            )
        else:
            report.unresolved.append(
                UnresolvedEntry(
                    number=record.number,
                    country_raw=record.country_raw,
                    region_raw=record.region_raw,
                    status=result.status,
                    candidates=result.candidates,
                )
            )

    all_numbers = {r.number for r in parsed.records}
    if all_numbers:
        highest = max(all_numbers)
        report.missing_numbers = [n for n in range(1, highest + 1) if n not in all_numbers]

    return report
