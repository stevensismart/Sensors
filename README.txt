Deployment fix for stevensismart/Sensors

1. Replace only .github/workflows/refresh-helium.yml with this file.
2. Ensure data/active_hexes.json, data/hexes.json, data/municipalities.geojson and fetch_active_hotspots.py are tracked and committed.
3. GitHub repository Settings > Pages > Source: GitHub Actions (requires lab repo admin/maintainer rights).
4. GitHub Actions workflow permissions need to allow commits to main. Organizational branch protection may prevent bot pushes.
5. On push: deploy committed JSON immediately without re-fetching.
6. On schedule/manual dispatch: fetch activity, validate, commit and explicitly deploy the artifact.
7. This workflow refreshes ONLY active_hexes.json, NOT registered hexes.json.
8. Data may lag Helium World; activity definitions and API rate limits are third-party and not guaranteed.
9. Scheduled workflows can be disabled after 60 days public-repo inactivity. Monitor Actions regularly.
10. Compare several known H3 cells with official map before promoting data for field planning.
