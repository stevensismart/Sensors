/*
 * Southern NJ Municipality Boundaries
 * Loads the original GeoJSON independently of other filters.
 * Displays exactly the 12 selected municipalities.
 */
(() => {
  'use strict';

  const SOUTHERN_TOWNS = new Set([
    'Carlstadt',
    'Cliffside Park',
    'East Rutherford',
    'Edgewater',
    'Fairview',
    'Lyndhurst',
    'North Arlington',
    'Passaic',
    'Ridgefield',
    'Rutherford',
    'Wallington',
    'Wood-Ridge'
  ]);

  const checkbox = document.getElementById('showBounds');

  // Require the existing Leaflet map and checkbox.
  if (typeof map === 'undefined' ||
      typeof L === 'undefined' ||
      !checkbox) {
    console.error(
      'Southern boundaries: Leaflet map or checkbox unavailable.'
    );
    return;
  }

  // Create a dedicated pane above hotspot polygons.
  if (!map.getPane('southernBoundaryPane')) {
    map.createPane('southernBoundaryPane');
  }

  const pane = map.getPane('southernBoundaryPane');
  pane.style.zIndex = '430';
  pane.style.pointerEvents = 'none';

  // Separate layer, unaffected by the old boundary filters.
  const southernLayer = L.geoJSON(null, {
    pane: 'southernBoundaryPane',
    interactive: false,
    style: {
      color: '#0047AB',
      weight: 3,
      opacity: 1,
      fill: false
    }
  });

  function updateVisibility() {
    if (checkbox.checked) {
      southernLayer.addTo(map);
    } else {
      map.removeLayer(southernLayer);
    }
  }

  async function loadSouthernBoundaries() {
    try {
      const response = await fetch(
        './data/municipalities.geojson',
        {cache: 'no-store'}
      );

      if (!response.ok) {
        throw new Error(
          'GeoJSON HTTP ' + response.status
        );
      }

      const data = await response.json();

      if (!Array.isArray(data.features)) {
        throw new Error('Invalid municipality GeoJSON');
      }

      const selected = data.features.filter(feature => {
        const name = String(
          feature.properties?.name || ''
        ).trim();

        return SOUTHERN_TOWNS.has(name);
      });

      const found = new Set(
        selected.map(f => f.properties.name)
      );

      const missing = [...SOUTHERN_TOWNS].filter(
        name => !found.has(name)
      );

      if (selected.length !== 12 || missing.length) {
        throw new Error(
          'Expected 12 municipalities, found ' +
          selected.length +
          '. Missing: ' + missing.join(', ')
        );
      }

      southernLayer.clearLayers();
      southernLayer.addData({
        type: 'FeatureCollection',
        features: selected
      });

      checkbox.checked = true;
      updateVisibility();

      // Always bring outlines above ordinary polygon layers.
      southernLayer.bringToFront();

      console.log(
        '[Southern boundaries] SUCCESS:',
        selected.length,
        'municipality polygons loaded'
      );

      console.log(
        '[Southern boundaries] Bounds:',
        southernLayer.getBounds().toBBoxString()
      );

    } catch (error) {
      console.error(
        '[Southern boundaries] FAILED:',
        error
      );
    }
  }

  checkbox.addEventListener(
    'change',
    updateVisibility
  );

  loadSouthernBoundaries();
})();
