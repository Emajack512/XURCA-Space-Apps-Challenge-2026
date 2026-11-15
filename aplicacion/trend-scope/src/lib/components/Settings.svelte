<script>
  import { translate } from '$lib/services/i18n.js';
  import { SlidersHorizontal, ChevronDown, Plus, X, Database, CalendarDays, MapPin, Pencil, FlaskConical } from '@lucide/svelte';
  import { workspace, editData } from '$lib/stores/workspace.js';
  import PlaceSearch from './PlaceSearch.svelte';
  import { catalog, providers, sourceConfig, variableCategories, variableOptions, legacyInaClimateVariable, coverageProblem, geographicEntityRoutes, entityGeometries, providerMatchesScope, providerGeometries, geometryMatchesScope, sourceMatchesScope } from '$lib/services/sources.js';
  import { coordinateLabel } from '$lib/services/geography.js';

  let { openCoordinates } = $props();
  let data = $derived($workspace.data);
  let features = $derived(data.geography.selection.features);
  let inferredScope = $derived(features.some(feature => feature.geometry.type === 'Point')
    ? features.some(feature => feature.geometry.type !== 'Point') ? 'both' : 'point'
    : features.length ? 'area' : '');
  let scope = $derived(data.geography.scope ?? inferredScope);
  let eligibleFeatures = $derived(features.filter(feature => geometryMatchesScope(feature.geometry.type, scope)));
  let targetId = $state('');
  let target = $derived(eligibleFeatures.find(feature => feature.id === targetId)
    ?? (eligibleFeatures.length === 1 ? eligibleFeatures[0] : null));
  let sourceChoice = $state('');
  let category = $state('weather');
  let availableVariables = $derived(variableOptions(scope, data.time, target?.geometry));
  let currentCategory = $derived(availableVariables.some(option => option.category === category) ? category : 'weather');
  let categoryVariables = $derived(availableVariables.filter(option => option.category === currentCategory));
  let choice = $derived(categoryVariables.find(option => option.id === sourceChoice));
  let selectedFeatures = $derived(choice?.item ? eligibleFeatures.filter(feature => {
    const types = providerGeometries(choice.item.route);
    return types.includes(feature.geometry.type);
  }) : []);
  let resolvedTarget = $derived(target ?? (selectedFeatures.length === 1 ? selectedFeatures[0] : null));
  let sections = $state({ objective: true });
  function addSource() {
    if (!choice?.item || (providerGeometries(choice.item.route).length && !resolvedTarget)) return;
    saveSource(choice.item, providerGeometries(choice.item.route).length ? resolvedTarget.id : null);
    sourceChoice = '';
  }

  function saveSource(item, geometryId, previousId = null) {
    const entry = sourceConfig(item.id);
    entry.upstream.geometryId = geometryId;
    editData(next => {
      next.geography.scope ??= scope;
      const existing = next.sources.find(source => source.id.split('::')[0] === item.id && source.upstream.geometryId === geometryId);
      if (next.sources.some(source => source.id === entry.id)) entry.id += '::' + geometryId;
      if (previousId) {
        next.sources = next.sources.flatMap(source => source.id !== previousId ? [source] : existing ? [] : [entry]);
      } else if (!existing) next.sources.push(entry);
    });
  }

  function replacementFor(item, feature) {
    const variable = legacyInaClimateVariable(item);
    if (!variable || !feature) return null;
    return variableOptions(scope, data.time, feature.geometry).find(option => option.id === variable)?.item;
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
    {#if scope}
      {@render group('sources','Fuentes de información',Database,sources)}
      {@render group('time','Período de análisis',CalendarDays,time)}
      {@render group('geography','Configuración geográfica',MapPin,geography)}
    {/if}
  </div>
</section>

{#snippet objective()}
  <label>{$translate('Zona o punto geográfico')}
    <select value={scope} onchange={event => set('geography', 'scope', event.currentTarget.value)}>
      <option disabled value="">{$translate('Elegí el alcance geográfico')}</option>
      <option value="point">{$translate('Punto geográfico')}</option>
      <option value="area">{$translate('Zona geográfica')}</option>
      <option value="both">{$translate('Ambos')}</option>
    </select>
  </label>
  <label>{$translate("Nombre del proyecto")}<input value={data.title} oninput={event => editData(next => next.title = event.currentTarget.value)}/></label>
  <label>{$translate("Objetivo")}<textarea value={data.objective} oninput={event => editData(next => next.objective = event.currentTarget.value)}></textarea></label>
  <label>{$translate("Descripción")}<textarea value={data.description} oninput={event => editData(next => next.description = event.currentTarget.value)}></textarea></label>
{/snippet}

{#snippet sources()}
  {#each data.sources as item (item.id)}
    {@const entry = catalog.find(source => source.id === item.id.split('::')[0])}
    {@const selectedRoute = providers.find(route => route.id === item.access)}
    {@const resolvesEntity = geographicEntityRoutes.has(item.access)}
    {@const geometryTypes = resolvesEntity ? entityGeometries : selectedRoute?.geometry ?? ['Point']}
    {@const active = sourceMatchesScope(item, scope, features)}
    {@const compatible = eligibleFeatures.filter(feature => geometryTypes.includes(feature.geometry.type))}
    {@const feature = features.find(feature => feature.id === item.upstream.geometryId) ?? (compatible.length === 1 ? compatible[0] : null)}
    {@const replacement = active ? replacementFor(item, feature) : null}
    {@const problem = entry ? coverageProblem(entry, data.time, feature?.geometry) : ''}
    <div class="selected-item"><div><strong>{$translate(entry?.label ?? item.variable)}</strong><small>{item.product}</small></div>
    <button class="icon-button" aria-label={$translate('Quitar') + ' ' + $translate(entry?.label ?? item.variable)} onclick={() => editData(next => next.sources = next.sources.filter(source => source.id !== item.id))}><X size={14}/></button></div>
    {#if active && problem}<small>{problem}</small>{/if}
    {#if selectedRoute?.disabled}
      <small>{$translate('Esta fuente está desactivada.')}</small>
    {:else if !active}
      <small>{$translate('En pausa para este alcance geográfico.')}</small>
    {/if}
    {#if selectedRoute && providerMatchesScope(selectedRoute, scope) && (resolvesEntity || selectedRoute.geometry || ['nasa.power.monthly', 'openmeteo.archive.daily'].includes(item.access))}
      {#if compatible.length !== 1 || !feature || feature.id !== compatible[0].id}
      <label>{$translate(geometryTypes.some(type => type !== 'Point') ? 'Geometría de consulta' : 'Punto de consulta')}
        <select value={item.upstream.geometryId ?? ''} onchange={event => editData(next => {
          next.sources.find(source => source.id === item.id).upstream.geometryId = event.currentTarget.value || null;
        })}>
          <option value="">{$translate("Usar la única selección compatible")}</option>
          {#each data.geography.selection.features.filter(feature => geometryTypes.includes(feature.geometry.type) && (geometryMatchesScope(feature.geometry.type, scope) || feature.id === item.upstream.geometryId)) as feature (feature.id)}
            <option value={feature.id}>{$translate(feature.properties.name || (feature.geometry.type === 'Point' ? coordinateLabel(feature.geometry.coordinates) : feature.id))}</option>
          {/each}
        </select>
      </label>
      {:else if feature.properties.name}
        <small>{feature.properties.name}</small>
      {/if}
    {/if}
    {#if active && legacyInaClimateVariable(item)}
      <small>{$translate('Esta serie depende de que haya una estación del INA con datos en las fechas elegidas.')}</small>
      {#if replacement}
        <button class="outlined" onclick={() => saveSource(replacement, feature.id, item.id)}>
          {$translate('Usar')} {replacement.route.label}
        </button>
      {/if}
    {/if}
    {#if item.access === 'usgs.earthquakes'}
      <label>{$translate('Magnitud mínima opcional')}
        <input type="number" step="any" value={item.upstream.selectors.minMagnitude ?? ''}
          oninput={event => editData(next => {
            next.sources.find(source => source.id === item.id).upstream.selectors.minMagnitude = event.currentTarget.value;
          })}/>
      </label>
    {/if}
  {/each}
  {#if eligibleFeatures.length > 1}
    <label>{$translate('Geometría de consulta')}
      <select value={targetId} onchange={event => targetId = event.currentTarget.value}>
        <option value="">{$translate('Usar la única selección compatible')}</option>
        {#each eligibleFeatures as feature (feature.id)}
          <option value={feature.id}>{feature.properties.name || (feature.geometry.type === 'Point' ? coordinateLabel(feature.geometry.coordinates) : feature.id)}</option>
        {/each}
      </select>
    </label>
  {/if}
  <label>{$translate('Categoría')}
    <select value={currentCategory} onchange={event => { category = event.currentTarget.value; sourceChoice = ''; }}>
      {#each variableCategories as [id, label] (id)}
        {#if availableVariables.some(option => option.category === id)}
          <option value={id}>{$translate(label)}</option>
        {/if}
      {/each}
    </select>
  </label>
  <div class="input-row">
    <select aria-label={$translate('Variable para agregar')} value={sourceChoice} onchange={event => sourceChoice = event.currentTarget.value}>
      <option value="" disabled>{$translate('Elegí una variable')}</option>
      {#each categoryVariables.filter(option => option.item) as option (option.id)}
        <option value={option.id}>{$translate(option.label)}</option>
      {/each}
      {#if categoryVariables.some(option => !option.item)}
        <optgroup label={$translate('Fuera de cobertura')}>
          {#each categoryVariables.filter(option => !option.item) as option (option.id)}
            <option value={option.id}>{$translate(option.label)}</option>
          {/each}
        </optgroup>
      {/if}
    </select>
    <button class="outlined" aria-label={$translate('Agregar variable')}
      disabled={!choice?.item || (providerGeometries(choice.item.route).length > 0 && !resolvedTarget)}
      onclick={addSource}><Plus size={14}/> {$translate('Agregar')}</button>
  </div>
  {#if choice?.problem}
    <small>{choice.problem}</small>
  {:else if choice?.item}
    <small>{choice.item.route.label} · {$translate(choice.item.label)}</small>
    {#if providerGeometries(choice.item.route).length && !resolvedTarget}
      <small>{$translate(eligibleFeatures.length > 1 ? 'Elegí qué selección del mapa usar.' : 'Seleccioná un punto o zona en el mapa.')}</small>
    {/if}
  {/if}
{/snippet}

{#snippet time()}
  <div class="field-pair">
    <label>{$translate("Desde")}<input type="date" value={data.time.start} oninput={event => set('time','start',event.currentTarget.value)}/></label>
    <label>{$translate("Hasta")}<input type="date" value={data.time.end} oninput={event => set('time','end',event.currentTarget.value)}/></label>
  </div>
  <small>{$translate("La frecuencia y la cobertura dependen del producto seleccionado.")}</small>
{/snippet}

{#snippet geography()}
  <PlaceSearch {scope}/>
  {#if scope === 'area'}
    <small>{$translate('Elegí un lugar con límite publicado o dibujá el área en el mapa.')}</small>
  {/if}
  {#each data.geography.selection.features as item (item.id)}
    <div class="selected-item"><div><strong>{$translate(item.properties.name || (item.geometry.type === 'Point' ? coordinateLabel(item.geometry.coordinates) : 'Zona geográfica'))}</strong>
      <small>{item.geometry.type === 'Point' ? $translate('Punto WGS 84') : $translate('Zona geográfica')}</small>
    </div>{#if item.geometry.type === 'Point' || (item.geometry.type === 'Polygon' && item.geometry.coordinates.length === 1)}
      <button class="icon-button" aria-label={$translate("Editar coordenadas")} onclick={() => openCoordinates(item)}><Pencil size={14}/></button>
    {/if}<button class="icon-button" aria-label={$translate("Eliminar selección")} onclick={() => editData(next => next.geography.selection.features = next.geography.selection.features.filter(feature => feature.id !== item.id))}><X size={14}/></button></div>
  {/each}
  <button class="outlined" onclick={() => openCoordinates()}><MapPin size={14}/> {$translate("Ingresar coordenadas")}</button>
{/snippet}

{#snippet options(label,value,items,change)}
  <label>{$translate(label)}<select {value} onchange={event => change(event.currentTarget.value)}>{#each items as item}<option value={item.id ?? item}>{item.label ?? item}</option>{/each}</select></label>
{/snippet}
