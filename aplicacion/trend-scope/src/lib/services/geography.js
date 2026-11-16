import { geoArea, geoOrthographic, geoPath } from 'd3-geo';

export const openPolygonNotice = 'Cerrá el polígono haciendo clic cerca del primer punto.';

export function nearPolygonStart(first, x, y) {
  return Math.hypot(first[0] - x, first[1] - y) <= 12;
}

export const initialCamera = { longitude: -66, latitude: -26, zoom: 1 };
const mapZoomOffset = 1.3;
export const toMapZoom = factor => mapZoomOffset + Math.log2(factor);
export const fromMapZoom = zoom => 2 ** (zoom - mapZoomOffset);
export const wrapLongitude = longitude => ((longitude + 180) % 360 + 360) % 360 - 180;
export const clampLatitude = latitude => Math.max(-89.9, Math.min(89.9, latitude));
export const validCoordinates = (longitude, latitude) => Number.isFinite(longitude) && Number.isFinite(latitude)
  && Math.abs(longitude) <= 180 && Math.abs(latitude) <= 90;

export function makeProjection(width, height, camera) {
  return geoOrthographic()
    .translate([width / 2, height / 2])
    .scale(Math.min(width, height) * 0.445 * camera.zoom)
    .rotate([-camera.longitude, -camera.latitude])
    .clipAngle(90);
}

export function positionAt(projection, x, y) {
  const [cx, cy] = projection.translate();
  if (Math.hypot(x - cx, y - cy) > projection.scale()) return null;
  return projection.invert([x, y]).map(value => Number(value.toFixed(5)));
}

// Shapes thinner than a ~1:60 strip touch too few grid cells for an area average.
const minimumCompactness = 0.05;

function segmentsCross([a, b], [c, d]) {
  const side = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  return side(a, b, c) * side(a, b, d) < 0 && side(c, d, a) * side(c, d, b) < 0;
}

/**
 * Why a ring of vertices cannot be used as a query area, or '' when it can.
 * Rejects self-crossing outlines ("bow ties", areas that fold over themselves) and very narrow strips.
 */
export function regionProblem(vertices) {
  const points = vertices.filter((point, index) => {
    const previous = vertices[index - 1];
    return !previous || point[0] !== previous[0] || point[1] !== previous[1];
  });
  if (points.length > 1 && points[0][0] === points.at(-1)[0] && points[0][1] === points.at(-1)[1]) points.pop();
  if (points.length < 3) return 'Marcá al menos tres vértices que delimiten un área.';
  const meanLatitude = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  const scale = Math.cos(meanLatitude * Math.PI / 180);
  const planar = points.map(([lon, lat]) => [lon * scale, lat]);
  const edges = planar.map((point, index) => [point, planar[(index + 1) % planar.length]]);
  for (let i = 0; i < edges.length; i++) {
    for (let j = i + 2; j < edges.length; j++) {
      if (i === 0 && j === edges.length - 1) continue;
      if (segmentsCross(edges[i], edges[j])) {
        return 'El polígono se cruza consigo mismo. Dibujá el contorno sin que los lados se crucen.';
      }
    }
  }
  const area = Math.abs(planar.reduce((sum, [x, y], index) => {
    const [nextX, nextY] = planar[(index + 1) % planar.length];
    return sum + x * nextY - nextX * y;
  }, 0)) / 2;
  const perimeter = edges.reduce((sum, [p, q]) => sum + Math.hypot(q[0] - p[0], q[1] - p[1]), 0);
  if (!area || 4 * Math.PI * area / perimeter ** 2 < minimumCompactness) {
    return 'El polígono es demasiado angosto: cubriría muy pocas celdas de las grillas y el promedio no sería representativo. Dibujá un área más ancha.';
  }
  return '';
}

export function closedRegion(vertices) {
  const points = vertices.filter((point, index) => {
    const previous = vertices[index - 1];
    return !previous || point[0] !== previous[0] || point[1] !== previous[1];
  });
  const first = points[0];
  const last = points.at(-1);
  if (points.length > 1 && first[0] === last[0] && first[1] === last[1]) points.pop();
  if (points.length < 3 || Math.max(...points.map(point => point[0])) - Math.min(...points.map(point => point[0])) > 180) return null;
  const signedArea = points.reduce((sum, [x, y], index) => {
    const [nextX, nextY] = points[(index + 1) % points.length];
    return sum + x * nextY - nextX * y;
  }, 0);
  if (points.length < 3 || Math.abs(signedArea) < 1e-10 || regionProblem(points)) return null;
  // GeoJSON exterior rings use counterclockwise order.
  if (signedArea < 0) points.reverse();
  return [[...points, points[0]]];
}

export function rectangle(first, last) {
  if (Math.abs(first[0] - last[0]) > 180) return null;
  return closedRegion([first, [last[0], first[1]], last, [first[0], last[1]]]);
}

export function draftGeometry(vertices) {
  return vertices.length > 1 ? { type: 'LineString', coordinates: vertices } : null;
}

export function addPolygonVertex(vertices, point) {
  if (vertices.some(([lon, lat]) => lon === point[0] && lat === point[1])) {
    return vertices;
  }
  return [...vertices, point];
}

export function featurePath(projection, item) {
  const geometry = item.geometry;
  // Imported boundaries can wind in either direction. D3 expects small
  // exteriors and complementary interiors on the sphere.
  const orientPolygon = polygon => polygon.map((ring, index) => {
    const complementary = geoArea({ type: 'Polygon', coordinates: [ring] }) > 2 * Math.PI;
    return complementary === (index > 0) ? ring : [...ring].reverse();
  });
  const drawable = geometry.type === 'Polygon' ? { ...geometry, coordinates: orientPolygon(geometry.coordinates) }
    : geometry.type === 'MultiPolygon' ? { ...geometry, coordinates: geometry.coordinates.map(orientPolygon) }
      : geometry;
  return geoPath(projection)(drawable);
}

export function coordinateLabel(point) {
  return point ? point.map(value => value.toFixed(3) + '°').join(', ') : '—';
}
