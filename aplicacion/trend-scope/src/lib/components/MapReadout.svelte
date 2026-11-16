<script>
  import { coordinateLabel } from '$lib/services/geography.js';

  let { cursor = null } = $props();
</script>

<div class="map-top">
  <span class="map-pill">WGS 84</span>
  <span class="map-pill">{coordinateLabel(cursor)}</span>
</div>
