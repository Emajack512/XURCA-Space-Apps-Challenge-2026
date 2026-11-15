<script>
  import { translate } from '$lib/services/i18n.js';
  import { onMount } from 'svelte';
  import { Map } from 'maplibre-gl';
  import { geoDistance } from 'd3-geo';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { workspace, editVisual, selectGeometry } from '$lib/stores/workspace.js';
  import { addPolygonVertex, closedRegion, draftGeometry, nearPolygonStart, openPolygonNotice, rectangle, coordinateLabel } from '$lib/services/geography.js';

  let { tool, vertices = $bindable([]), cursor = $bindable(null), notice = $bindable(''), fallback } = $props();
  let container;
  let map = $state.raw(null);
  let ready = $state(false);
  let unavailable = $state(false);
  let theme = $derived($workspace.visual.theme);
  let camera = $derived($workspace.visual.map.camera);
  let selectionVisible = $derived($workspace.visual.map.layers.selection);
  let features = $derived($workspace.data.geography.selection.features);
  let draft = $derived(draftGeometry(vertices));
  const zoomOffset = 1.3;
  const layerSource = 'earth-selection';

  onMount(() => {
    let instance;
    try {
      instance = new Map({
        container, style: 'https://tiles.openfreemap.org/styles/' + (theme === 'light' ? 'positron' : 'dark'),
        center: [camera.longitude, camera.latitude], zoom: zoomOffset + Math.log2(camera.zoom),
        maxZoom: 18, maxPitch: 0, dragRotate: false, rollEnabled: false
      });
    } catch {
      unavailable = true;
      return;
    }
    map = instance;
    const timeout = setTimeout(() => { if (!ready) unavailable = true; }, 15000);
    instance.on('error', () => { if (!instance.isStyleLoaded()) unavailable = true; });
    instance.on('style.load', () => {
      clearTimeout(timeout);
      unavailable = false;
      instance.setProjection({ type: 'globe' });
      for (const id of ['place_state', 'place_city', 'place_city_large', 'place_town', 'place_village']) {
        if (!instance.getLayer(id)) continue;
        if (theme === 'light') continue;
        instance.setPaintProperty(id, 'text-color', id === 'place_state' ? '#a9bdcf' : '#e0e8ef');
        instance.setPaintProperty(id, 'text-halo-color', '#121820');
        instance.setLayoutProperty(id, 'text-field', ['coalesce', ['get', 'name:es'], ['get', 'name'], ['get', 'name_en']]);
      }
      instance.addSource(layerSource, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      instance.addLayer({ id: 'earth-selection-fill', type: 'fill', source: layerSource,
        filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': '#57dfc1', 'fill-opacity': 0.23 } });
      instance.addLayer({ id: 'earth-selection-line', type: 'line', source: layerSource,
        paint: { 'line-color': ['case', ['has', 'draft'], '#f5bd77', '#78f8dc'], 'line-width': 2 } });
      instance.addLayer({ id: 'earth-selection-point', type: 'circle', source: layerSource,
        filter: ['==', '$type', 'Point'], paint: { 'circle-color': '#f8c277', 'circle-radius': ['case', ['has', 'start'], 7, 5], 'circle-stroke-color': ['case', ['has', 'start'], '#fff', '#17263b'], 'circle-stroke-width': 1.5 } });
      ready = true;
    });
    instance.on('moveend', event => {
      if (event.fromWorkspace) return;
      const center = instance.getCenter().wrap();
      editVisual(visual => visual.map.camera = {
        longitude: center.lng, latitude: center.lat, zoom: 2 ** (instance.getZoom() - zoomOffset)
      });
    });
    instance.on('mousemove', event => cursor = coordinates(event));
    instance.on('mouseout', () => cursor = null);
    instance.on('click', event => {
      const point = coordinates(event);
      if (!point) return;
      if (tool === 'point') selectGeometry('Point', point);
      if (tool === 'polygon') {
        if (vertices.length >= 3 && geoDistance(vertices[0], point) < Math.PI / 2) {
          const first = instance.project(vertices[0]);
          if (nearPolygonStart([first.x, first.y], event.point.x, event.point.y)) {
            const ring = closedRegion(vertices);
            if (ring) {
              selectGeometry('Polygon', ring, 'Polígono');
              vertices = [];
              if (notice === openPolygonNotice) notice = '';
            }
            return;
          }
        }
        vertices = addPolygonVertex(vertices, point);
      }
      if (tool === 'rectangle') {
        if (!vertices.length) { vertices = [point]; return; }
        const ring = rectangle(vertices[0], point);
        if (ring) selectGeometry('Polygon', ring, 'Rectángulo');
        else notice = 'Elegí dos esquinas que delimiten un rectángulo.';
        vertices = [];
      }
    });
    return () => { clearTimeout(timeout); instance.remove(); };
  });

  let appliedTheme;
  $effect(() => {
    if (!map) return;
    if (appliedTheme && appliedTheme !== theme) {
      ready = false;
      map.setStyle('https://tiles.openfreemap.org/styles/' + (theme === 'light' ? 'positron' : 'dark'), { diff: false });
    }
    appliedTheme = theme;
  });

  function coordinates(event) {
    const point = event.lngLat.wrap();
    if (!Number.isFinite(point.lng) || Math.abs(point.lat) > 90) return null;
    const projected = map.project(point);
    if (Math.hypot(projected.x - event.point.x, projected.y - event.point.y) > 2) return null;
    return [point.lng, point.lat].map(value => Number(value.toFixed(6)));
  }

  $effect(() => {
    if (!map || !ready) return;
    const center = map.getCenter().wrap();
    const zoom = zoomOffset + Math.log2(camera.zoom);
    if (Math.abs(center.lng - camera.longitude) > 1e-6 || Math.abs(center.lat - camera.latitude) > 1e-6 || Math.abs(map.getZoom() - zoom) > 1e-6) {
      map.jumpTo({ center: [camera.longitude, camera.latitude], zoom }, { fromWorkspace: true });
    }
  });

  $effect(() => {
    if (!ready || !map.getSource(layerSource)) return;
    const shown = selectionVisible ? [...features] : [];
    if (draft) shown.push({
      type: 'Feature', properties: { draft: true }, geometry: draft
    });
    vertices.forEach((point, index) => shown.push({
      type: 'Feature', properties: tool === 'polygon' && index === 0 ? { start: true } : {},
      geometry: { type: 'Point', coordinates: point }
    }));
    map.getSource(layerSource).setData(JSON.parse(JSON.stringify({ type: 'FeatureCollection', features: shown })));
    map.getCanvas().style.cursor = tool === 'pan' ? '' : 'crosshair';
  });

</script>

<svelte:window onkeydown={event => {
  if (event.key === 'Escape' && tool !== 'polygon') vertices = [];
}}/>

<section class="map-panel">
  <header class="panel-heading">
    <span>{$translate("Exploración geográfica")}</span>
    <div class="input-row"><button class="outlined" aria-pressed={selectionVisible} onclick={() => editVisual(visual => visual.map.layers.selection = !selectionVisible)}>{$translate("Selecciones")}</button><button class="outlined" onclick={fallback}>{$translate("Mapa sin conexión")}</button></div>
  </header>
  <div class="map-view">
    <div class="world-map" bind:this={container}></div>
    <div class="map-top"><span class="map-pill">WGS 84</span><span class="map-pill">{coordinateLabel(cursor)}</span></div>
    {#if unavailable}
      <div class="map-message"><p>{$translate("No se pudo cargar la cartografía mundial.")}</p><button class="outlined" onclick={fallback}>{$translate("Abrir mapa sin conexión")}</button></div>
    {:else if !ready}
      <div class="map-message" role="status">{$translate("Cargando cartografía mundial…")}</div>
    {/if}
  </div>
</section>
