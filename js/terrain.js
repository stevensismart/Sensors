/* USGS 3DEP elevation visualization, clipped client-side to the 22 municipal polygons.
   Does not download, modify, or store DEM rasters. Rendering is visual only. */
(() => {
  'use strict';
  const toggle = document.getElementById('showTerrain');
  const style = document.getElementById('terrainStyle');
  const opacity = document.getElementById('terrainOpacity');
  const status = document.getElementById('terrainStatus');
  const source = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage';
  const functions = {
    tinted: 'Hillshade Elevation Tinted',
    hillshade: 'Hillshade Gray-Stretch',
    slope: 'Slope Map'
  };
  const legend = document.getElementById('terrainLegend');
  // Fixed 5-meter classes, not a dynamic per-tile stretch. Values are meters;
  // the RGB class definitions below are shared with the on-page legend.
  const palette = [
    [0, '#2166ac'], [20, '#67a9cf'], [40, '#4daf8b'],
    [60, '#66bd63'], [80, '#d9ef8b'], [100, '#fee08b'],
    [120, '#fdae61'], [140, '#f46d43'], [180, '#d73027']
  ];
  function rgbAt(elevation) {
    if (elevation <= palette[0][0]) return [33,102,172];
    for (let i=1; i<palette.length; i++) {
      if (elevation <= palette[i][0]) {
        const [a,ac]=palette[i-1], [b,bc]=palette[i];
        const start=[1,3,5].map(x=>parseInt(ac.slice(x,x+2),16));
        const end=[1,3,5].map(x=>parseInt(bc.slice(x,x+2),16));
        const t=(elevation-a)/(b-a);
        return start.map((v,j)=>Math.round(v+(end[j]-v)*t));
      }
    }
    return [215,48,39];
  }
  function elevationRule() {
    // Remap continuous float DEM into integer elevation bins, then apply a custom
    // colormap. Below zero and above 180 m are clamped to the end colors.
    // This runs on the USGS server; no raw DEM bytes are exposed to the browser.
    const bounds=[-1000,0];
    for(let e=5;e<=180;e+=5) bounds.push(e);
    bounds.push(10000);
    const inputRanges=[], outputValues=[], colorMap=[];
    for(let i=0;i<bounds.length-1;i++) {
      inputRanges.push(bounds[i],bounds[i+1]);
      outputValues.push(i+1);
      const representative=i===0?0:Math.min(180,bounds[i]);
      colorMap.push([i+1,...rgbAt(representative)]);
    }
    return {
      rasterFunction:'Colormap',
      rasterFunctionArguments:{
        Colormap:colorMap,
        Raster:{
          rasterFunction:'Remap',
          rasterFunctionArguments:{InputRanges:inputRanges,OutputValues:outputValues,Raster:'$$'},
          outputPixelType:'U8'
        }
      },
      outputPixelType:'U8'
    };
  }
  let errors = 0;

  map.createPane('terrainPane');
  map.getPane('terrainPane').style.zIndex = '320';
  map.getPane('terrainPane').style.pointerEvents = 'none';

  function selectedFeatures() {
    const name = townEl.value;
    return (typeof boundaries !== 'undefined' ? boundaries : [])
      .filter(f => !name || normalizeName(f) === name);
  }

  function coordinatesToPolygons(g) {
    if (!g) return [];
    if (g.type === 'Polygon') return [g.coordinates];
    if (g.type === 'MultiPolygon') return g.coordinates;
    return [];
  }

  function paintMask(ctx, coords, size, features) {
    const x0 = coords.x * size.x, y0 = coords.y * size.y;
    ctx.beginPath();
    let rings = 0;
    for (const feature of features) {
      for (const polygon of coordinatesToPolygons(feature.geometry)) {
        for (const ring of polygon) {
          if (ring.length < 4) continue;
          for (let i = 0; i < ring.length; i++) {
            const xy = map.project([ring[i][1], ring[i][0]], coords.z);
            if (i === 0) ctx.moveTo(xy.x - x0, xy.y - y0);
            else ctx.lineTo(xy.x - x0, xy.y - y0);
          }
          ctx.closePath();
          rings++;
        }
      }
    }
    // GeoJSON outer and interior rings are handled with even-odd fill, including holes.
    if (rings) ctx.fill('evenodd');
  }

  const TerrainTiles = L.GridLayer.extend({
    createTile(coords, done) {
      const tile = document.createElement('canvas');
      const size = this.getTileSize();
      tile.width = size.x;
      tile.height = size.y;
      tile.setAttribute('aria-hidden', 'true');
      const features = selectedFeatures();
      if (!features.length) {
        done(null, tile);
        return tile;
      }

      // Skip image requests for tiles that cannot touch the selected study area.
      const tileBounds = L.latLngBounds(
        map.unproject([coords.x*size.x, (coords.y+1)*size.y], coords.z),
        map.unproject([(coords.x+1)*size.x, coords.y*size.y], coords.z)
      );
      const touching = features.filter(f => {
        const bounds = L.geoJSON(f).getBounds();
        return bounds.isValid() && bounds.intersects(tileBounds);
      });
      if (!touching.length) {
        done(null, tile);
        return tile;
      }

      const bbox = tileBBox3857(this, coords);
      const args = new URLSearchParams({
        f: 'image', bbox, bboxSR: '3857', imageSR: '3857',
        size: `${size.x},${size.y}`, format: 'png32',
        renderingRule: JSON.stringify(style.value === 'heatmap' ? elevationRule() : {rasterFunction: functions[style.value] || functions.tinted})
      });
      const image = new Image();
      image.crossOrigin = 'anonymous'; // Required for safe canvas clipping.
      image.onload = () => {
        try {
          const ctx = tile.getContext('2d');
          ctx.drawImage(image, 0, 0, size.x, size.y);
          ctx.globalCompositeOperation = 'destination-in';
          ctx.fillStyle = '#000';
          paintMask(ctx, coords, size, touching);
          ctx.globalCompositeOperation = 'source-over';
          done(null, tile);
        } catch (err) {
          tile.getContext('2d').clearRect(0,0,size.x,size.y);
          reportError(err);
          done(err, tile);
        }
      };
      image.onerror = () => {
        const err = new Error('USGS 3DEP tile request failed (network, CORS, or image service)');
        reportError(err);
        done(err, tile);
      };
      image.src = source + '?' + args;
      return tile;
    }
  });

  const terrain = new TerrainTiles({
    pane: 'terrainPane', opacity: Number(opacity.value)/100,
    maxZoom: 19, updateWhenIdle: true,
    attribution: 'Elevation visualization: USGS 3DEP / The National Map'
  });

  function reportError(err) {
    errors++;
    if (errors === 1) {
      console.warn('USGS terrain overlay:', err);
      status.textContent = 'Unable to render USGS terrain tiles. Check browser console and network/CORS access to the USGS ImageServer.';
      status.classList.add('error');
    }
  }

  function update() {
    legend.hidden = !toggle.checked || style.value !== 'heatmap';
    if (!toggle.checked) {
      map.removeLayer(terrain);
      status.textContent = 'Terrain layer hidden.';
      status.classList.remove('error');
      return;
    }
    if (!selectedFeatures().length) {
      map.removeLayer(terrain);
      status.textContent = 'Waiting for municipality boundaries to load.';
      return;
    }
    errors = 0;
    status.classList.remove('error');
    status.textContent = 'USGS 3DEP terrain enabled; clipped to ' + (townEl.value || 'all study municipalities') + '. Terrain colors are not measured flood depths.';
    terrain.setOpacity(Number(opacity.value)/100);
    if (!map.hasLayer(terrain)) terrain.addTo(map);
    else terrain.redraw();
  }

  toggle.addEventListener('change', update);
  style.addEventListener('change', () => { if (toggle.checked) update(); });
  opacity.addEventListener('input', () => { terrain.setOpacity(Number(opacity.value)/100); });
  townEl.addEventListener('change', () => { if (toggle.checked) update(); });
  document.getElementById('reset').addEventListener('click', () => {
    // Reset button sets townEl.value in the main script before this handler.
    if (toggle.checked) update();
  });
  window.addEventListener('municipality-boundaries-ready', () => { if (toggle.checked) update(); });
  update();
})();
