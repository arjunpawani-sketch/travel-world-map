"""
Merges the two authoritative sources the traveller now maintains:

- Country_Number_Index.xlsx: authoritative for established CHRONOLOGICAL
  visit numbers. Never renumbered here.
- reconciliation.csv: authoritative for the expanded universe of
  CONFIRMED-VISITED countries/territories, but does not carry reliable
  chronological ordering of its own (see the month-level ordering check
  in the reconciliation report -- atlas_first_visit is too coarse to
  safely reorder or fill the 21 old chronology gaps).

Neither source is discarded, overwritten, or silently preferred over the
other. This module produces one merged view where a visit's
CONFIRMED-VISITED status and its NUMBERED status are two independent
flags, never conflated:

    confirmed_visited: bool   -- appears in either source
    chronology_known: bool    -- has an established old visit_number
    visit_number: int | None  -- the old chronological number, or None
    source_old_index: bool    -- present in Country_Number_Index.xlsx
    source_reconciliation: bool -- present in reconciliation.csv

A visit is never assigned a visit_number that didn't already exist in the
old Excel -- there is no code path in this module that invents one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .matcher import CountryMatcher
from .validation import ValidationReport

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECONCILIATION_CSV_PATH = PROJECT_ROOT / "reconciliation.csv"


def _entity_key(entity_ids) -> tuple[int, ...]:
    return tuple(sorted(entity_ids))


@dataclass
class ReconciledEntry:
    name: str
    entity_ids: list[int]
    matched_value: str
    confirmed_visited: bool = True
    chronology_known: bool = False
    visit_number: int | None = None
    source_old_index: bool = False
    source_reconciliation: bool = False
    region_raw: str | None = None
    internal_note: str | None = None  # not shown prominently on the poster


@dataclass
class UnresolvedReconciliationEntry:
    name: str
    source: str  # "old_index" | "reconciliation"
    status: str  # "unmatched" | "ambiguous"
    candidates: list[str] | None = None


@dataclass
class MergedReconciliationReport:
    entries: list[ReconciledEntry]
    unresolved: list[UnresolvedReconciliationEntry] = field(default_factory=list)
    csv_record_count: int = 0

    @property
    def confirmed_visited_count(self) -> int:
        return len(self.entries)

    @property
    def numbered_entries(self) -> list[ReconciledEntry]:
        return [e for e in self.entries if e.chronology_known]

    @property
    def pending_entries(self) -> list[ReconciledEntry]:
        return [e for e in self.entries if not e.chronology_known]

    @property
    def numbered_count(self) -> int:
        return len(self.numbered_entries)

    @property
    def pending_count(self) -> int:
        return len(self.pending_entries)

    @property
    def geographically_unresolved_count(self) -> int:
        return len(self.unresolved)

    def all_entity_ids(self) -> set[int]:
        ids: set[int] = set()
        for e in self.entries:
            ids.update(e.entity_ids)
        return ids

    def pending_entity_ids(self) -> set[int]:
        ids: set[int] = set()
        for e in self.pending_entries:
            ids.update(e.entity_ids)
        return ids


def load_reconciliation_csv(path: Path | None = None) -> pd.DataFrame:
    path = path or RECONCILIATION_CSV_PATH
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def build_merged_reconciliation(
    old_report: ValidationReport,
    matcher: CountryMatcher,
    csv_path: Path | None = None,
) -> MergedReconciliationReport:
    """Builds the merged confirmed-visited / chronology view described
    above. `old_report` must come from `build_validation_report` against
    the Excel with a matcher that has already loaded the current
    aliases/composites (so e.g. the old bare "Virgin Islands" entry
    resolves). `matcher` is used to resolve every reconciliation.csv row
    against the same geographic dataset -- never a second, different
    matcher instance.
    """
    csv_df = load_reconciliation_csv(csv_path)

    entries: list[ReconciledEntry] = []
    unresolved: list[UnresolvedReconciliationEntry] = []

    for u in old_report.unresolved:
        unresolved.append(
            UnresolvedReconciliationEntry(
                name=u.country_raw, source="old_index", status=u.status, candidates=u.candidates
            )
        )

    old_keys = {_entity_key(m.entity_ids) for m in old_report.mapped}

    csv_by_key: dict[tuple[int, ...], tuple[str, object]] = {}
    for _, row in csv_df.iterrows():
        name = row["country"]
        result = matcher.match(name)
        if result.status == "matched":
            key = _entity_key(result.entity_ids)
            if key not in csv_by_key:  # first occurrence wins; CSV has no true duplicates
                csv_by_key[key] = (name, result)
        else:
            unresolved.append(
                UnresolvedReconciliationEntry(
                    name=name, source="reconciliation", status=result.status, candidates=result.candidates
                )
            )

    # 1. Every old-source mapped visit: chronology preserved exactly.
    for m in old_report.mapped:
        key = _entity_key(m.entity_ids)
        also_in_csv = key in csv_by_key
        entries.append(
            ReconciledEntry(
                name=m.country_raw,
                entity_ids=list(m.entity_ids),
                matched_value=m.matched_value,
                confirmed_visited=True,
                chronology_known=True,
                visit_number=m.number,
                source_old_index=True,
                source_reconciliation=also_in_csv,
                region_raw=m.region_raw,
                internal_note=(
                    None
                    if also_in_csv
                    else "Present in established chronology; absent from latest reconciliation source."
                ),
            )
        )

    # 2. reconciliation.csv entries with no old-source match: confirmed
    #    visited, but chronology is NOT established -- no number invented.
    for key, (name, result) in csv_by_key.items():
        if key in old_keys:
            continue
        entries.append(
            ReconciledEntry(
                name=name,
                entity_ids=list(result.entity_ids),
                matched_value=result.matched_value,
                confirmed_visited=True,
                chronology_known=False,
                visit_number=None,
                source_old_index=False,
                source_reconciliation=True,
            )
        )

    entries.sort(key=lambda e: (e.visit_number is None, e.visit_number or 0, e.name))

    return MergedReconciliationReport(
        entries=entries, unresolved=unresolved, csv_record_count=len(csv_df)
    )
