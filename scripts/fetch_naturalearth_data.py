"""
One-time setup script: downloads and caches the Natural Earth geographic
dataset used by the Travel World Map app.

Dataset: Natural Earth 1:10m Cultural Vectors - Admin 0 - Map Units
Source:  https://www.naturalearthdata.com/downloads/10m-cultural-vectors/
License: Natural Earth data is public domain (no attribution legally
         required). A courtesy credit "Made with Natural Earth" is included
         in the poster footer.

Map Units (rather than plain Admin-0 Countries) is used because it breaks
out overseas territories and dependencies (Hong Kong, Macao, Puerto Rico,
Greenland, Guadeloupe, French Polynesia, Cook Islands, Scotland, Zanzibar,
etc.) as their own polygons, which a travel map needs.

Run once:
    python scripts/fetch_naturalearth_data.py

The app also calls this automatically on first run if the data is missing,
but running it explicitly is useful on a slow/unreliable connection.
"""
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "naturalearth"
DATASET_NAME = "ne_10m_admin_0_map_units"
ZIP_PATH = DATA_DIR / f"{DATASET_NAME}.zip"
EXTRACT_DIR = DATA_DIR / DATASET_NAME
SHP_PATH = EXTRACT_DIR / f"{DATASET_NAME}.shp"

SOURCE_URL = f"https://naturalearth.s3.amazonaws.com/10m_cultural/{DATASET_NAME}.zip"


def fetch() -> Path:
    """Download and extract the dataset if not already cached. Returns the .shp path."""
    if SHP_PATH.exists():
        return SHP_PATH

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Natural Earth data from {SOURCE_URL} ...")
    try:
        urlretrieve(SOURCE_URL, ZIP_PATH)
    except Exception as exc:
        raise RuntimeError(
            f"Could not download Natural Earth data automatically ({exc}). "
            f"Please download it manually from "
            f"https://www.naturalearthdata.com/downloads/10m-cultural-vectors/ "
            f"(file: {DATASET_NAME}.zip) and place the extracted shapefile at "
            f"{SHP_PATH}"
        ) from exc

    print("Extracting...")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(EXTRACT_DIR)

    if not SHP_PATH.exists():
        raise RuntimeError(
            f"Extraction completed but expected shapefile not found at {SHP_PATH}"
        )

    print(f"Done. Cached at {SHP_PATH}")
    return SHP_PATH


if __name__ == "__main__":
    try:
        path = fetch()
        print(f"Geographic dataset ready: {path}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
