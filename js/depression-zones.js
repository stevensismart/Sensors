/* Closed-depression polygons ONLY. No low-point markers are loaded or drawn. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const status = el('depressionZoneStatus');
  const renderer = L.canvas({padding: 0.3});
  const zones = L.geoJSON(null, {
    renderer,
    style: f => {
      const d = Number(f.properties?.max_depth_m || 0);
      const color = d >= 3 ? '#661073' : d >= 2 ? '#8b239e' : d >= 1 ? '#a64abb' : '#c48ad7';
      return {color, weight: 1.2, opacity: 0.95, fillColor: color, fillOpacity: 0.48};
    },
    onEachFeature: (f, layer) => {
      const p = f.properties || {};
      layer.bindPopup(`<b>DEM-derived closed depression area</b><br>Max fill depth: ${p.max_depth_m} m<br>Area: ${p.area_m2} m²<br>Lowest elevation: ${p.low_elevation_m} m<br><small>Topographic screening only, NOT FEMA flood zoning or predicted flooding.</small>`);
    }
  });

  map.createPane('exaggeratedTerrainPane');
  map.getPane('exaggeratedTerrainPane').style.zIndex = '315';
  map.getPane('exaggeratedTerrainPane').style.pointerEvents = 'none';
  map.createPane('depressionZonePane');
  map.getPane('depressionZonePane').style.zIndex = '440';
  let meta = null, allAreas = null, shade = null, shadeFactor = null;
  let loading = null;

  async function load() {
    if (allAreas) return;
    if (!loading) loading = Promise.all([
      './data/depression_metadata.json',
      './data/depression_areas.geojson'
    ].map(async url => {
      const r = await fetch(url, {cache:'no-store'});
      if (!r.ok) throw Error(`${url}: HTTP ${r.status}`);
      return r.json();
    })).then(([m, areas]) => {
      if (areas.type !== 'FeatureCollection' || !Array.isArray(areas.features)) throw Error('Invalid depression_areas.geojson');
      meta = m;
      allAreas = areas.features;
    }).catch(err => { loading = null; throw err; });
    return loading;
  }

  function updateZones() {
    zones.clearLayers();
    if (!el('showDepressionZones').checked) {
      map.removeLayer(zones);
      status.textContent = 'Closed depression areas hidden.';
      return;
    }
    const minArea = Number(el('depressionMinArea').value);
    const minDepth = Number(el('depressionMinDepth').value);
    const filtered = allAreas.filter(f =>
      Number(f.properties?.area_m2) >= minArea &&
      Number(f.properties?.max_depth_m) >= minDepth
    );
    zones.options.pane = 'depressionZonePane';
    zones.addData({type:'FeatureCollection',features:filtered});
    if (!map.hasLayer(zones)) zones.addTo(map);
    status.textContent = `${filtered.length.toLocaleString()} of ${allAreas.length.toLocaleString()} areas shown (area ≥ ${minArea} m², depth ≥ ${minDepth} m). No point markers.`;
  }

  function updateShade() {
    const factor = el('demExaggeration').value;
    el('demExaggerationValue').textContent = factor + '×';
    if (!el('showExaggeratedDem').checked) {
      if (shade) map.removeLayer(shade);
      return;
    }
    if (!shade || shadeFactor !== factor) {
      if (shade) map.removeLayer(shade);
      shade = L.imageOverlay(`./data/hillshade_${factor}x.png`, meta.bounds_latlon, {
        pane:'exaggeratedTerrainPane', opacity:0.72, interactive:false
      });
      shadeFactor = factor;
    }
    if (!map.hasLayer(shade)) shade.addTo(map);
  }

  async function update() {
    const need = el('showDepressionZones').checked || el('showExaggeratedDem').checked;
    if (!need) {
      map.removeLayer(zones);
      if (shade) map.removeLayer(shade);
      status.textContent = 'Analysis layers hidden.';
      return;
    }
    try {
      await load();
      updateZones();
      updateShade();
      status.classList.remove('error');
    } catch(err) {
      console.error('Depression areas:',err);
      status.classList.add('error');
      status.textContent = `Cannot load depression layers: ${err.message}`;
    }
  }
  ['showDepressionZones','showExaggeratedDem','demExaggeration','depressionMinArea','depressionMinDepth']
    .forEach(id => el(id).addEventListener('change', update));
})();
