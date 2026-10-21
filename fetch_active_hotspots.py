#!/usr/bin/env python3
"""Fetch Helium Tools gateway status in H3 r8 cells overlapping municipality polygons.

Third-party /v1/gateways/hex API, not a documented guaranteed service.
Does not measure signal coverage. Fails closed and never overwrites valid JSON on errors.
"""
import argparse
import datetime as dt
import json
import os
import tempfile
import time
from pathlib import Path

import h3
import requests
from shapely.geometry import shape, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parent
BASE = 'https://api-iot.heliumtools.org/v1/gateways/hex'
BOUNDARY_FILE = ROOT / 'data/municipalities.geojson'
OUTPUT = ROOT / 'data/active_hexes.json'


def polygon_for_cell(cell):
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])


def study_cells():
    geo = json.loads(BOUNDARY_FILE.read_text(encoding='utf-8'))
    geoms = {}
    for feature in geo.get('features', []):
        name = feature.get('properties', {}).get('name') or feature.get('properties', {}).get('NAME')
        if not name or name in geoms:
            raise ValueError(f'Missing or duplicate municipality name: {name}')
        geom = shape(feature['geometry'])
        if geom.is_empty or not geom.is_valid:
            raise ValueError(f'Invalid geometry: {name}')
        geoms[name] = geom
    if not geoms:
        raise ValueError('No municipality polygons')
    merged = unary_union(list(geoms.values()))
    # H3 polygon-to-cells includes centers inside; add neighbors so boundary-touching
    # cells are not lost, and retain only genuine geometric intersections.
    center_cells = h3.geo_to_cells(merged.__geo_interface__, 8)
    candidates = set(center_cells)
    for c in center_cells:
        candidates.update(h3.grid_disk(c, 1))
    # For very small polygons that contain no cell centers, seed from bbox corners
    # and polygon representative points, then apply the exact intersection check.
    for g in geoms.values():
        p = g.representative_point()
        candidates.update(h3.grid_disk(h3.latlng_to_cell(p.y, p.x, 8), 2))
    prepared = {n: prep(g) for n, g in geoms.items()}
    members = {}
    for c in candidates:
        poly = polygon_for_cell(c)
        if not merged.intersects(poly):
            continue
        names = [n for n, p in prepared.items() if p.intersects(poly)]
        if names:
            members[c] = sorted(names)
    if not members:
        raise RuntimeError('No intersecting H3 cells')
    return members


def get_gateway_list(session, cell, delay):
    for attempt in range(6):
        try:
            resp = session.get(f'{BASE}/{cell}', timeout=35)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f'HTTP {resp.status_code}')
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError('Expected JSON array of gateways')
            return data
        except (requests.RequestException, ValueError) as exc:
            if attempt == 5:
                raise RuntimeError(f'Could not download H3 cell {cell}: {exc}') from exc
            time.sleep(max(delay, 1) * (2 ** attempt))
    raise AssertionError('unreachable')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--delay', type=float, default=0.3)
    parser.add_argument('--limit', type=int, default=0,
                        help='Test N cells; no output is published in limit mode')
    args = parser.parse_args()
    members = study_cells()
    print(f'Querying {len(members)} municipality-intersecting H3 resolution-8 cells', flush=True)
    session = requests.Session()
    session.headers.update({'Accept': 'application/json',
        'User-Agent': 'Stevens-I-SMART-Sensors-Research/1.0'})
    rows = []
    unique = {}
    ordered = sorted(members)
    for idx, cell in enumerate(ordered[:args.limit] if args.limit else ordered, 1):
        gateways = get_gateway_list(session, cell, args.delay)
        addresses = set()
        for g in gateways:
            if not isinstance(g, dict) or not g.get('address'):
                raise RuntimeError(f'Unexpected gateway record in {cell}')
            # Do not coerce 0 to False: status=0 means active in observed API.
            active = g.get('statusString') == 'active'
            inactive = g.get('statusString') == 'inactive'
            if not (active or inactive):
                raise RuntimeError(f'Unknown gateway status in {cell}: {g.get("statusString")}')
            addresses.add(g['address'])
            prior = unique.get(g['address'])
            if prior is not None and prior != active:
                raise RuntimeError(f'Conflicting statuses for {g["address"]}')
            unique[g['address']] = active
        # Query is by H3 parent: count each gateway by its asserted location's
        # resolution-8 parent, not merely by membership in the response.
        active_ids = set()
        registered_ids = set()
        for g in gateways:
            fine = (g.get('location') or {}).get('hex')
            if fine and h3.is_valid_cell(fine):
                parent = h3.cell_to_parent(fine, 8)
            else:
                loc = g.get('location') or {}
                lat, lng = loc.get('lat'), loc.get('lng')
                if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
                    raise RuntimeError(f'Missing usable location for {g["address"]}')
                parent = h3.latlng_to_cell(lat, lng, 8)
            if parent != cell:
                raise RuntimeError(f'Gateway {g["address"]} unexpectedly maps to {parent}, not queried {cell}; investigate API query semantics')
            registered_ids.add(g['address'])
            if g['statusString'] == 'active':
                active_ids.add(g['address'])
        if registered_ids:
            rows.append({'h3': cell, 'count': len(active_ids),
                         'active_count': len(active_ids),
                         'registered_count': len(registered_ids),
                         'municipalities': members[cell]})
        if idx % 25 == 0 or idx == len(ordered):
            print(f'{idx}/{len(ordered)} cells; {len(unique)} unique gateways; '
                  f'{sum(unique.values())} active', flush=True)
        time.sleep(max(args.delay, 0))
    if args.limit:
        print('Test complete; --limit mode does NOT publish files')
        return
    if not rows or sum(r['active_count'] for r in rows) == 0:
        raise RuntimeError('No active gateway cells; retaining previous data')
    output = {'metadata': {
        'source': BASE, 'retrieved_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'complete': True, 'spatial_filter': 'h3_polygon_intersects_municipality',
        'h3_resolution': 8, 'cells_queried': len(ordered),
        'municipalities': sorted({n for ns in members.values() for n in ns}),
        'meaning': 'Third-party reported gateway activity; not measured RF coverage',
        'total_unique_gateways': len(unique), 'total_unique_active_gateways': sum(unique.values())},
        'cells': rows}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.active_hexes-', suffix='.json', dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
            f.write('\n')
        os.replace(tmp, OUTPUT)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f'Published {len(rows)} occupied H3 cells to {OUTPUT}')


if __name__ == '__main__':
    main()
