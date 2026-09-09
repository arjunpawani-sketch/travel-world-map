"""
Matches country/territory names from the Excel sheet against entities in
the Natural Earth geographic dataset.

Matching never guesses: a name either resolves to one or more known
geographic entities (via an exact field match, an explicit alias, or an
explicit composite-entity union), or it is reported as unmatched /
ambiguous for a human to resolve -- by editing data/country_aliases.json
or data/composite_entities.json, never by the app silently picking one.

A single visit entry can resolve to more than one geographic polygon: some
sovereign states the traveller may record as one entry (e.g. "United
Kingdom") have no single polygon in this dataset, only their constituent
home parts (England / Scotland / Wales / N. Ireland). For those, an entry
in composite_entities.json lists which real Natural Earth entities should
be unioned to represent it -- every part is still a genuine, official
polygon.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from rapidfuzz import fuzz, process

from .geography import MATCH_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALIASES_PATH = PROJECT_ROOT / "data" / "country_aliases.json"
COMPOSITES_PATH = PROJECT_ROOT / "data" / "composite_entities.json"

FUZZY_ACCEPT_THRESHOLD = 92
FUZZY_AMBIGUOUS_MARGIN = 3  # if 2nd-best score is within this of the best, it's ambiguous


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name)
    return " ".join(text.strip().split()).lower()


def _load_json_string_map(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_aliases() -> dict[str, str]:
    raw = _load_json_string_map(ALIASES_PATH)
    return {normalize(k): v for k, v in raw.items() if isinstance(v, str)}


def load_composites() -> dict[str, list[str]]:
    raw = _load_json_string_map(COMPOSITES_PATH)
    return {normalize(k): v for k, v in raw.items() if isinstance(v, list)}


@dataclass
class MatchResult:
    input_name: str
    status: str  # "matched" | "ambiguous" | "unmatched"
    entity_ids: list[int] | None = None  # >1 only for composite matches
    matched_value: str | None = None  # display name(s) it resolved to
    matched_field: str | None = None
    match_type: str | None = None  # "exact" | "alias" | "fuzzy" | "composite"
    confidence: float | None = None
    candidates: list[str] | None = None  # for ambiguous matches


class CountryMatcher:
    def __init__(
        self,
        gdf: gpd.GeoDataFrame,
        aliases: dict[str, str] | None = None,
        composites: dict[str, list[str]] | None = None,
    ):
        self.gdf = gdf
        self.aliases = aliases if aliases is not None else load_aliases()
        self.composites = composites if composites is not None else load_composites()
        self._field_indexes = self._build_field_indexes()
        self._fuzzy_choices = self._build_fuzzy_choices()

    def _build_field_indexes(self) -> dict[str, dict[str, list[int]]]:
        indexes: dict[str, dict[str, list[int]]] = {}
        for field in MATCH_FIELDS:
            index: dict[str, list[int]] = {}
            for entity_id, value in self.gdf[field].items():
                if not isinstance(value, str) or not value.strip():
                    continue
                key = normalize(value)
                index.setdefault(key, []).append(entity_id)
            indexes[field] = index
        return indexes

    def _build_fuzzy_choices(self) -> dict[str, int]:
        """normalized NAME/NAME_LONG value -> entity_id, for fuzzy fallback."""
        choices: dict[str, int] = {}
        for field in ("NAME", "NAME_LONG"):
            for entity_id, value in self.gdf[field].items():
                if isinstance(value, str) and value.strip():
                    choices[normalize(value)] = entity_id
        return choices

    def _exact_lookup(self, normalized_name: str) -> MatchResult | None:
        for field in MATCH_FIELDS:
            candidates = self._field_indexes[field].get(normalized_name)
            if not candidates:
                continue
            unique_ids = sorted(set(candidates))
            if len(unique_ids) == 1:
                entity_id = unique_ids[0]
                return MatchResult(
                    input_name=normalized_name,
                    status="matched",
                    entity_ids=[entity_id],
                    matched_value=self.gdf.at[entity_id, "NAME"],
                    matched_field=field,
                    match_type="exact",
                    confidence=100.0,
                )
            # Same field value shared by multiple entities: ambiguous.
            return MatchResult(
                input_name=normalized_name,
                status="ambiguous",
                candidates=[self.gdf.at[eid, "NAME"] for eid in unique_ids],
            )
        return None

    def _composite_lookup(self, normalized_name: str) -> MatchResult | None:
        parts = self.composites.get(normalized_name)
        if not parts:
            return None
        entity_ids = []
        for part in parts:
            part_result = self._exact_lookup(normalize(part))
            if part_result is None or part_result.status != "matched":
                raise ValueError(
                    f"composite_entities.json entry for '{normalized_name}' "
                    f"references '{part}', which does not resolve to exactly "
                    "one entity in the geographic dataset. Fix this entry."
                )
            entity_ids.extend(part_result.entity_ids)
        return MatchResult(
            input_name=normalized_name,
            status="matched",
            entity_ids=entity_ids,
            matched_value=" + ".join(parts),
            matched_field="composite",
            match_type="composite",
            confidence=100.0,
        )

    def _resolve_direct(self, normalized_name: str) -> MatchResult | None:
        """Composite union or exact field match, in that order. Does not
        consult the alias table or fuzzy matching."""
        composite_result = self._composite_lookup(normalized_name)
        if composite_result is not None:
            return composite_result
        return self._exact_lookup(normalized_name)

    def match(self, raw_name: str) -> MatchResult:
        normalized = normalize(raw_name)

        # 1. Alias table (explicit, human-curated -- highest priority).
        alias_target = self.aliases.get(normalized)
        if alias_target is not None:
            result = self._resolve_direct(normalize(alias_target))
            if result is not None and result.status == "matched":
                result.input_name = raw_name
                result.match_type = "alias"
                return result
            if result is not None and result.status == "ambiguous":
                result.input_name = raw_name
                return result
            return MatchResult(input_name=raw_name, status="unmatched")

        # 2. Explicit composite-entity union or exact field match against
        #    the geographic dataset.
        result = self._resolve_direct(normalized)
        if result is not None:
            result.input_name = raw_name
            return result

        # 3. Fuzzy fallback.
        matches = process.extract(
            normalized,
            self._fuzzy_choices.keys(),
            scorer=fuzz.WRatio,
            limit=3,
        )
        if not matches:
            return MatchResult(input_name=raw_name, status="unmatched")

        best_value, best_score, _ = matches[0]
        if best_score < FUZZY_ACCEPT_THRESHOLD:
            return MatchResult(input_name=raw_name, status="unmatched")

        close_others = [
            m for m in matches[1:] if best_score - m[1] <= FUZZY_AMBIGUOUS_MARGIN
        ]
        if close_others:
            candidate_ids = {
                self._fuzzy_choices[m[0]]
                for m in matches
                if best_score - m[1] <= FUZZY_AMBIGUOUS_MARGIN
            }
            return MatchResult(
                input_name=raw_name,
                status="ambiguous",
                candidates=[self.gdf.at[eid, "NAME"] for eid in candidate_ids],
            )

        entity_id = self._fuzzy_choices[best_value]
        return MatchResult(
            input_name=raw_name,
            status="matched",
            entity_ids=[entity_id],
            matched_value=self.gdf.at[entity_id, "NAME"],
            matched_field="NAME/NAME_LONG (fuzzy)",
            match_type="fuzzy",
            confidence=float(best_score),
        )
