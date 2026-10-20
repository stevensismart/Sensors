#!/usr/bin/env python3
"""Download boundaries for 12 NJ municipalities from Census COUSUB data.

NJ county subdivisions correspond to municipalities (boroughs, cities, townships).
Requires: requests, pyshp (shapefile).
"""
import io
import json
from pathlib import Path
import zipfile

import requests
import shapefile

COUNTIES = {
    'Carlstadt': '003',
    'Cliffside Park': '003',
    'East Rutherford': '003',
    'Edgewater': '003',
    'Fairview': '003',
    'Lyndhurst': '003',
    'North Arlington': '003',
    'Passaic': '031',
    'Ridgefield': '003',
    'Rutherford': '003',
    'Wallington': '003',
    'Wood-Ridge': '003',
}
SOURCE = 'https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_34_cousub_500k.zip'


def main():
    response = requests.get(SOURCE, timeout=90)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        members = {Path(n).suffix.lower(): n for n in zf.namelist()
                   if Path(n).suffix.lower() in ('.shp', '.shx', '.dbf')}
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(members['.shp'])),
            shx=io.BytesIO(zf.read(members['.shx'])),
            dbf=io.BytesIO(zf.read(members['.dbf'])))
        found = {}
        for record in reader.iterShapeRecords():
            props = record.record.as_dict()
            name = props.get('NAME')
            county = props.get('COUNTYFP')
            if name not in COUNTIES or county != COUNTIES[name]:
                continue
            if name in found:
                raise RuntimeError(f'Duplicate municipality: {name} (GEOID {props.get("GEOID")})')
            found[name] = {
                'type': 'Feature',
                'properties': {'name': name, 'county_fips': county,
                               'geoid': props.get('GEOID')},
                'geometry': record.shape.__geo_interface__,
            }
    missing = sorted(set(COUNTIES) - set(found))
    if missing:
        raise RuntimeError(f'Missing boundaries: {missing}. Found: {sorted(found)}')
    output = Path(__file__).resolve().parent / 'data' / 'municipalities.geojson'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'type': 'FeatureCollection',
                                  'features': [found[name] for name in sorted(found)]}) + '\n',
                      encoding='utf-8')
    print(f'Wrote {output} with {len(found)} municipalities')
    for name in sorted(found):
        print(f'  {name}: {found[name]["properties"]["geoid"]}')


if __name__ == '__main__':
    main()
