#!/usr/bin/env python3
"""Build DEM-derived closed-depression candidates and exaggerated hillshades.

Run from /home/igul/python_projects/usgs_3dep_dem.
Input: data/processed/5m/dem_municipalities.tif
Outputs in outputs/depression_zones/ and optionally a Leaflet data directory.

Important: clipped municipality boundaries are artificial drainage outlets. Zones
near NoData are excluded; buffered DEM data is needed for definitive assessment.
"""
import argparse
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_geom
from scipy import ndimage as ndi
from skimage.morphology import reconstruction
from PIL import Image


def make_hillshade(z, valid, dx, dy, exaggeration):
    # Vertical exaggeration is only used for the rendered hillshade, NEVER the hydrologic analysis.
    fill = float(np.median(z[valid]))
    arr = np.where(valid, z, fill).astype('float32')
    y, x = np.gradient(arr, dy, dx)
    nx = -x * exaggeration
    ny = -y * exaggeration
    nz = np.ones_like(nx)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    # Sun at azimuth 315 deg clockwise from north, elevation 45 deg.
    azi, alt = np.deg2rad(315), np.deg2rad(45)
    sx, sy, sz = np.sin(azi) * np.cos(alt), np.cos(azi) * np.cos(alt), np.sin(alt)
    shade = np.clip((nx*sx + ny*sy + nz*sz)/n, 0, 1)
    gray = np.uint8(np.round(255 * (0.2 + 0.8 * shade)))
    rgba = np.empty((*z.shape, 4), np.uint8)
    rgba[:, :, :3] = gray[:, :, None]
    rgba[:, :, 3] = np.where(valid, 210, 0).astype('uint8')
    return rgba


def write_kmz(zones, points, path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             '<name>DEM Closed Depression Candidates</name>',
             '<Style id="zone"><LineStyle><color>ff940071</color><width>1.6</width></LineStyle>'
             '<PolyStyle><color>777d26c1</color></PolyStyle></Style>',
             '<Style id="low"><IconStyle><color>ff00ffff</color><scale>0.7</scale></IconStyle></Style>']
    for f in zones['features']:
        p, geo = f['properties'], f['geometry']
        description = escape(f"Maximum fill depth: {p['max_depth_m']:.2f} m; Area: {p['area_m2']:.0f} m²; Candidate only")
        polys = geo['coordinates'] if geo['type']=='MultiPolygon' else [geo['coordinates']]
        geoms=[]
        for poly in polys:
            outer = ' '.join(f'{a},{b},0' for a,b in poly[0])
            inner = ''.join('<innerBoundaryIs><LinearRing><coordinates>'+ ' '.join(f'{a},{b},0' for a,b in hole) + '</coordinates></LinearRing></innerBoundaryIs>' for hole in poly[1:])
            geoms.append(f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>')
        lines.append(f'<Placemark><name>Depression {p["id"]}</name><description>{description}</description><styleUrl>#zone</styleUrl><MultiGeometry>{"".join(geoms)}</MultiGeometry></Placemark>')
    for f in points['features']:
        p=f['properties']; lon,lat=f['geometry']['coordinates']
        lines.append(f'<Placemark><name>Low point {p["id"]}</name><styleUrl>#low</styleUrl><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>')
    lines.append('</Document></kml>')
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('doc.kml','\n'.join(lines))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dem', type=Path, default=Path('data/processed/5m/dem_municipalities.tif'))
    parser.add_argument('--output', type=Path, default=Path('outputs/depression_zones'))
    parser.add_argument('--web-data', type=Path, default=None, help='Optional directory: Sensors/data')
    parser.add_argument('--min-depth', type=float, default=0.5, help='Minimum max fill depth in meters')
    parser.add_argument('--min-area', type=float, default=25, help='Minimum zone footprint in square meters')
    parser.add_argument('--footprint-depth', type=float, default=0.05, help='Small threshold for mapping filled depression footprint')
    parser.add_argument('--max-image-dimension', type=int, default=4000)
    a=parser.parse_args()
    if a.min_depth <= a.footprint_depth or a.min_area <= 0:
        parser.error('--min-depth must exceed --footprint-depth and --min-area must be positive')
    a.output.mkdir(parents=True, exist_ok=True)
    print('Reading DEM:',a.dem, flush=True)
    with rasterio.open(a.dem) as src:
        dem=src.read(1,masked=True).filled(np.nan).astype('float32')
        valid=np.isfinite(dem)
        if src.crs is None or not src.crs.is_projected:
            raise ValueError('DEM must use a projected CRS with meter coordinates')
        dx,dy=abs(src.res[0]),abs(src.res[1]);transform=src.transform;crs=src.crs
        src_bounds=src.bounds
        if not valid.any(): raise ValueError('DEM contains no valid pixels')
        print(f'Raster {src.width} x {src.height}, valid={valid.mean()*100:.1f}%, pixel={dx:.2f} x {dy:.2f} m',flush=True)
        print('Rendering exaggerated hillshade (1x, 3x, 5x)...',flush=True)
        # Reproject to 4326 so a Leaflet imageOverlay is correctly registered.
        dest_transform, dw, dh = calculate_default_transform(crs, 'EPSG:4326',src.width,src.height,*src.bounds)
        scale=min(1.0, a.max_image_dimension/max(dw,dh))
        if scale<1:
            nw=max(1,int(round(dw*scale))); nh=max(1,int(round(dh*scale)))
            from affine import Affine
            dest_transform=dest_transform * Affine.scale(dw/nw,dh/nh)
            dw,dh=nw,nh
        dst=np.full((dh,dw), np.nan, np.float32)
        reproject(source=dem, destination=dst,src_transform=transform,src_crs=crs,
                  dst_transform=dest_transform,dst_crs='EPSG:4326',src_nodata=np.nan,
                  dst_nodata=np.nan,resampling=Resampling.bilinear)
        mask=np.isfinite(dst)
        midlat=float(src_bounds.top+src_bounds.bottom)/2 # not used for projected lat
        lat_center= float(dest_transform.f + dest_transform.e*dh/2)
        map_dx=abs(dest_transform.a)*111320*np.cos(np.deg2rad(lat_center))
        map_dy=abs(dest_transform.e)*111132
        for v in [1,3,5]:
            fn=a.output/f'hillshade_{v}x.png'
            Image.fromarray(make_hillshade(dst,mask,map_dx,map_dy,v),'RGBA').save(fn,optimize=True)
            print(' ',fn,flush=True)
        # Upper left and lower right latlon for Leaflet imageOverlay.
        west=float(dest_transform.c); north=float(dest_transform.f)
        east=float(west+dest_transform.a*dw);south=float(north+dest_transform.e*dh)
    print('Priority-Flood-equivalent morphological reconstruction on actual DEM...',flush=True)
    # NoData is open outlet; construct lowest possible source elevations there.
    # Erosion reconstruction propagates the minimum spill elevation from outlets.
    outlet=-1000000.0
    mask_dem=np.where(valid, dem, outlet).astype('float32')
    seed=np.full(mask_dem.shape, float(np.nanmax(dem[valid])+1000),dtype='float32')
    seed[~valid]=outlet
    seed[0,:]=mask_dem[0,:]; seed[-1,:]=mask_dem[-1,:]
    seed[:,0]=mask_dem[:,0]; seed[:,-1]=mask_dem[:,-1]
    filled=reconstruction(seed, mask_dem, method='erosion',footprint=np.ones((3,3),bool)).astype('float32')
    depth=np.where(valid,np.maximum(filled-dem,0),0).astype('float32')
    del seed,filled,mask_dem
    footprint=valid & (depth >= a.footprint_depth)
    labels,count=ndi.label(footprint,structure=np.ones((3,3),np.uint8))
    if count==0:
        print('No candidate basins; creating empty layers.',flush=True)
    area_pixel=dx*dy
    sizes=np.bincount(labels.ravel(),minlength=count+1)
    max_depth=np.asarray(ndi.maximum(depth,labels,index=np.arange(1,count+1)),dtype='float64') if count else np.array([])
    accepted=(sizes[1:]*area_pixel >= a.min_area)&(max_depth >= a.min_depth)
    # If a candidate touches the municipal cut / NoData, reject it, rather than
    # treating a clipped valley as a closed basin.
    invalid_border=ndi.binary_dilation(~valid,structure=np.ones((3,3),bool),iterations=2)
    invalid_border[0,:]=True;invalid_border[-1,:]=True
    invalid_border[:,0]=True;invalid_border[:,-1]=True
    bad=np.unique(labels[invalid_border]);bad=bad[bad>0]
    accepted[bad-1]=False
    selected=np.flatnonzero(accepted)+1
    print(f'Raw connected regions: {count}; qualifying interior regions: {len(selected)}',flush=True)
    # Encode the selected labels in a raster for vectorization.
    lut=np.zeros(count+1,np.int32)
    lut[selected]=selected
    keep=lut[labels]
    zones={'type':'FeatureCollection','features':[]}
    points={'type':'FeatureCollection','features':[]}
    properties={}
    if len(selected):
        min_coords=ndi.minimum_position(dem, labels, index=selected.tolist())
        if len(selected)==1 and isinstance(min_coords,tuple): min_coords=[min_coords]
        for k, lab in enumerate(selected):
            r,c=min_coords[k]
            xx,yy=rasterio.transform.xy(transform,r,c,offset='center')
            from pyproj import Transformer
            if k==0: tr=Transformer.from_crs(crs,'EPSG:4326',always_xy=True)
            lon,lat=tr.transform(xx,yy)
            p={'id':int(lab),'max_depth_m':round(float(max_depth[lab-1]),3),
               'area_m2':round(float(sizes[lab]*area_pixel),1),
               'low_elevation_m':round(float(dem[r,c]),3),
               'low_lat':round(float(lat),8),'low_lon':round(float(lon),8),
               'screening_only':True}
            properties[int(lab)]=p
            points['features'].append({'type':'Feature','properties':p.copy(),'geometry':{'type':'Point','coordinates':[lon,lat]}})
        del min_coords
        for geometry,idx in shapes(keep,mask=keep>0,transform=transform,connectivity=8):
            lab=int(idx)
            zones['features'].append({'type':'Feature','properties':properties[lab].copy(),
             'geometry':transform_geom(crs,'EPSG:4326',geometry,precision=7)})
    (a.output/'depression_areas.geojson').write_text(json.dumps(zones),encoding='utf-8')
    (a.output/'depression_points.geojson').write_text(json.dumps(points),encoding='utf-8')
    metadata={'bounds_latlon':[[south,west],[north,east]],'pixel_size_m':[dx,dy],
      'zone_count':len(zones['features']),'low_point_count':len(points['features']),
      'min_depth_m':a.min_depth,'min_area_m2':a.min_area,'footprint_depth_m':a.footprint_depth,
      'analysis':'closed depression candidates from raster reconstruction',
      'warning':'Boundary-clipped DEM: boundary-touching candidates excluded; not a flood hazard designation.'}
    (a.output/'depression_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    write_kmz(zones,points,a.output/'depressions_google_earth.kmz')
    if a.web_data:
        a.web_data.mkdir(parents=True,exist_ok=True)
        for name in ['depression_areas.geojson','depression_points.geojson','depression_metadata.json','hillshade_1x.png','hillshade_3x.png','hillshade_5x.png']:
            shutil.copy2(a.output/name,a.web_data/name)
        print('Copied web layers to',a.web_data,flush=True)
    print('COMPLETE:',a.output,flush=True)
    print('Note: 3x/5x exaggerated hillshade changes the appearance only; depression depths use original elevations.',flush=True)

if __name__=='__main__':main()
