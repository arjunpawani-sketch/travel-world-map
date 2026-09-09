"""
Loads the Natural Earth geographic dataset used to place and draw countries
and territories on the map.

See data/SOURCES.md for dataset details and license.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_NAME = "ne_10m_admin_0_map_units"
SHP_PATH = (
    PROJECT_ROOT
    / "data"
    / "naturalearth"
    / DATASET_NAME
    / f"{DATASET_NAME}.shp"
)

# Dataset fields checked, in priority order, when matching a name from the
# Excel sheet against a geographic entity. Earlier fields are more specific
# and are preferred when multiple fields could match.
MATCH_FIELDS = ["NAME", "NAME_LONG", "FORMAL_EN", "ABBREV", "GEOUNIT", "ADMIN"]

# Columns kept from the (very wide) Natural Earth attribute table -- the
# rest are dropped to keep things simple downstream.
KEEP_COLUMNS = [
    "NAME",
    "NAME_LONG",
    "FORMAL_EN",
    "ABBREV",
    "GEOUNIT",
    "ADMIN",
    "SOVEREIGNT",
    "TYPE",
    "CONTINENT",
    "SUBREGION",
    "LABEL_X",
    "LABEL_Y",
    "geometry",
]


class GeographicDataUnavailable(Exception):
    pass


def ensure_dataset() -> Path:
    """Makes sure the Natural Earth shapefile is present locally, downloading
    it once if necessary. Returns the path to the .shp file."""
    if SHP_PATH.exists():
        return SHP_PATH

    scripts_dir = PROJECT_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import fetch_naturalearth_data  # noqa: E402

        return fetch_naturalearth_data.fetch()
    except Exception as exc:
        raise GeographicDataUnavailable(
            "The Natural Earth geographic dataset is not available and could "
            f"not be downloaded automatically ({exc}). Run "
            "`python scripts/fetch_naturalearth_data.py` manually, or check "
            "your internet connection."
        ) from exc


def load_geodata() -> gpd.GeoDataFrame:
    """Loads the Admin-0 map units dataset as a GeoDataFrame with a plain
    integer index, keeping only the columns this app actually uses."""
    shp_path = ensure_dataset()
    gdf = gpd.read_file(shp_path)
    gdf = gdf[KEEP_COLUMNS].reset_index(drop=True)
    gdf.index.name = "entity_id"
    return gdf
