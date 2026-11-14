<script>
  import { translate } from '$lib/services/i18n.js';
  import { SlidersHorizontal, ChevronDown, Plus, X, Database, CalendarDays, MapPin, Pencil, FlaskConical } from '@lucide/svelte';
  import { workspace, editData } from '$lib/stores/workspace.js';
  import PlaceSearch from './PlaceSearch.svelte';
  import { catalog, providers, sourceConfig, customSource } from '$lib/services/sources.js';
  import { coordinateLabel } from '$lib/services/geography.js';

  let { openCoordinates } = $props();
  let data = $derived($workspace.data);
  let provider = $state('nasa.power.monthly');
  let sourceChoice = $state('');
  let availableVariables = $derived(catalog.filter(item =>
    item.route.id === provider && !data.sources.some(selected => selected.id === item.id)
  ));
  let source = $derived(
    sourceChoice === 'custom' && provider !== 'openmeteo.archive.daily' ? 'custom'
      : availableVariables.some(item => item.id === sourceChoice) ? sourceChoice
      : availableVariables[0]?.id ?? (provider === 'openmeteo.archive.daily' ? '' : 'custom')
  );
  let code = $state('');
  let featureType = $state('Reach');
  let sections = $state({ sources:true, time:true, methods:true });
  function addSource() {
    const codeValue = provider === 'nasa.swot.hydrocron' ? code.trim().toLowerCase() : code.trim().toUpperCase();
    const type = provider === 'nasa.swot.hydrocron' ? featureType : null;
    const known = catalog.find(item => item.route.id === provider && item.code === codeValue && (item.featureType ?? null) === type);
    const entry = source !== 'custom' ? sourceConfig(source) : known ? sourceConfig(known.id) : customSource(provider, codeValue, type);
    if (!data.sources.some(item => item.id === entry.id)) editData(next => next.sources.push(entry));
    sourceChoice = '';
    code = '';
  }
  const set = (group, key, value) => editData(next => next[group][key] = value);
  const toggle = id => sections[id] = !sections[id];
</script>

{#snippet group(id, label, icon, contents)}
  {@const Icon = icon}
  <section class="setting-group">
    <button class="section-toggle" onclick={() => toggle(id)} aria-expanded={!!sections[id]}><Icon size={15}/><span>{$translate(label)}</span><ChevronDown class={sections[id] ? '' : 'closed'} size={14}/></button>
    {#if sections[id]}<div class="section-content">{@render contents()}</div>{/if}
  </section>
{/snippet}

<section class="settings-panel">
  <header class="panel-heading"><span><SlidersHorizontal size={16}/> {$translate("Configuración")}</span></header>
  <div class="settings-scroll">
    {@render group('objective','Investigación',FlaskConical,objective)}
    {@render group('sources','Fuentes de información',Database,sources)}
    {@render group('time','Período de análisis',CalendarDays,time)}
    {@render group('geography','Configuración geográfica',MapPin,geography)}
  </div>
</section>

{#snippet objective()}
  <label>{$translate("Nombre del proyecto")}<input value={data.title} oninput={event => editData(next => next.title = event.currentTarget.value)}/></label>
  <label>{$translate("Objetivo")}<textarea value={data.objective} oninput={event => editData(next => next.objective = event.currentTarget.value)}></textarea></label>
  <label>{$translate("Descripción")}<textarea value={data.description} oninput={event => editData(next => next.description = event.currentTarget.value)}></textarea></label>
{/snippet}

{#snippet sources()}
  {#each data.sources as item (item.id)}
    {@const entry = catalog.find(source => source.id === item.id)}
    <div class="selected-item"><div><strong>{$translate(entry?.label ?? item.variable)}</strong><small>{item.product}</small></div>
    <button class="icon-button" aria-label={$translate('Quitar') + ' ' + $translate(entry?.label ?? item.variable)} onclick={() => editData(next => next.sources = next.sources.filter(source => source.id !== item.id))}><X size={14}/></button></div>
    {#if item.access === 'noaa.ncei.station' || item.access === 'nasa.swot.hydrocron'}
      {@const field = item.access === 'noaa.ncei.station' ? 'stationId' : 'featureId'}
      <label>{$translate(field === 'stationId' ? 'ID de estación NOAA' : (item.upstream.selectors.featureType === 'Reach' ? 'ID SWOT de tramo' : 'ID SWOT de lago'))}
        <input value={item.upstream.selectors[field]} oninput={event => editData(next => {
          next.sources.find(source => source.id === item.id).upstream.selectors[field] = event.currentTarget.value;
        })}/>
      </label>
    {:else if ['nasa.power.monthly', 'openmeteo.archive.daily'].includes(item.access)}
      <label>{$translate('Punto de consulta')}
        <select value={item.upstream.geometryId ?? ''} onchange={event => editData(next => {
          next.sources.find(source => source.id === item.id).upstream.geometryId = event.currentTarget.value || null;
        })}>
          <option value="">{$translate("Usar el único punto marcado")}</option>
          {#each data.geography.selection.features.filter(feature => feature.geometry.type === 'Point') as feature (feature.id)}
            <option value={feature.id}>{$translate(feature.properties.name || coordinateLabel(feature.geometry.coordinates))}</option>
          {/each}
        </select>
      </label>
    {/if}
  {/each}
  <label>{$translate('Fuente de datos')}
    <select bind:value={provider} onchange={() => { sourceChoice = ''; code = ''; }}>
      {#each providers as entry}<option value={entry.id}>{entry.label}</option>{/each}
    </select>
  </label>
  <small>{$translate(providers.find(entry => entry.id === provider)?.hint)}</small>
  <div class="input-row">
    <select aria-label={$translate("Variable para agregar")} value={source} onchange={event => sourceChoice = event.currentTarget.value} disabled={!source}>
      {#if !source}<option disabled>{$translate("Sin variables disponibles")}</option>{/if}
      {#if provider !== 'openmeteo.archive.daily'}<option value="custom">{$translate("Ingresar código oficial…")}</option>{/if}
      {#each availableVariables as item}
        <option value={item.id}>{$translate(item.label)}</option>
      {/each}
    </select>
    <button class="icon-button outlined" aria-label={$translate("Agregar variable")} disabled={!source || (source === 'custom' && !/^[A-Za-z][A-Za-z0-9_]{0,159}$/.test(code.trim()))} onclick={addSource}><Plus size={16}/></button>
  </div>
  {#if source === 'custom'}
    <label>{$translate("Código oficial de variable")}<input bind:value={code}/></label>
    {#if provider === 'nasa.swot.hydrocron'}
      <label>{$translate("Entidad SWOT")}<select bind:value={featureType}>
        <option value="Reach">{$translate("Tramo de río")}</option>
        <option value="PriorLake">{$translate("Lago")}</option>
      </select></label>
    {/if}
  {/if}
{/snippet}

{#snippet time()}
  <div class="field-pair">
    <label>{$translate("Desde")}<input type="date" value={data.time.start} oninput={event => set('time','start',event.currentTarget.value)}/></label>
    <label>{$translate("Hasta")}<input type="date" value={data.time.end} oninput={event => set('time','end',event.currentTarget.value)}/></label>
  </div>
  <small>{$translate("POWER y NOAA devuelven series mensuales. Open-Meteo devuelve series diarias y SWOT observaciones por pasada.")}</small>
{/snippet}

{#snippet geography()}
  <PlaceSearch/>
  {#each data.geography.selection.features as item (item.id)}
    <div class="selected-item"><div><strong>{$translate(item.properties.name || coordinateLabel(item.geometry.coordinates))}</strong>
      <small>{item.geometry.type === 'Point' ? $translate('Punto WGS 84') : (item.geometry.coordinates[0].length - 1) + ' ' + $translate('vértices')}</small>
    </div><button class="icon-button" aria-label={$translate("Editar coordenadas")} onclick={() => openCoordinates(item)}><Pencil size={14}/></button><button class="icon-button" aria-label={$translate("Eliminar selección")} onclick={() => editData(next => next.geography.selection.features = next.geography.selection.features.filter(feature => feature.id !== item.id))}><X size={14}/></button></div>
  {/each}
  <button class="outlined" onclick={() => openCoordinates()}><MapPin size={14}/> {$translate("Ingresar coordenadas")}</button>
{/snippet}

{#snippet options(label,value,items,change)}
  <label>{$translate(label)}<select {value} onchange={event => change(event.currentTarget.value)}>{#each items as item}<option value={item.id ?? item}>{item.label ?? item}</option>{/each}</select></label>
{/snippet}
