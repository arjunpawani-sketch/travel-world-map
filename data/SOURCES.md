# Data sources

## Geographic data

**Natural Earth** — 1:10m Cultural Vectors, Admin 0 - Map Units
(`ne_10m_admin_0_map_units`)

- Homepage: https://www.naturalearthdata.com/downloads/10m-cultural-vectors/
- Direct download used by `scripts/fetch_naturalearth_data.py`:
  https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_map_units.zip
- License: **Public domain.** Natural Earth data is free for any use,
  commercial or otherwise, with no attribution required
  (https://www.naturalearthdata.com/about/terms-of-use/). A courtesy credit
  ("Made with Natural Earth") is included in the poster footer regardless.
- Why "Map Units" and not plain "Admin 0 Countries": Map Units breaks out
  overseas territories and dependencies as their own polygons (Hong Kong,
  Macao, Puerto Rico, Greenland, Guadeloupe, Réunion, Martinique,
  French Polynesia, Cook Islands, U.S./British Virgin Islands, Scotland,
  Zanzibar, etc.), which a travel map needs and a UN-member-states-only
  dataset would not provide.
- Cached locally under `data/naturalearth/ne_10m_admin_0_map_units/` after
  the first run (or after running the fetch script). The app does not
  re-download on every run.

## Traveller visit data

The chronological country/territory list is supplied by the user as an
Excel workbook (default: `Country_Number_Index.xlsx` in the project root).
The app never modifies this source file — normalization happens only in
memory when matching names against the geographic dataset.
