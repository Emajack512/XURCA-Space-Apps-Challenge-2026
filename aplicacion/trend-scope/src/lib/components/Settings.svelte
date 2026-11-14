<script>
  import { SlidersHorizontal, ChevronDown, Plus, X, Database, CalendarDays, MapPin, Pencil, Workflow, ChartNoAxesCombined, FlaskConical } from '@lucide/svelte';
  import { workspace, editData, editChart } from '$lib/stores/workspace.js';
  import { catalog, chartTypes, methods, methodConfig, sourceConfig } from '$lib/services/demo.js';
  import { coordinateLabel } from '$lib/services/geography.js';

  let { chartId, openCoordinates } = $props();
  let data = $derived($workspace.data);
  let chart = $derived($workspace.visual.charts.find(item => item.id === chartId));
  let source = $state('');
  let method = $state('');
  let sections = $state({ sources:true, time:true, methods:true });
  const set = (group, key, value) => editData(next => next[group][key] = value);
  const setMethodParameter = (id, key, value) => editData(next => next.methods.find(item => item.id === id).parameters[key] = value);
  const toggle = id => sections[id] = !sections[id];
  const update = (name, value) => editChart(chart.id, next => next[name] = value);
</script>

{#snippet group(id, label, icon, contents)}
  {@const Icon = icon}
  <section class="setting-group">
    <button class="section-toggle" onclick={() => toggle(id)} aria-expanded={!!sections[id]}><Icon size={15}/><span>{label}</span><ChevronDown class={sections[id] ? '' : 'closed'} size={14}/></button>
    {#if sections[id]}<div class="section-content">{@render contents()}</div>{/if}
  </section>
{/snippet}

<section class="settings-panel">
  <header class="panel-heading"><span><SlidersHorizontal size={16}/> Configuración</span></header>
  <div class="settings-scroll">
    {@render group('objective','Investigación',FlaskConical,objective)}
    {@render group('sources','Fuentes de información',Database,sources)}
    {@render group('time','Período de análisis',CalendarDays,time)}
    {@render group('geography','Configuración geográfica',MapPin,geography)}
    {@render group('processing','Procesamiento',Workflow,processing)}
    {@render group('methods','Métodos estadísticos',FlaskConical,analysis)}
    {@render group('charts','Apariencia de gráficas',ChartNoAxesCombined,appearance)}
  </div>
</section>

{#snippet objective()}
  <label>Nombre del proyecto<input value={data.title} oninput={event => editData(next => next.title = event.currentTarget.value)}/></label>
  <label>Objetivo<textarea value={data.objective} oninput={event => editData(next => next.objective = event.currentTarget.value)}></textarea></label>
  <label>Descripción<textarea value={data.description} oninput={event => editData(next => next.description = event.currentTarget.value)}></textarea></label>
{/snippet}

{#snippet sources()}
  {#each data.sources as item (item.id)}
    {@const entry = catalog.find(source => source.id === item.id)}
    <div class="selected-item"><div><strong>{entry?.label ?? item.variable}</strong><small>{item.provider} · {item.product} · {item.unit}</small><small>{entry?.coverage ?? ''}</small></div>
    <button class="icon-button" aria-label={'Quitar ' + (entry?.label ?? item.variable)} onclick={() => editData(next => next.sources = next.sources.filter(source => source.id !== item.id))}><X size={14}/></button></div>
  {/each}
  <div class="input-row">
    <select aria-label="Variable para agregar" bind:value={source}>
      <option value="">Seleccionar variable</option>
      {#each catalog.filter(item => !data.sources.some(selected => selected.id === item.id)) as item}
        <option value={item.id}>{item.provider} · {item.product} · {item.label}</option>
      {/each}
    </select>
    <button class="icon-button outlined" aria-label="Agregar variable" disabled={!source} onclick={() => { editData(next => next.sources.push(sourceConfig(source))); source = ''; }}><Plus size={16}/></button>
  </div>
{/snippet}

{#snippet time()}
  <div class="field-pair">
    <label>Desde<input type="date" value={data.time.start} oninput={event => set('time','start',event.currentTarget.value)}/></label>
    <label>Hasta<input type="date" value={data.time.end} oninput={event => set('time','end',event.currentTarget.value)}/></label>
  </div>
  {@render options('Resolución', data.time.resolution, ['Diaria','Mensual','Anual'], value => set('time','resolution',value))}
  {@render options('Agregación temporal', data.time.aggregation, ['Media','Suma','Mediana','Máximo'], value => set('time','aggregation',value))}
{/snippet}

{#snippet geography()}
  {@render options('Agregación espacial', data.geography.aggregation, ['Media de la región','Total','Por punto'], value => set('geography','aggregation',value))}
  {@render options('Interpolación', data.geography.interpolation, ['Ninguna','Vecino más cercano','Bilineal'], value => set('geography','interpolation',value))}
  {#each data.geography.selection.features as item (item.id)}
    <div class="selected-item"><div><strong>{item.properties.name || coordinateLabel(item.geometry.coordinates)}</strong>
      <small>{item.geometry.type === 'Point' ? 'Punto WGS 84' : (item.geometry.coordinates[0].length - 1) + ' vértices'}</small>
    </div><button class="icon-button" aria-label="Editar coordenadas" onclick={() => openCoordinates(item)}><Pencil size={14}/></button><button class="icon-button" aria-label="Eliminar selección" onclick={() => editData(next => next.geography.selection.features = next.geography.selection.features.filter(feature => feature.id !== item.id))}><X size={14}/></button></div>
  {/each}
  <button class="outlined" onclick={() => openCoordinates()}><MapPin size={14}/> Ingresar coordenadas</button>
{/snippet}

{#snippet processing()}
  {@render options('Valores faltantes', data.processing.missing, ['Excluir','Conservar','Interpolar'], value => set('processing','missing',value))}
  {@render options('Normalización', data.processing.normalization, ['Ninguna','Z-score','Min–max'], value => set('processing','normalization',value))}
  {#each [['quality','Filtrar por calidad'],['anomalies','Analizar anomalías'],['deseasonalize','Eliminar estacionalidad']] as [id,label]}
    {@render checkbox(label, data.processing[id], checked => set('processing',id,checked))}
  {/each}
{/snippet}

{#snippet analysis()}
  {#each data.methods as item (item.id)}
    <div class="selected-item"><strong>{methods.find(method => item.id === method.id)?.label ?? item.id}</strong>
      <button class="icon-button" aria-label="Quitar método" onclick={() => editData(next => next.methods = next.methods.filter(method => method.id !== item.id))}><X size={14}/></button></div>
    {#if item.id === 'linear'}
      {@render checkbox('Ajustar intercepto', item.parameters.fitIntercept ?? true, checked => setMethodParameter(item.id, 'fitIntercept', checked))}
    {:else if item.id === 'mann-kendall'}
      {@render options('Hipótesis alternativa', item.parameters.alternative ?? 'Bilateral', ['Bilateral','Creciente','Decreciente'], value => setMethodParameter(item.id, 'alternative', value))}
    {/if}
  {/each}
  <div class="input-row"><select aria-label="Método para agregar" bind:value={method}><option value="">Seleccionar método</option>
    {#each methods.filter(item => !data.methods.some(selected => selected.id === item.id)) as item}<option value={item.id}>{item.label}</option>{/each}
  </select><button class="icon-button outlined" disabled={!method} aria-label="Agregar método" onclick={() => { editData(next => next.methods.push(methodConfig(method))); method = ''; }}><Plus size={16}/></button></div>
  <div class="field-pair">
    <label>Significancia<input type="number" min="0.01" max="0.99" step="0.01" value={data.significance} onchange={event => { if (event.currentTarget.validity.valid && event.currentTarget.value) editData(next => next.significance = event.currentTarget.valueAsNumber); }}/></label>
    <label>Confianza<input type="number" min="0.01" max="0.99" step="0.01" value={data.confidence} onchange={event => { if (event.currentTarget.validity.valid && event.currentTarget.value) editData(next => next.confidence = event.currentTarget.valueAsNumber); }}/></label>
  </div>
{/snippet}

{#snippet appearance()}
  {#if chart}
    {@render options('Tipo de gráfica', chart.type, chartTypes, value => editChart(chart.id, next => { next.type = value; next.yLabel = value === 'histogram' ? 'Frecuencia' : 'mm/mes'; if (value === 'comparison') next.series.secondary.visible = true; }))}
    {#each [['title','Título'],['xLabel','Etiqueta del eje X'],['yLabel','Etiqueta del eje Y']] as [id,label]}
      <label>{label}<input value={chart[id]} oninput={event => update(id,event.currentTarget.value)}/></label>
    {/each}
    {@render options('Escala Y', chart.scale, [{id:'linear',label:'Lineal'},{id:'logarithmic',label:'Logarítmica'}], value => update('scale',value))}
    {#each [['grid','Grilla'], ['legend','Leyenda'], ['trend','Tendencia'], ['interval','Intervalo de confianza']] as [id,label]}
      {@render checkbox(label,chart[id],checked => update(id,checked))}
    {/each}
    {#each [['primary','Serie principal'], ['secondary','Serie comparativa']] as [id,label]}
      <div class="input-row">
        {@render checkbox(label,chart.series[id].visible,checked => editChart(chart.id, next => next.series[id].visible = checked))}
        <input type="color" aria-label={'Color de ' + label} value={chart.series[id].color} oninput={event => editChart(chart.id, next => next.series[id].color = event.currentTarget.value)}/>
      </div>
    {/each}
  {:else}<small>Seleccioná una gráfica para editar su apariencia.</small>{/if}
{/snippet}

{#snippet options(label,value,items,change)}
  <label>{label}<select {value} onchange={event => change(event.currentTarget.value)}>{#each items as item}<option value={item.id ?? item}>{item.label ?? item}</option>{/each}</select></label>
{/snippet}

{#snippet checkbox(label,value,change)}
  <label class="check-label"><input type="checkbox" checked={value} onchange={event => change(event.currentTarget.checked)}/>{label}</label>
{/snippet}
