<script>
  import { shouldRetryAssistant, waitForAssistantRetry } from '$lib/services/assistantRetry.js';
  import { chartCadences, chartResolutions } from '$lib/services/charts.js';
  import { saveChartImage } from '$lib/services/chartExport.js';
  import { catalog } from '$lib/services/sources.js';
  import { translate } from '$lib/services/i18n.js';
  import { onMount, tick } from 'svelte';
  import { Earth, Bot, ChevronDown, CircleHelp, Crosshair, FlaskConical, Hand, MapPin, Play, Hexagon, Settings, Settings2, Square, Trash2, X, Save, FolderOpen } from '@lucide/svelte';
  import WorldMap from '$lib/components/WorldMap.svelte';
  import Globe from '$lib/components/Globe.svelte';
  import SettingsPanel from '$lib/components/Settings.svelte';
  import Results from '$lib/components/Results.svelte';
  import AnalysisPanel from '$lib/components/AnalysisPanel.svelte';
  import Assistant from '$lib/components/Assistant.svelte';
  import ResizeHandle from '$lib/components/ResizeHandle.svelte';
  import Tutorial from '$lib/components/Tutorial.svelte';
  import { EXAMPLE, LEVELS } from '$lib/services/tutorialSteps.js';
  import { chatDraft, analysisForm, loadTutorial, saveTutorial } from '$lib/stores/tour.js';
  import { analysisDraft } from '$lib/stores/analysis.js';
  import { sourceConfig } from '$lib/services/sources.js';
  import { workspace, defaults, editData, editVisual, selectGeometry, removeSelections } from '$lib/stores/workspace.js';
  import { loadWorkspace, saveWorkspace, downloadJson } from '$lib/services/configuration.js';
  import { acquireData, prepareInvestigation } from '$lib/services/acquisition.js';
  import { coordinateLabel, closedRegion, openPolygonNotice, regionProblem, validCoordinates } from '$lib/services/geography.js';
  import { attend, flag } from '$lib/services/attention.js';
  import '$lib/styles/dashboard.css';

  let detailedMap = $state(true);
  $effect(() => { document.documentElement.lang = $workspace.visual.language === 'en' ? 'en' : 'es'; });
  let tool = $state('pan');
  let vertices = $state([]);
  let cursor = $state(null);
  let notice = $state('');
  let menu = $state('');
  let dialog;
  let modal = $state('');
  let latitude = $state('');
  let longitude = $state('');
  let polygonInput = $state('');
  let selectionName = $state('');
  let editingFeature = $state(null);
  let coordinateMode = $state('point');
  let modalError = $state('');
  let running = $state(false);
  let settingsOpen = $state(false);
  let acquisitionError = $state(null);
  let result = $state(null);
  let chartId = $state(null);
  let analysisView = $state(false);
  let analysisOpened = $state(false);
  let selectionMenu = $state(false);
  let runningGeometries = [];
  // Guided tour: null (closed), 'welcome' or 'tour'. The level persists in localStorage.
  let tutorial = $state(null);
  let tutorialLevel = $state('novice');
  let tutorialKey = $state(0);
  let tourPrefill = $state(false);
  let acquisitionGeneration = 0;
  let regionReset = $state(0);
  let savedConfig = $state('');
  let storageBusy = $state(true);
  let panels = $derived($workspace.visual.workspace);
  let mapVisible = $derived(panels.map !== false);
  let assistantVisible = $derived(panels.assistantVisible !== false);
  let currentSeries = $derived(result?.key === configKey ? result.series : []);
  const mapTab = 'regional-result-map';
  let mapSeries = $derived(currentSeries.flatMap(item => {
    if (item.map) return [item];
    const location = item.coordinates;
    if (!Array.isArray(location) || location.length !== 2 || !location.every(Number.isFinite)) return [];
    const events = item.points.filter(point => Number.isFinite(point.value))
      .map(point => ({ date: point.month, value: point.value, coordinates: location, entityId: item.id }));
    if (!events.length) return [];
    const [lon, lat] = location;
    const west = Math.max(-180, lon - 1), east = Math.min(180, lon + 1);
    const south = Math.max(-89.9, Math.min(89.8, lat - 1)), north = Math.min(89.9, Math.max(-89.8, lat + 1));
    return [{ ...item, map: { kind: 'entities', field: 'value', pointView: true, events,
      cadence: item.cadence === 'monthly' || events.length > 93 ? 'monthly' : 'daily',
      start: events[0].date.slice(0, 10), end: events.at(-1).date.slice(0, 10),
      area: { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] }
    } }];
  }));
  let hasRegionalMaps = $derived(mapSeries.some(item => !item.map.pointView));
  let mapSeriesId = $state(null);
  let selectedMap = $derived(mapSeries.find(item => item.id === mapSeriesId) ?? mapSeries[0]);
  let activeMap = $derived(chartId === mapTab && !!selectedMap);
  let activeChart = $derived(currentSeries.find(item => item.id === chartId));
  let analysisVisible = $derived(analysisView && !activeChart && !activeMap);
  let exportableSeries = $derived(currentSeries.filter(item => item.points.some(point => point.value !== null)));
  let exportId = $state('');
  let exporting = $state(false);
  let dirty = $derived(JSON.stringify($workspace) !== savedConfig);
  let configKey = $derived(JSON.stringify($workspace.data));
  let savedAccent = $derived($workspace.visual.appearance.accent);
  let customAccent = $derived(savedAccent?.toLowerCase() === '#57dfc1' ? null : savedAccent);
  let resultStatus = $derived(running ? 'Procesando…' : result?.key === configKey ? 'Consulta completada' : result ? 'Configuración modificada' : 'Sin resultados');
  let selected = $derived($workspace.data.geography.selection.features.at(-1));
  const tools = [
    ['pan','Desplazar globo',Hand], ['point','Seleccionar punto',MapPin],
    ['polygon','Selección poligonal',Hexagon]
  ];

  onMount(async () => {
    try {
      const saved = await loadWorkspace();
      if (saved) workspace.set({ ...defaults(), ...Object.fromEntries(Object.entries(saved).filter(([, value]) => value != null)) });
      savedConfig = JSON.stringify($workspace);
      const stored = loadTutorial();
      if (stored?.level) tutorialLevel = stored.level;
      if (!stored) tutorial = 'welcome';
    } catch (error) {
      notify($translate('No se pudo recuperar la configuración.') + ' ' + $translate(String(error.message ?? error)));
    } finally { storageBusy = false; }
  });

  function notify(text) { notice = text; }
  function togglePanel(id, value = panels[id] === false) {
    chartId = null;
    analysisView = false;
    editVisual(visual => visual.workspace[id] = value);
    if (id === 'map' && !value) cursor = null;
  }

  async function openChartExport() {
    if (!exportableSeries.length) {
      notify('Consultá datos antes de exportar una gráfica.');
      return;
    }
    exportId = exportableSeries.find(item => item.id === chartId)?.id ?? exportableSeries[0].id;
    await showDialog('chart-export');
  }

  async function exportChart(event) {
    event.preventDefault();
    if (exporting) return;
    chartId = exportId;
    await tick();
    const card = [...document.querySelectorAll('[data-series-id]')].find(item => item.dataset.seriesId === exportId);
    const canvas = card?.querySelector('canvas');
    if (!canvas) { modalError = 'La gráfica ya no está disponible.'; return; }
    modalError = '';
    exporting = true;
    try {
      if (await saveChartImage(canvas, exportId.replace(/[^a-z0-9_-]/gi, '-') + '.png', $workspace.visual.theme === 'light')) {
        dialog.close();
        notify('Gráfica guardada.');
      }
    } catch {
      modalError = 'No se pudo guardar la gráfica.';
    } finally {
      exporting = false;
    }
  }
  function chooseTool(id) { tool = id; vertices = []; if (notice === openPolygonNotice) notice = ''; }
  function removeMapSelections(shouldRemove) {
    vertices = [];
    regionReset++;
    if (notice === openPolygonNotice) notice = '';
    const removed = removeSelections(shouldRemove);
    // A query that reads a selection the user just removed no longer answers anything useful.
    if (running && removed.some(id => runningGeometries.includes(id))) {
      cancelRun();
      notify('Se canceló la consulta porque quitaste una selección que estaba usando.');
    }
  }
  function clearSelection() { selectionMenu = false; removeMapSelections(() => true); }
  function removeFeature(id) { removeMapSelections(feature => feature.id === id); }
  let selectionFeatures = $derived($workspace.data.geography.selection.features);
  let selectedPoints = $derived(selectionFeatures.filter(feature => feature.geometry.type === 'Point'));
  function featureLabel(feature, index) {
    const name = feature.properties?.name?.trim();
    const point = feature.geometry.type === 'Point';
    const kind = $translate(point ? 'Punto' : 'Área');
    return name ? kind + ' · ' + name
      : kind + ' ' + (index + 1) + (point ? ' · ' + coordinateLabel(feature.geometry.coordinates) : '');
  }
  function joinPoints() {
    const points = selectedPoints.map(feature => feature.geometry.coordinates);
    if (points.length < 3) { notify('Marcá al menos tres puntos para unirlos en un polígono.'); return; }
    // First the order in which the points were marked; if that outline crosses itself, sort them around their centre.
    const center = points.reduce((sum, point) => [sum[0] + point[0] / points.length, sum[1] + point[1] / points.length], [0, 0]);
    const angle = point => Math.atan2(point[1] - center[1], point[0] - center[0]);
    const around = [...points].sort((a, b) => angle(a) - angle(b));
    const ring = closedRegion(points) ?? closedRegion(around);
    if (!ring) { notify(regionProblem(around) || 'Esos puntos no delimitan un área válida.'); return; }
    const pointIds = selectedPoints.map(feature => feature.id);
    removeMapSelections(feature => pointIds.includes(feature.id));
    selectGeometry('Polygon', ring, 'Polígono de puntos');
    selectionMenu = false;
    notify('Los puntos se unieron en un polígono. Si tenías variables asignadas a esos puntos, asignalas a la nueva área.');
  }
  function cancelRun() {
    if (!running) return;
    acquisitionGeneration++;
    running = false;
    runningGeometries = [];
    notify('Consulta cancelada. Podés cambiar la configuración y volver a procesar.');
  }

  function clearChatResults() {
    acquisitionGeneration++;
    analysisView = false;
    running = false;
    result = null;
    chartId = null;
    mapSeriesId = null;
    acquisitionError = null;
    notice = '';
    if (modal === 'chart-export' && dialog?.open) dialog.close();
  }
  function buildInvestigation() {
    try {
      return prepareInvestigation($workspace.data);
    } catch (error) {
      notify($translate(error.message));
      if (error.field) showMissingSetting(error.field);
      return null;
    }
  }

  // Opens the settings where the missing value goes and makes that place glow red with a short beep.
  async function showMissingSetting(field) {
    chartId = null;
    analysisView = false;
    settingsOpen = true;
    if (field === 'geometry' && !mapVisible) editVisual(visual => visual.workspace.map = true);
    await tick();
    flag(field, 'settings-button', ...(field === 'geometry' ? ['map'] : []));
  }

  function openAnalysis() { chartId = null; analysisView = true; analysisOpened = true; }
  function openSettings() { chartId = null; analysisView = false; settingsOpen = true; }

  async function run({ showChart = true, retry = false } = {}) {
    if (running || storageBusy) return;
    const investigation = buildInvestigation();
    if (!investigation) return;
    analysisView = false;
    const startedWith = configKey;
    const generation = ++acquisitionGeneration;
    runningGeometries = investigation.sources.map(source => source.upstream?.geometryId).filter(Boolean);
    running = true;
    acquisitionError = null;
    result = null;
    chartId = null;
    notice = '';
    try {
      let acquired;
      try {
        acquired = await acquireData(investigation);
      } catch (error) {
        if (generation !== acquisitionGeneration) return;
        if (!retry || !shouldRetryAssistant(error) || startedWith !== configKey) throw error;
        await waitForAssistantRetry();
        if (generation !== acquisitionGeneration || startedWith !== configKey) return;
        acquired = await acquireData(investigation);
      }
      if (generation !== acquisitionGeneration) return;
      const sources = new Map(investigation.sources.map(source => [source.id, source]));
      const features = new Map(investigation.geography.selection.features.map(feature => [feature.id, feature]));
      const series = acquired.map(item => {
        const source = sources.get(item.id);
        const feature = features.get(source?.upstream.geometryId);
        const name = feature?.properties?.name?.trim();
        const region = ['Polygon', 'MultiPolygon'].includes(feature?.geometry.type);
        const named = name && !['Polígono', 'Polígono manual', 'Rectángulo'].includes(name);
        const placeLabel = region
          ? named ? name + ' ' + $translate('y alrededores') : $translate('Área seleccionada')
          : name;
        return { ...item, placeLabel };
      });
      result = { key: startedWith, series };
      if (showChart && startedWith === configKey) chartId = series[0]?.id ?? null;
    } catch (error) {
      if (generation !== acquisitionGeneration) return;
      const message = String(error.message ?? error);
      acquisitionError = { key: startedWith, message };
      notify(message);
    } finally {
      if (generation === acquisitionGeneration) { running = false; runningGeometries = []; }
    }
  }
  async function save() {
    if (storageBusy) return;
    storageBusy = true;
    const snapshot = $workspace;
    try {
      await saveWorkspace(snapshot);
      savedConfig = JSON.stringify(snapshot);
      notify('Configuración guardada');
    } catch (error) {
      notify($translate('No se pudo guardar.') + ' ' + $translate(String(error.message ?? error)));
    } finally { storageBusy = false; }
  }
  async function restore() {
    if (storageBusy) return;
    storageBusy = true;
    try {
      const saved = await loadWorkspace();
      if (!saved) { notify('Todavía no hay una configuración guardada.'); return; }
      workspace.set({ ...defaults(), ...Object.fromEntries(Object.entries(saved).filter(([, value]) => value != null)) });
      savedConfig = JSON.stringify($workspace);
      notify('Configuración recuperada');
    } catch (error) {
      notify($translate('No se pudo recuperar.') + ' ' + $translate(String(error.message ?? error)));
    } finally { storageBusy = false; }
  }
  async function showDialog(id) {
    menu = '';
    modal = id;
    modalError = '';
    await tick();
    dialog.showModal();
  }
  function openCoordinates(feature = null) {
    editingFeature = feature;
    selectionName = feature?.properties?.name ?? '';
    coordinateMode = feature?.geometry.type === 'Polygon' ? 'polygon' : 'point';
    longitude = feature?.geometry.type === 'Point' ? String(feature.geometry.coordinates[0]) : '';
    latitude = feature?.geometry.type === 'Point' ? String(feature.geometry.coordinates[1]) : '';
    polygonInput = feature?.geometry.type === 'Polygon'
      ? feature.geometry.coordinates[0].slice(0, -1).map(point => point.join(', ')).join('\n')
      : '';
    tourPrefill = !feature && tutorial === 'tour';
    if (tourPrefill) {
      selectionName = EXAMPLE.place;
      longitude = String(EXAMPLE.longitude);
      latitude = String(EXAMPLE.latitude);
    }
    return showDialog('coordinates');
  }

  function saveSelection(type, coordinates, name) {
    if (!editingFeature) {
      selectGeometry(type, coordinates, name);
      return;
    }
    editData(data => {
      const feature = data.geography.selection.features.find(item => item.id === editingFeature.id);
      if (feature) {
        feature.geometry = { type, coordinates };
        feature.properties.name = name;
      }
    });
  }

  function submitCoordinates(event) {
    event.preventDefault();
    let center;
    if (coordinateMode === 'point') {
      center = [Number(longitude), Number(latitude)];
      if (longitude === '' || latitude === '' || !validCoordinates(...center)) {
        modalError = 'Ingresá longitud entre −180 y 180 y latitud entre −90 y 90.';
        return;
      }
      saveSelection('Point', center, selectionName.trim());
    } else {
      const points = polygonInput.trim().split(/\r?\n/).map(line => line.trim().split(/[ ,]+/).map(Number));
      if (points.some(point => point.length !== 2 || !validCoordinates(...point))) {
        modalError = 'Ingresá un par longitud, latitud por línea.';
        return;
      }
      const ring = closedRegion(points);
      if (!ring) { modalError = regionProblem(points) || 'Ingresá al menos tres vértices que delimiten un área.'; return; }
      saveSelection('Polygon', ring, selectionName.trim());
      center = points[0];
    }
    editVisual(visual => {
      visual.map.camera.longitude = center[0];
      visual.map.camera.latitude = center[1];
      visual.map.layers.selection = true;
    });
    dialog.close();
    notify('Selección geográfica actualizada');
  }
  // ── Guided tour ──
  let tourState = $derived({ data: $workspace.data, settingsOpen, running, analysisVisible,
    hasResults: currentSeries.length > 0, form: $analysisForm });

  function examplePointId() {
    const features = $workspace.data.geography.selection.features;
    return features.find(feature => feature.geometry.type === 'Point' && feature.properties?.name === EXAMPLE.place)?.id
      ?? features.find(feature => feature.geometry.type === 'Point')?.id;
  }
  const tourApi = {
    openSettings: () => { chartId = null; analysisView = false; settingsOpen = true; },
    setScope: scope => { tourApi.openSettings(); editData(data => data.geography.scope = scope); },
    addExamplePoint: () => {
      tourApi.setScope('point');
      if (!examplePointId()) selectGeometry('Point', [EXAMPLE.longitude, EXAMPLE.latitude], EXAMPLE.place);
      editVisual(visual => Object.assign(visual.map.camera, { longitude: EXAMPLE.longitude, latitude: EXAMPLE.latitude }));
    },
    setPeriod: (start, end) => editData(data => { Object.assign(data.time, { start, end, resolution: 'Mensual' }); delete data.time.years; }),
    // Every "do it for me" leaves the whole example ready up to that step, so levels that skip steps still work.
    addExampleSource: () => {
      tourApi.addExamplePoint();
      tourApi.setPeriod(EXAMPLE.start, EXAMPLE.end);
      const geometryId = examplePointId();
      editData(data => {
        if (data.sources.some(source => source.id.split('::')[0] === EXAMPLE.sourceId)) return;
        const source = sourceConfig(EXAMPLE.sourceId);
        source.upstream.geometryId = geometryId;
        data.sources.push(source);
      });
    },
    process: async () => { tourApi.addExampleSource(); await tick(); run(); },
    writeChat: () => { if (!assistantVisible) togglePanel('assistantVisible', true); chatDraft.set(EXAMPLE.prompt); },
    openAnalysis: () => openAnalysis(),
    chooseAnalysis: () => { tourApi.addExampleSource(); openAnalysis(); analysisDraft.set({ struct: EXAMPLE.struct, targets: [EXAMPLE.sourceId] }); }
  };

  function setTutorialLevel(level) {
    tutorialLevel = level;
    saveTutorial({ ...(loadTutorial() ?? {}), level });
  }
  function closeTutorial(finished) {
    tutorial = null;
    tourPrefill = false;
    saveTutorial({ ...(loadTutorial() ?? {}), level: tutorialLevel, finished: finished || !!loadTutorial()?.finished });
  }
  function restartTutorial() {
    if (dialog?.open) dialog.close();
    tutorialKey++;
    tutorial = 'welcome';
  }

  async function menuAction(action) { menu = ''; await action(); }
  const menus = [
    ['Proyecto', [['Guardar configuración',save],['Recuperar configuración',() => dirty ? showDialog('restore') : restore()]]],
    ['Análisis', [['Procesar',run],['Mostrar resultados',() => chartId = currentSeries[0]?.id ?? null],['Análisis estadístico…',openAnalysis]]],
    ['Visualización', [['Resolución gráfica',() => showDialog('chart-resolution')]]],
    ['Exportar', [['Guardar gráfica…',openChartExport],['Descargar cfg_data.json',() => downloadJson('cfg_data.json',$workspace.data)],['Descargar cfg_visual.json',() => downloadJson('cfg_visual.json',$workspace.visual)]]]
  ];
</script>

<svelte:head><title>TrendScope</title><meta name="description" content={$translate("Espacio de trabajo para explorar tendencias del sistema terrestre.")}/></svelte:head>
<svelte:window onpointerdown={event => {
  // Any click outside an open menu closes it.
  if ((menu || selectionMenu) && !event.target?.closest?.('.menu-anchor')) { menu = ''; selectionMenu = false; }
}} onkeydown={event => {
  if (tool === 'polygon' && vertices.length && !dialog?.open &&
      ['Enter', 'Escape'].includes(event.key) && !event.target?.closest?.('input, textarea, select, button, [contenteditable]')) {
    event.preventDefault();
    notify(openPolygonNotice);
  }
  if (event.key === 'Escape') { menu = ''; selectionMenu = false; }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(); }
}}/>

<div class="app-shell" class:light={$workspace.visual.theme === 'light'} style:--custom-accent={customAccent} style:--base-size={$workspace.visual.appearance.fontSize + 'px'}>
  <header class="topbar">
    <div class="identity"><strong>TrendScope</strong></div>
    <nav aria-label={$translate("Menú principal")}>
      {#each menus as [name,actions]}
        <div class="menu-anchor">
          <button data-tour={'menu-' + name} class:active={menu === name} aria-expanded={menu === name} onclick={() => menu = menu === name ? '' : name}>{$translate(name)}<ChevronDown size={12}/></button>
          {#if menu === name}<div class="dropdown">{#each actions as [label,action]}<button disabled={label === 'Mostrar resultados' && !currentSeries.length} onclick={() => menuAction(action)}>{$translate(label)}</button>{/each}</div>{/if}
        </div>
      {/each}
    </nav>
    <button class="icon-button top-icon" aria-label={$translate("Preferencias")} title={$translate("Preferencias")} onclick={() => showDialog('preferences')}><Settings2 size={17}/></button>
  </header>

  <div class="toolbar" aria-label={$translate("Herramientas")}>
    <div class="geo-tools">
      {#each tools as [id,label,Icon]}
        <button class="tool-button" class:active={id === tool} aria-pressed={id === tool} title={$translate(label)} aria-label={$translate(label)} onclick={() => chooseTool(id)}><Icon size={17}/></button>
      {/each}
      <div class="menu-anchor">
        <button class="tool-button" class:active={selectionMenu} aria-expanded={selectionMenu} title={$translate("Selecciones del mapa")} aria-label={$translate("Selecciones del mapa")} onclick={() => selectionMenu = !selectionMenu}><Trash2 size={16}/></button>
        {#if selectionMenu}
          <div class="dropdown selection-menu">
            {#each selectionFeatures as feature, index (feature.id)}
              <div class="selection-row">
                <span title={featureLabel(feature, index)}>{featureLabel(feature, index)}</span>
                <button class="icon-button" title={$translate('Eliminar selección')} aria-label={$translate('Eliminar selección')} onclick={() => removeFeature(feature.id)}><X size={14}/></button>
              </div>
            {:else}
              <p class="quiet">{$translate('No hay selecciones en el mapa.')}</p>
            {/each}
            {#if selectedPoints.length >= 3}
              <button onclick={joinPoints}><Hexagon size={14}/> {$translate('Unir los puntos en un polígono')}</button>
            {/if}
            {#if selectionFeatures.length}
              <button onclick={clearSelection}><Trash2 size={14}/> {$translate('Borrar todas')}</button>
            {/if}
          </div>
        {/if}
      </div>
    </div>
    <div class="panel-buttons">
      <button class="tool-button" class:active={mapVisible} aria-pressed={mapVisible}
        title={$translate('Alternar mapa')} aria-label={$translate('Alternar mapa')}
        onclick={() => togglePanel('map', !mapVisible)}><Earth size={17}/></button>
      <button class="tool-button" data-tour="settings-button" use:attend={'settings-button'} class:active={settingsOpen} aria-pressed={settingsOpen} title={$translate("Configuración")} aria-label={$translate("Alternar panel de configuración")} onclick={() => { chartId = null; analysisView = false; settingsOpen = !settingsOpen; }}><Settings size={17}/></button>
      <button class="tool-button" class:active={assistantVisible} aria-pressed={assistantVisible} title={$translate("Asistente de IA")} aria-label={$translate("Alternar asistente")} onclick={() => togglePanel('assistantVisible', !assistantVisible)}><Bot size={17}/></button>
      <button class="tool-button" data-tour="analysis-button" class:active={analysisVisible} aria-pressed={analysisVisible}
        title={$translate('Análisis estadístico')} aria-label={$translate('Análisis estadístico')}
        onclick={openAnalysis}><FlaskConical size={17}/></button>
    </div>
    <div class="view-tabs" data-tour="view-tabs" role="group" aria-label={$translate('Vistas de la consulta')}>
      <button class:active={!activeChart && !activeMap && !analysisVisible} aria-pressed={!activeChart && !activeMap && !analysisVisible} onclick={() => { chartId = null; analysisView = false; }}>{$translate('Espacio de trabajo')}</button>
      {#if mapSeries.length}
        <button class:active={activeMap} aria-pressed={activeMap} onclick={() => chartId = mapTab}>{$translate(hasRegionalMaps ? 'Mapa coroplético' : 'Mapa de datos')}</button>
      {/if}
      {#each currentSeries as item (item.id)}
        {@const label = $translate(catalog.find(source => source.id === item.id.split('::')[0])?.label ?? item.label ?? item.variable)}
        <button class:active={activeChart?.id === item.id} aria-pressed={activeChart?.id === item.id} title={item.placeLabel ? item.placeLabel + ' · ' + label : label} onclick={() => chartId = item.id}><span>{item.placeLabel ?? label}{item.placeLabel && currentSeries.some(other => other.id !== item.id && other.placeLabel === item.placeLabel) ? ' · ' + label : ''}</span></button>
      {/each}
    </div>
    <div class="run-actions" data-tour="process">
      {#if running}
        <button class="run" onclick={cancelRun} title={$translate('Cancelar la consulta en curso')}><Square size={13} fill="currentColor"/> {$translate('Cancelar')}</button>
      {:else}
        <button class="primary run" onclick={() => run()}><Play size={15} fill="currentColor"/> {$translate('Procesar')}</button>
      {/if}
    </div>
  </div>

  <main class="view-content">
  <div class="desktop workspace-view" hidden={!!activeChart || activeMap || analysisVisible}
    style:--settings-width={panels.settingsWidth + 'px'} style:--assistant-width={(panels.assistantWidth ?? 330) + 'px'}>
    {#if settingsOpen}
      <SettingsPanel {openCoordinates}/>
      {#if mapVisible || assistantVisible}<ResizeHandle label={$translate("Ancho del panel de configuración")} value={panels.settingsWidth} min={220} max={450} resize={value => editVisual(visual => visual.workspace.settingsWidth = value)}/>{/if}
    {/if}
    {#if mapVisible && detailedMap}
      <WorldMap {tool} bind:vertices bind:cursor bind:notice fallback={() => detailedMap = false}/>
    {:else if mapVisible}
      <Globe {tool} bind:vertices bind:cursor bind:notice showDetail={() => detailedMap = true}/>
    {/if}
    {#if assistantVisible && mapVisible}<ResizeHandle label={$translate('Ancho del asistente')} value={panels.assistantWidth ?? 388} min={265} max={600} direction={-1} resize={value => editVisual(visual => visual.workspace.assistantWidth = value)}/>{/if}
    <aside class="assistant-panel" data-tour="assistant" hidden={!assistantVisible}>
      <header class="panel-heading"><span><Bot size={16}/> {$translate('Asistente de IA')}</span>
        <!-- Space Apps rules: AI-generated content must be identified as such. -->
        <small class="ai-label" title="El texto del asistente lo genera un modelo de IA (Gemini). Los cálculos los hace el motor estadístico de la app.">{$translate('Respuestas generadas con IA')}</small></header>
      <Assistant series={currentSeries} {running} {storageBusy} {buildInvestigation} {regionReset} onreset={clearChatResults} oncancel={cancelRun}
        acquisitionError={acquisitionError?.key === configKey ? acquisitionError.message : ''}
        onprocess={() => run({ showChart: false, retry: true })} onresults={() => chartId = currentSeries[0]?.id ?? null}
        onanalysis={openAnalysis}/>
    </aside>
  </div>
  {#if activeMap}
    <div class="map-results">
      {#if mapSeries.length > 1}
        <label>{$translate('Variable')}
          <select value={selectedMap.id} onchange={event => mapSeriesId = event.currentTarget.value}>
            {#each mapSeries as item (item.id)}
              <option value={item.id}>{item.placeLabel ? item.placeLabel + ' · ' : ''}{$translate(catalog.find(source => source.id === item.id.split('::')[0])?.label ?? item.label ?? item.variable)}</option>
            {/each}
          </select>
        </label>
      {/if}
      <Results series={[selectedMap]} mapsOnly/>
    </div>
  {:else if activeChart}
    <div class="chart-workspace"><Results series={[activeChart]} all={currentSeries}/></div>
  {/if}
  {#if analysisOpened}
    <!-- Kept mounted so the form survives switching to the map and back. -->
    <div class="chart-workspace" hidden={!analysisVisible}><AnalysisPanel {buildInvestigation} {notify} opensettings={openSettings}/></div>
  {/if}
  </main>

  <footer class="statusbar">
    <span class="status-coordinates"><Crosshair size={12}/> {cursor ? coordinateLabel(cursor) : selected?.geometry.type === 'Point' ? coordinateLabel(selected.geometry.coordinates) : $translate(selected?.properties.name || 'Sin selección')}</span>
    <span>{$workspace.data.sources.length} {$translate('variables')}</span>
    <button onclick={save} disabled={storageBusy} title={$translate("Guardar configuración (Ctrl+S)")}><Save size={13}/> {$translate(storageBusy ? 'Procesando' : dirty ? 'Sin guardar' : 'Guardado')}</button>
    <span class="status-results">{$translate(resultStatus)}</span>
  </footer>

  {#if notice}<div class="toast" role="status"><CircleHelp size={17}/><span>{$translate(notice)}</span><button aria-label={$translate("Cerrar aviso")} class="icon-button" onclick={() => notice = ''}><X size={15}/></button></div>{/if}

  {#if tutorial}
    {#key tutorialKey}
      <Tutorial phase={tutorial} level={tutorialLevel} appState={tourState} api={tourApi}
        onlevel={setTutorialLevel} onstart={() => tutorial = 'tour'} onclose={closeTutorial}/>
    {/key}
  {/if}

  <dialog bind:this={dialog} aria-labelledby="dialog-title">
    <header><strong id="dialog-title">{$translate(modal === 'coordinates' ? 'Coordenadas WGS 84' : modal === 'restore' ? 'Recuperar configuración' : modal === 'chart-resolution' ? 'Resolución gráfica' : modal === 'chart-export' ? 'Guardar gráfica…' : 'Preferencias')}</strong><button class="icon-button" aria-label={$translate("Cerrar")} onclick={() => dialog.close()}><X size={17}/></button></header>
    {#if modal === 'coordinates'}
      <form onsubmit={submitCoordinates}>
        {#if tourPrefill}<p class="quiet">Tutorial: ya cargamos las coordenadas de la ciudad de San Luis. Pulsá «Agregar selección».</p>{/if}
        <label>{$translate("Nombre del lugar")}<input maxlength="100" bind:value={selectionName}/></label>
        <label>{$translate("Geometría")}<select bind:value={coordinateMode}><option value="point">{$translate("Punto")}</option><option value="polygon">{$translate("Polígono")}</option></select></label>
        {#if coordinateMode === 'point'}
          <div class="field-pair"><label>{$translate("Longitud")}<input type="number" min="-180" max="180" step="any" value={longitude} oninput={event => longitude = event.currentTarget.value}/></label><label>{$translate("Latitud")}<input type="number" min="-90" max="90" step="any" value={latitude} oninput={event => latitude = event.currentTarget.value}/></label></div>
        {:else}
          <label>{$translate("Vértices (longitud, latitud)")}<textarea rows="5" bind:value={polygonInput} placeholder={'-67.1, -33.8\n-66.4, -33.8\n-66.7, -33.2'}></textarea></label>
        {/if}
        {#if modalError}<p role="alert">{$translate(modalError)}</p>{/if}
        <button class="primary"><MapPin size={16}/> {$translate(editingFeature ? 'Guardar selección' : 'Agregar selección')}</button>
      </form>
    {:else if modal === 'restore'}
      <form onsubmit={event => { event.preventDefault(); dialog.close(); restore(); }}>
        <p>{$translate("Se reemplazarán los cambios actuales con la última configuración guardada.")}</p>
        <button class="primary"><FolderOpen size={16}/> {$translate("Recuperar")}</button>
      </form>
    {:else if modal === 'chart-resolution'}
      <div class="preferences">
        <label>{$translate('Resolución gráfica')}
          <select value={$workspace.visual.chartResolution ?? 'auto'} onchange={event => editVisual(visual => visual.chartResolution = event.currentTarget.value)}>
            {#each chartResolutions as [id, label]}<option value={id}>{$translate(label)}</option>{/each}
          </select>
        </label>
        <label>{$translate('Frecuencia del gráfico')}
          <select value={$workspace.visual.chartCadence ?? 'native'} onchange={event => editVisual(visual => visual.chartCadence = event.currentTarget.value)}>
            {#each chartCadences as [id, label]}<option value={id}>{$translate(label)}</option>{/each}
          </select>
        </label>
        <small>{$translate('Las series diarias se pueden agrupar. Se muestran solo semanas o meses completos y se conserva la frecuencia de las demás fuentes.')}</small>
      </div>
    {:else if modal === 'chart-export'}
      <form onsubmit={exportChart}>
        <label>{$translate('Gráfica')}
          <select bind:value={exportId}>
            {#each exportableSeries as item (item.id)}
              <option value={item.id}>{$translate(catalog.find(source => source.id === item.id.split('::')[0])?.label ?? item.variable)}</option>
            {/each}
          </select>
        </label>
        {#if modalError}<p role="alert">{$translate(modalError)}</p>{/if}
        <button class="primary" disabled={exporting}>{$translate('Guardar como PNG…')}</button>
      </form>
    {:else}
      <div class="preferences">
        <label>{$translate('Idioma')}<select value={$workspace.visual.language} onchange={event => editVisual(visual => visual.language = event.currentTarget.value)}><option value="es">Español</option><option value="en">English</option></select></label>
        <label>{$translate("Tema")}<select value={$workspace.visual.theme} onchange={event => editVisual(visual => visual.theme = event.currentTarget.value)}><option value="dark">{$translate("Oscuro")}</option><option value="light">{$translate("Claro")}</option></select></label>
        <label>{$translate("Tamaño del texto")}<select value={$workspace.visual.appearance.fontSize} onchange={event => editVisual(visual => visual.appearance.fontSize = Number(event.currentTarget.value))}><option value="12">{$translate("Compacto")}</option><option value="13">{$translate("Normal")}</option><option value="15">{$translate("Grande")}</option></select></label>
        <label>Nivel de experiencia (tutorial)<select value={tutorialLevel} onchange={event => setTutorialLevel(event.currentTarget.value)}>
          {#each LEVELS as [id, label] (id)}<option value={id}>{label}</option>{/each}
        </select></label>
        <button class="outlined" onclick={restartTutorial}>Ver el tutorial de nuevo</button>
        <label>{$translate("Color de acento")}<input type="color" value={customAccent ?? ($workspace.visual.theme === 'light' ? '#2563eb' : '#38bdf8')} oninput={event => editVisual(visual => visual.appearance.accent = event.currentTarget.value)}/></label>
      </div>
    {/if}
  </dialog>
</div>


<style>
  .map-results { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 8px; }
  .map-results > label { display: flex; align-items: center; gap: 8px; padding-bottom: 8px; }
  .map-results > label select { width: auto; max-width: 100%; }
  .ai-label { margin-left: auto; color: var(--muted); font-size: 11px; font-weight: 400; }
  .selection-menu { z-index: 30; min-width: 260px; max-width: 340px; max-height: 360px; overflow: auto; }
  .selection-row { display: flex; align-items: center; gap: 6px; }
  .selection-row span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
  .selection-menu .quiet { margin: 6px 8px; font-size: 12px; }
</style>
