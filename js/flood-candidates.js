/* Independent flood screening layer. Loaded after the existing map script. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const layer = L.layerGroup();
  const colors = {'Fluvial':'#1f6fd1','Pluvial':'#8e44ad','Fluvial + pluvial':'#e67e22'};
  let sites = [], loaded = false;
  const selected = () => sites.filter(f => ['Town','Exp','Pri'].every((suffix,i) => !el('flood'+suffix).value || f.properties[['town','exp','pri'][i]] === el('flood'+suffix).value));
  function currentGateways(f) {
    if (!activeCells.length) return 'Unavailable: active dataset not loaded';
    const [lng,lat] = f.geometry.coordinates;
    const resolutions = [...new Set(activeCells.map(c => h3.getResolution(c.h3)))];
    if (resolutions.length !== 1) return 'Unavailable: mixed H3 resolutions';
    const cell = h3.latLngToCell(lat,lng,resolutions[0]);
    const match = activeCells.find(c => c.h3 === cell);
    return match ? String(match.active_count ?? 'Unknown') : 'Not listed in loaded active dataset';
  }
  function popup(f) {
    const p=f.properties, box=document.createElement('div');
    const heading=document.createElement('strong'); heading.textContent=p.id+' · '+p.town; box.appendChild(heading);
    const rows=[['Screening priority',p.pri],['Exposure',p.exp],['Nearest address',p.addr],['Source / feature',p.src],['FEMA zone',p.zone],['Static BFE (ft)',p.bfe],['FEMA cross-section',p.xs],['Depression depth (m)',p.dep],['Ponded area (m²)',p.area],['Ponding storage (m³)',p.vol],['Contributing area (m²)',p.ca],['Ground elevation (m NAVD88)',p.elev],['Distance to FEMA stream (m)',p.distance],['DEM cell size (m N-S)',p.dem],['Source H3 cell',p.h3],['Gateways in loaded active dataset cell',currentGateways(f)],['Active dataset retrieved',activeMeta.retrieved_utc||activeMeta.observed_utc||'Unknown'],['Source gateway snapshot (2026-11-13 17:18 UTC)',p.source_gateway_count_snapshot],['1% floodplain fraction of hex/town overlap',p.pct1],['0.2% zone fraction of hex/town overlap',p.pct02],['Selection basis',p.basis],['Earlier pins in same cell',p.existing],['Notes',p.note],['Mounting feasibility',p.installation_feasibility],['Validation','Source reconciled; GIS and field assessment unverified']];
    for (const [label,value] of rows) if(value!==null && value!==undefined && value!=='') {
      const line=document.createElement('div'); const title=document.createElement('b'); title.textContent=label+': '; line.append(title,document.createTextNode(String(value))); box.appendChild(line);
    }
    return box;
  }
  function render() {
    layer.clearLayers(); el('floodList').replaceChildren();
    const rows=selected(); el('floodCount').textContent=loaded?rows.length.toLocaleString():'—';
    el('zoomFlood').disabled=!rows.length;
    if(el('showFlood').checked) layer.addTo(map); else map.removeLayer(layer);
    for(const f of rows) {
      const p=f.properties,[lng,lat]=f.geometry.coordinates;
      const marker=L.circleMarker([lat,lng],{radius:({'1':9,'2':7,'3':5})[p.pri[0]],color:colors[p.exp],fillColor:colors[p.exp],fillOpacity:.85,weight:2}).bindPopup(()=>popup(f),{maxWidth:360}).addTo(layer);
      const button=document.createElement('button');button.type='button';button.className='legacy-site-item';button.style.borderLeftColor=colors[p.exp];button.textContent=p.id+' · '+p.pri+' · '+p.exp+' · '+p.town+' · '+p.addr;
      button.addEventListener('click',()=>{el('showFlood').checked=true;layer.addTo(map);map.setView([lat,lng],17);marker.openPopup();});el('floodList').appendChild(button);
    }
  }
  ['showFlood','floodTown','floodExp','floodPri'].forEach(id=>el(id).addEventListener('change',render));
  window.addEventListener('helium-data-ready',render);
  el('zoomFlood').addEventListener('click',()=>{const rows=selected();if(!rows.length)return;el('showFlood').checked=true;render();map.fitBounds(L.latLngBounds(rows.map(f=>[f.geometry.coordinates[1],f.geometry.coordinates[0]])).pad(.08),{maxZoom:16});});
  (async()=>{
    try {
      const geo=await loadJSON('./data/flood_candidates.geojson');
      if(geo.type!=='FeatureCollection'||!Array.isArray(geo.features))throw Error('Expected a GeoJSON FeatureCollection');
      const ids=new Set();
      for(const f of geo.features) {
        const p=f.properties,c=f.geometry?.coordinates;
        if(f.type!=='Feature'||f.geometry?.type!=='Point'||!Array.isArray(c)||c.length!==2||!c.every(Number.isFinite)||Math.abs(c[0])>180||Math.abs(c[1])>90||!p||typeof p.id!=='string'||ids.has(p.id)||!p.town||!p.addr||!Object.hasOwn(colors,p.exp)||!['1 - High','2 - Medium','3 - Low'].includes(p.pri))throw Error('Invalid candidate or duplicate ID');
        ids.add(p.id);
      }
      sites=geo.features; loaded=true;
      for(const [suffix,key] of [['Town','town'],['Exp','exp'],['Pri','pri']])for(const value of [...new Set(sites.map(f=>f.properties[key]))].sort())el('flood'+suffix).add(new Option(value,value));
      el('floodStatus').textContent=sites.length+' screening candidates loaded. Independent filters apply only to this layer.';render();
    } catch(error) {
      el('floodStatus').textContent='Flood candidates could not load: '+error.message+'. Check data/flood_candidates.geojson and serve the map over HTTP.';el('floodStatus').classList.add('error');
    }
  })();
})();
