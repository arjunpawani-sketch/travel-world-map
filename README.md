# Travel World Map

Turns a chronological Excel list of visited countries and territories into
a premium, print-quality A2 poster: an accurate world map with numbered
visit markers, four regional inset maps for dense areas, and a
chronological country index -- built entirely from real geographic data
and your Excel file, with no AI-generated imagery.

## Quick start (Windows)

**1. Activate the virtual environment**

Open a terminal in this folder (`travel-world-map`) and run:

```bash
.venv\Scripts\activate
```

If you haven't set it up yet:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/fetch_naturalearth_data.py
```

(The last step downloads the ~5MB geographic dataset once. After that the
app works offline.)

**2. Launch the app**

```bash
streamlit run app.py
```

This opens the app in your browser (usually `http://localhost:8501`).

**3. Use your Excel file**

The app starts with the bundled `Country_Number_Index.xlsx` already
loaded. To use an updated version, click **"Upload a replacement .xlsx
file"** near the top of the page and choose your file -- validation,
the map, and the poster all regenerate automatically. Nothing needs to be
typed into the app; everything comes from the Excel columns `Number`,
`Country / Territory`, and `Region(s)`.

**4. Check the validation summary**

Before looking at the poster, glance at the validation summary: how many
locations mapped, how many chronological numbers are missing from the
source, and whether any name didn't match a real place. Missing numbers
and unmatched names are never guessed -- fix them in the Excel file and
re-upload if you want them included.

**5. Download the poster**

Scroll to **"Poster preview"** and use:

- **Download A2 PDF** -- production-quality, vector where practical, true
  594mm x 420mm page size, ready to send to a print shop.
- **Download High-Resolution PNG** -- a 300 dpi raster image (about
  7016x4961 px), good for sharing or reviewing on screen.

Generating these takes under a minute (the on-screen preview above them
is a faster, lower-resolution stand-in so the page doesn't stall while
you're still checking the data).

## Where things live

- **Bundled Excel source**: `Country_Number_Index.xlsx` in this folder.
  Never edited by the app -- upload a new file to change what's mapped.
- **Downloads**: come straight from your browser's download dialog: no
  need to dig through this folder.
- **Optional output files**: `output/` contains PNG/PDF snapshots saved by
  the development review scripts (`scripts/render_*.py`), kept for
  reference -- not required for normal use.

## IMPORTANT

**Do not manually change ISO/geographic data unless fixing a real mapping
issue.** The traveller normally only needs to update the Excel file --
the app re-derives everything else (matching, highlighting, markers, the
index, the poster) automatically. The `data/*.json` files
(`country_aliases.json`, `composite_entities.json`, `label_offsets.json`,
`insets.json`, `poster_layout.json`) are configuration for genuine
geographic/layout edge cases, not something to touch for routine use.

## Development views

Toggle **"Show development views"** (off by default) to see the main map
and each regional inset rendered individually, plus a marker-debug overlay
(true anchor points, leader lines, collision reports). Useful for
diagnosing a specific placement, not needed for normal use.

## Run tests

```bash
python -m pytest tests/ -v
```

## How matching works

1. **Alias table** (`data/country_aliases.json`) -- hand-curated renames for
   abbreviations and naming differences (e.g. `UK` -> `United Kingdom`,
   `Czech Republic` -> `Czechia`).
2. **Composite entities** (`data/composite_entities.json`) -- for
   sovereign states that have no single polygon in the geographic dataset,
   only constituent parts (e.g. the United Kingdom is only present as
   separate England / Scotland / Wales / N. Ireland geo units, and Iraq is
   split into Iraq + Iraqi Kurdistan). These are unioned from real,
   official Natural Earth polygons -- nothing is invented.
3. **Exact match** against the Natural Earth dataset's name fields.
4. **Fuzzy match** (high-confidence only) as a last resort, for things
   like minor accent differences.

Anything that doesn't resolve cleanly is reported as unmatched or
ambiguous in the validation screen -- never guessed. See the `_comment`
and `_ambiguous_notes` keys in `data/country_aliases.json` for the current
known ambiguity (a bare "Virgin Islands" entry, which could be US or
British).

## Data sources

See [`data/SOURCES.md`](data/SOURCES.md).

## Project structure

```
app.py                  Streamlit UI
src/
  excel_parser.py       Reads the workbook into VisitRecord objects
  geography.py           Loads/caches the Natural Earth dataset
  matcher.py             Name -> geographic entity resolution
  validation.py          Orchestrates parser + matcher into a report
  labels.py               Marker placement, collision detection/resolution
  insets.py               Regional inset bounds/projection configuration
  poster.py               Matplotlib rendering: main map, insets, full poster
  poster_layout.py        Poster zone/typography configuration
  poster_index.py         Chronological index column layout (pure logic)
  export.py                Final PDF/PNG export
data/
  country_aliases.json      Name normalization (editable)
  composite_entities.json   Multi-polygon entity unions (editable)
  label_offsets.json        Marker display-target/offset overrides (editable)
  insets.json                Regional inset bounds/projection (editable)
  poster_layout.json         Poster zones, typography sizes (editable)
  naturalearth/               Cached geographic dataset (gitignored)
  SOURCES.md
scripts/
  fetch_naturalearth_data.py   One-time dataset download/cache
  render_phase*.py             Development review scripts (output/ images)
  render_final_export.py       Generates + QA-checks the production PDF/PNG
tests/
output/                  Generated PNG/PDF snapshots (gitignored except .gitkeep)
```
