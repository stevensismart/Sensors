# Helium IoT NJ — registry map (not verified coverage)

**Data caveat:** the official Helium Entity API lists *asserted/registered* hotspot locations. It does NOT report live online status or LoRaWAN RF coverage; `is_active` is deprecated. This project does not reproduce the Helium World live IoT map. **Do not infer sensor deployability from red hexagons.**

## Setup and run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fetch_boundaries.py
python fetch_hotspots.py
python -m http.server 8000
```
Open http://localhost:8000. Map uses OpenStreetMap public tiles (subject to its tile-use policy). No API key or payment card needed for this prototype.

## Features
- Official Census New Jersey county-subdivision boundaries for the 12 requested municipalities.
- Registered hotspot counts aggregated in H3 r8 cells, clipped to a study bounding box, filtered by municipality using cell centers.
- Minimum-hotspots-per-cell slider is **visual density filtering only**. It does NOT select active hotspots.
- Optional independent verified activity layer, disabled unless `data/verified_hexes.json` is supplied. Structure: `{ "metadata": { "source": "...", "retrieved_utc": "...", "complete": true }, "cells": [{"h3":"...", "count":1}] }`. Don't label data verified without a valid source and observation criteria.
- Timestamp and source-completeness display.

## Automatic daily refresh on GitHub Pages
Commit `data/municipalities.geojson` and `data/hexes.json` after successful local generation. Push this project's `.github/workflows/refresh-helium.yml`. GitHub Actions > Refresh Helium registered hotspots > Run workflow tests the downloader. Scheduled at 09:21 UTC daily (GitHub may delay scheduled runs). Set repository Settings > Actions > General > Workflow permissions to Read and write permissions if needed. For Pages choose Settings > Pages > Source: **GitHub Actions**. The refresh workflow commits data, uploads the static site, and deploys it directly. In Settings > Actions > General permit `GITHUB_TOKEN` read/write permissions if needed. GitHub Action may time out / API rate limit during full scan. Previous JSON remains if refresh fails.

## Limitations and next work
Matching Helium World's operational IoT layer requires access to its documented or authorized activity source, with semantics confirmed. The directory cannot be filtered by active status: API `is_active` is deprecated and always false. Do not generate a fake 'active' layer. Daily refresh updates registry assertions, not coverage. IoT PoC ceased July 2026; historical PoC cannot indicate present activity. Helium Oracle raw datasets may incur AWS Requester Pays charges. Public OSM tiles are subject to fair-use limits and not guaranteed production infrastructure.

Sources: https://docs.helium.com/network-data/entity-api/ ; https://docs.helium.com/network-data/oracle-data/ ; https://operations.osmfoundation.org/policies/tiles/


## Boundary-driven filtering (version 2)
Run `python fetch_boundaries.py` first. The hotspot downloader reads **all** features from `data/municipalities.geojson`, and saves only H3 cells whose polygon intersects at least one municipal polygon (including borders). Each saved cell has a `municipalities` list. The frontend filters by that list rather than using the cell center.

Adding/removing municipalities: update your boundary-generation configuration or supply an updated GeoJSON feature collection, commit that GeoJSON, and run `python fetch_hotspots.py` again. The webpage automatically populates its municipality dropdown from the GeoJSON. The daily workflow refreshes hotspots with the committed boundary file; it does not automatically change the municipality list.

**API limitation:** the Helium Entity API's documented list endpoint only supports `subnetwork` and `cursor`, not spatial query parameters. The downloader must paginate the worldwide IoT directory but only retains/publishes locally intersecting cells. No live connectivity is inferred.

Requires Shapely (`pip install -r requirements.txt`). The first run against an older bbox-based dataset intentionally bypasses the 50% size-drop safety test because it changes geographic scope.
