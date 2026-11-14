<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { Aperture, Bot, ChevronDown, CircleHelp, Crosshair, Hand, MapPin, Play, Scan, Hexagon, Settings2, Square, Trash2, X, PanelLeft, PanelRight, Save, FolderOpen } from '@lucide/svelte';
  import Globe from '$lib/components/Globe.svelte';
  import Settings from '$lib/components/Settings.svelte';
  import Results from '$lib/components/Results.svelte';
  import Assistant from '$lib/components/Assistant.svelte';
  import ResizeHandle from '$lib/components/ResizeHandle.svelte';
  import { workspace, defaults, editData, editVisual, selectGeometry } from '$lib/stores/workspace.js';
  import { loadWorkspace, saveWorkspace, downloadJson } from '$lib/services/configuration.js';
  import { demoQuestion } from '$lib/services/demo.js';
  import { coordinateLabel, closedRegion, validCoordinates } from '$lib/services/geography.js';
  import '$lib/styles/dashboard.css';

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
  let editingFeature = $state(null);
  let coordinateMode = $state('point');
  let modalError = $state('');
  let chartId = $state('chart-trend');
  let running = $state(false);
  let resultsData = $state(null);
  let savedConfig = $state('');
  let storageBusy = $state(true);
  let timer;
  let panels = $derived($workspace.visual.workspace);
  let dirty = $derived(JSON.stringify($workspace) !== savedConfig);
  let configKey = $derived(JSON.stringify($workspace.data));
  let resultStatus = $derived(running ? 'En ejecución' : resultsData === null ? 'Vista previa' : resultsData === configKey ? 'Demostración completada' : 'Configuración modificada');
  let selected = $derived($workspace.data.geography.selection.features.at(-1));
  let messages = $state([
    { role:'user', text:demoQuestion },
    { role:'assistant', text:'Esta demostración propone comparar series de precipitación y humedad del suelo para una región aproximada de San Luis.', proposal:true }
  ]);
  const tools = [
    ['pan','Desplazar globo',Hand], ['point','Seleccionar punto',MapPin],
    ['rectangle','Selección rectangular',Scan], ['polygon','Selección poligonal',Hexagon]
  ];

  onMount(async () => {
    try {
      const saved = await loadWorkspace();
      if (saved) workspace.set({ ...defaults(), ...Object.fromEntries(Object.entries(saved).filter(([, value]) => value != null)) });
      chartId = $workspace.visual.charts[0]?.id;
      savedConfig = JSON.stringify($workspace);
    } catch (error) {
      notify('No se pudo recuperar la configuración. ' + (error.message ?? error));
    } finally { storageBusy = false; }
  });
  onDestroy(() => clearTimeout(timer));

  function notify(text) { notice = text; }
  function togglePanel(id, value = !panels[id]) { editVisual(visual => visual.workspace[id] = value); }
  function chooseTool(id) { tool = id; vertices = []; }
  function clearSelection() { vertices = []; editData(data => data.geography.selection.features = []); }
  function run() {
    if (running) return;
    const { sources, methods, time } = $workspace.data;
    if (!sources.length || !methods.length || !time.start || !time.end || time.start > time.end) {
      notify('Seleccioná una variable, un método y un intervalo de fechas válido.');
      return;
    }
    const startedWith = configKey;
    running = true;
    notify('Ejecutando demostración…');
    timer = setTimeout(() => { running = false; resultsData = startedWith; notify('Demostración completada'); }, 850);
  }
  function cancel() {
    clearTimeout(timer);
    running = false;
    notify('Demostración cancelada');
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
      notify('No se pudo guardar. ' + (error.message ?? error));
    } finally { storageBusy = false; }
  }
  async function restore() {
    if (storageBusy) return;
    storageBusy = true;
    try {
      const saved = await loadWorkspace();
      if (!saved) { notify('Todavía no hay una configuración guardada.'); return; }
      workspace.set({ ...defaults(), ...Object.fromEntries(Object.entries(saved).filter(([, value]) => value != null)) });
      chartId = $workspace.visual.charts[0]?.id;
      savedConfig = JSON.stringify($workspace);
      notify('Configuración recuperada');
    } catch (error) {
      notify('No se pudo recuperar. ' + (error.message ?? error));
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
    coordinateMode = feature?.geometry.type === 'Polygon' ? 'polygon' : 'point';
    longitude = feature?.geometry.type === 'Point' ? String(feature.geometry.coordinates[0]) : '';
    latitude = feature?.geometry.type === 'Point' ? String(feature.geometry.coordinates[1]) : '';
    polygonInput = feature?.geometry.type === 'Polygon'
      ? feature.geometry.coordinates[0].slice(0, -1).map(point => point.join(', ')).join('\n')
      : '';
    return showDialog('coordinates');
  }

  function saveSelection(type, coordinates, name) {
    if (!editingFeature) {
      selectGeometry(type, coordinates, name);
      return;
    }
    editData(data => {
      const feature = data.geography.selection.features.find(item => item.id === editingFeature.id);
      if (feature) feature.geometry = { type, coordinates };
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
      saveSelection('Point', center);
    } else {
      const points = polygonInput.trim().split(/\r?\n/).map(line => line.trim().split(/[ ,]+/).map(Number));
      if (points.some(point => point.length !== 2 || !validCoordinates(...point))) {
        modalError = 'Ingresá un par longitud, latitud por línea.';
        return;
      }
      const ring = closedRegion(points);
      if (!ring) { modalError = 'Ingresá al menos tres vértices que delimiten un área.'; return; }
      saveSelection('Polygon', ring, 'Polígono manual');
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
  async function menuAction(action) { menu = ''; await action(); }
  const menus = [
    ['Proyecto', [['Guardar configuración',save],['Recuperar configuración',() => dirty ? showDialog('restore') : restore()]]],
    ['Datos', [['Abrir configuración',() => togglePanel('settings',true)],['Ingresar coordenadas',() => openCoordinates()]]],
    ['Análisis', [['Ejecutar demostración',run],['Mostrar resultados',() => togglePanel('results',true)]]],
    ['Visualización', [['Alternar configuración',() => togglePanel('settings')],['Alternar resultados',() => togglePanel('results')]]],
    ['Capas', [['Alternar controles de capas',() => togglePanel('layers')]]],
    ['Exportar', [['Descargar cfg_data.json',() => downloadJson('cfg_data.json',$workspace.data)],['Descargar cfg_visual.json',() => downloadJson('cfg_visual.json',$workspace.visual)]]]
  ];
</script>

<svelte:head><title>Earth Detective</title><meta name="description" content="Espacio de trabajo para explorar tendencias del sistema terrestre."/></svelte:head>
<svelte:window onkeydown={event => {
  if (event.key === 'Escape') menu = '';
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(); }
}}/>

<div class="app-shell" class:light={$workspace.visual.theme === 'light'} style:--accent={$workspace.visual.appearance.accent} style:--base-size={$workspace.visual.appearance.fontSize + 'px'}>
  <header class="topbar">
    <div class="identity"><span class="brand-mark"><Aperture size={24} strokeWidth={1.7}/></span><strong>Earth Detective</strong></div>
    <nav aria-label="Menú principal">
      {#each menus as [name,actions]}
        <div class="menu-anchor">
          <button class:active={menu === name} aria-expanded={menu === name} onclick={() => menu = menu === name ? '' : name}>{name}<ChevronDown size={12}/></button>
          {#if menu === name}<div class="dropdown">{#each actions as [label,action]}<button onclick={() => menuAction(action)}>{label}</button>{/each}</div>{/if}
        </div>
      {/each}
    </nav>
    <div class="project-tag" title={$workspace.data.title}><span class="live-dot"></span>{$workspace.data.title || 'Proyecto sin nombre'}</div>
    <button class="icon-button top-icon" aria-label="Preferencias" title="Preferencias" onclick={() => showDialog('preferences')}><Settings2 size={17}/></button>
  </header>

  <div class="toolbar" aria-label="Herramientas">
    <div class="segmented">
      <button class:active={!panels.assistant} aria-pressed={!panels.assistant} onclick={() => togglePanel('assistant',false)}><Hand size={15}/> Manual</button>
      <button class:active={panels.assistant} aria-pressed={panels.assistant} onclick={() => togglePanel('assistant')}><Bot size={16}/> Asistente IA</button>
    </div>
    <div class="geo-tools">
      {#each tools as [id,label,Icon]}
        <button class="tool-button" class:active={id === tool} aria-pressed={id === tool} title={label} aria-label={label} onclick={() => chooseTool(id)}><Icon size={17}/></button>
      {/each}
      <button class="tool-button" title="Ingresar coordenadas" aria-label="Ingresar coordenadas" onclick={() => openCoordinates()}><Crosshair size={17}/></button>
      <button class="tool-button" title="Limpiar selecciones" aria-label="Limpiar selecciones" onclick={clearSelection}><Trash2 size={16}/></button>
    </div>
    <div class="panel-buttons">
      <button class="tool-button" class:active={panels.settings} title="Configuración" aria-label="Alternar panel de configuración" onclick={() => togglePanel('settings')}><PanelLeft size={17}/></button>
      <button class="tool-button" class:active={panels.results} title="Resultados" aria-label="Alternar panel de resultados" onclick={() => togglePanel('results')}><PanelRight size={17}/></button>
    </div>
    <div class="run-actions">
      <button class="primary run" onclick={run} disabled={running}><Play size={15} fill="currentColor"/> {running ? 'Ejecutando…' : 'Ejecutar análisis'}</button>
      <button class="tool-button outlined" disabled={!running} title="Cancelar" aria-label="Cancelar" onclick={cancel}><Square size={15}/></button>
    </div>
  </div>

  <main class="desktop" class:with-assistant={panels.assistant}
    style:--settings-width={panels.settingsWidth + 'px'} style:--results-width={panels.resultsWidth + 'px'} style:--assistant-width={panels.assistantWidth + 'px'}>
    {#if panels.settings}
      <Settings {chartId} {openCoordinates}/>
      <ResizeHandle label="Ancho del panel de configuración" value={panels.settingsWidth} min={220} max={450} resize={value => editVisual(visual => visual.workspace.settingsWidth = value)}/>
    {/if}
    <Globe {tool} bind:vertices bind:cursor bind:notice/>
    {#if panels.results}
      <ResizeHandle label="Ancho del panel de resultados" value={panels.resultsWidth} min={300} max={600} direction={-1} resize={value => editVisual(visual => visual.workspace.resultsWidth = value)}/>
      <Results bind:chartId {resultStatus}/>
    {/if}
    {#if panels.assistant}
      <ResizeHandle label="Ancho del asistente" value={panels.assistantWidth} min={270} max={470} direction={-1} resize={value => editVisual(visual => visual.workspace.assistantWidth = value)}/>
      <Assistant bind:messages close={() => togglePanel('assistant',false)} {notify}/>
    {/if}
  </main>

  <footer class="statusbar">
    <span><span class="live-dot"></span>{running ? 'En ejecución' : 'Listo'}</span>
    <span>{panels.assistant ? 'Asistido · demo' : 'Manual'}</span>
    <span class="status-coordinates"><Crosshair size={12}/> {cursor ? coordinateLabel(cursor) : selected?.geometry.type === 'Point' ? coordinateLabel(selected.geometry.coordinates) : selected?.properties.name || 'Sin selección'}</span>
    <span>{$workspace.data.sources.length} variables</span>
    <button onclick={save} disabled={storageBusy} title="Guardar configuración (Ctrl+S)"><Save size={13}/> {storageBusy ? 'Procesando' : dirty ? 'Sin guardar' : 'Guardado'}</button>
    <span class="status-results">{resultStatus}</span>
    <span class="footer-demo">Datos simulados</span>
  </footer>

  {#if notice}<div class="toast" role="status"><CircleHelp size={17}/><span>{notice}</span><button aria-label="Cerrar aviso" class="icon-button" onclick={() => notice = ''}><X size={15}/></button></div>{/if}

  <dialog bind:this={dialog} aria-labelledby="dialog-title">
    <header><strong id="dialog-title">{modal === 'coordinates' ? 'Coordenadas WGS 84' : modal === 'restore' ? 'Recuperar configuración' : 'Preferencias'}</strong><button class="icon-button" aria-label="Cerrar" onclick={() => dialog.close()}><X size={17}/></button></header>
    {#if modal === 'coordinates'}
      <form onsubmit={submitCoordinates}>
        <label>Geometría<select bind:value={coordinateMode}><option value="point">Punto</option><option value="polygon">Polígono</option></select></label>
        {#if coordinateMode === 'point'}
          <div class="field-pair"><label>Longitud<input type="number" min="-180" max="180" step="any" value={longitude} oninput={event => longitude = event.currentTarget.value}/></label><label>Latitud<input type="number" min="-90" max="90" step="any" value={latitude} oninput={event => latitude = event.currentTarget.value}/></label></div>
        {:else}
          <label>Vértices (longitud, latitud)<textarea rows="5" bind:value={polygonInput} placeholder={'-67.1, -33.8\n-66.4, -33.8\n-66.7, -33.2'}></textarea></label>
        {/if}
        {#if modalError}<p role="alert">{modalError}</p>{/if}
        <button class="primary"><MapPin size={16}/> {editingFeature ? 'Guardar selección' : 'Agregar selección'}</button>
      </form>
    {:else if modal === 'restore'}
      <form onsubmit={event => { event.preventDefault(); dialog.close(); restore(); }}>
        <p>Se reemplazarán los cambios actuales con la última configuración guardada.</p>
        <button class="primary"><FolderOpen size={16}/> Recuperar</button>
      </form>
    {:else}
      <div class="preferences">
        <label>Tema<select value={$workspace.visual.theme} onchange={event => editVisual(visual => visual.theme = event.currentTarget.value)}><option value="dark">Oscuro</option><option value="light">Claro</option></select></label>
        <label>Tamaño del texto<select value={$workspace.visual.appearance.fontSize} onchange={event => editVisual(visual => visual.appearance.fontSize = Number(event.currentTarget.value))}><option value="12">Compacto</option><option value="13">Normal</option><option value="15">Grande</option></select></label>
        <label>Color de acento<input type="color" value={$workspace.visual.appearance.accent} oninput={event => editVisual(visual => visual.appearance.accent = event.currentTarget.value)}/></label>
      </div>
    {/if}
  </dialog>
</div>
