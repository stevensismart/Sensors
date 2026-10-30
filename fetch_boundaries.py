#!/usr/bin/env python3
"""Generate the project municipality boundaries from 2024 NJ Census COUSUB shapefiles.

To add another municipality, add its exact Census NAME and county FIPS below.
For Washington Township (Bergen), the Census NAME is 'Washington'; we retain
'Washington Twp' as the display name matching the legacy pin inventory.
"""
import io
import json
from pathlib import Path
import zipfile
import requests
import shapefile

# Keys = names displayed in app; values = (Census NAME, county FIPS).
MUNICIPALITIES = {
    'Carlstadt': ('Carlstadt', '003'),
    'Cliffside Park': ('Cliffside Park', '003'),
    'East Rutherford': ('East Rutherford', '003'),
    'Edgewater': ('Edgewater', '003'),
    'Fairview': ('Fairview', '003'),
    'Lyndhurst': ('Lyndhurst', '003'),
    'North Arlington': ('North Arlington', '003'),
    'Passaic': ('Passaic', '031'),
    'Ridgefield': ('Ridgefield', '003'),
    'Rutherford': ('Rutherford', '003'),
    'Wallington': ('Wallington', '003'),
    'Wood-Ridge': ('Wood-Ridge', '003'),
    # Legacy sites: 10 more municipalities
    'Emerson': ('Emerson', '003'),
    'Hillsdale': ('Hillsdale', '003'),
    'Montvale': ('Montvale', '003'),
    'Old Tappan': ('Old Tappan', '003'),
    'Oradell': ('Oradell', '003'),
    'Park Ridge': ('Park Ridge', '003'),
    'River Vale': ('River Vale', '003'),
    'Washington Twp': ('Washington', '003'),
    'Westwood': ('Westwood', '003'),
    'Woodcliff Lake': ('Woodcliff Lake', '003'),
}
SOURCE='https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_34_cousub_500k.zip'

def main():
    wanted={(census,county):label for label,(census,county) in MUNICIPALITIES.items()}
    if len(wanted)!=len(MUNICIPALITIES):
        raise RuntimeError('Duplicate Census municipality mapping')
    response=requests.get(SOURCE,timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        members={Path(name).suffix.lower():name for name in zf.namelist()
                 if Path(name).suffix.lower() in ('.shp','.shx','.dbf')}
        reader=shapefile.Reader(
            shp=io.BytesIO(zf.read(members['.shp'])),
            shx=io.BytesIO(zf.read(members['.shx'])),
            dbf=io.BytesIO(zf.read(members['.dbf'])))
        found={}
        for record in reader.iterShapeRecords():
            p=record.record.as_dict()
            census=p.get('NAME');county=p.get('COUNTYFP')
            label=wanted.get((census,county))
            if label is None: continue
            if label in found:
                raise RuntimeError(f'Duplicate record for {label}')
            found[label]={
                'type':'Feature',
                'properties':{'name':label,'census_name':census,
                              'county_fips':county,'geoid':p.get('GEOID')},
                'geometry':record.shape.__geo_interface__,
            }
    missing=sorted(set(MUNICIPALITIES)-set(found))
    if missing:
        raise RuntimeError(f'Missing municipalities: {missing}; found: {sorted(found)}')
    path=Path(__file__).resolve().parent/'data'/'municipalities.geojson'
    path.parent.mkdir(parents=True,exist_ok=True)
    data={'type':'FeatureCollection','features':[found[n] for n in sorted(found)]}
    path.write_text(json.dumps(data,separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Wrote {len(found)} municipalities to {path}')
    for n in sorted(found):print(f'  {n} ({found[n]["properties"]["geoid"]})')

if __name__=='__main__':main()
