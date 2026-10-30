# Active Helium Gateway Layer — test first

This replaces **neither** the municipality boundaries **nor** the legacy registered-hotspot snapshot. It is a third-party gateway-status layer, not measured LoRaWAN RF coverage. This API is not confirmed as a supported bulk-download interface; rate limits and access terms may change.

Files to replace/add in your local Sensors project:

- **ADD** `fetch_active_hotspots.py` in the repository root.
- **REPLACE** `index.html` to allow selecting reported active vs registered gateways.
- **REPLACE** `.github/workflows/refresh-helium.yml` to run the activity-specific refresh and commit `data/active_hexes.json` (no competing Pages deploy step; compatible with existing branch-based Pages settings).
- **KEEP** `fetch_boundaries.py`, `fetch_hotspots.py`, `data/municipalities.geojson`, and `data/hexes.json` unchanged.
- **GENERATE** `data/active_hexes.json` by running the new script.

Commands:

```bash
cd ~/Projects/Sensors
source .venv/bin/activate
cp index.html index.html.before-active.html
cp .github/workflows/refresh-helium.yml .github/workflows/refresh-helium.before-active.yml.bak
# copy supplied files into place
pip install -r requirements.txt
python fetch_active_hotspots.py --limit 5
python fetch_active_hotspots.py --delay 0.4
python -m http.server 8000
```

Open http://localhost:8000. Verify active gateway cells vs registered cells and cross-check at least 5 cells with Helium World before pushing to the shared repository. An H3 cell with zero reported active gateways is hidden in the active view.

If the API blocks full enumeration or if an unexpected response arrives, the script stops with an error and retains any prior `data/active_hexes.json`; do **not** silently label registered gateways active.

**Caution:** `git add .` may include your `.backup` files. Select only intended files when committing. Site publication through GitHub Pages is managed by the repository's existing branch-based Pages build. GitHub Actions refresh is separate.
