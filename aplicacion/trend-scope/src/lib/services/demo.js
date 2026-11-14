export const catalog = [
  { id: 'gldas-precipitation', provider: 'NASA', dataset: 'GLDAS', product: 'GLDAS', variable: 'precipitation', label: 'Precipitación', unit: 'mm/mes', coverage: 'Cobertura de muestra · mensual' },
  { id: 'gldas-soil', provider: 'NASA', dataset: 'GLDAS', product: 'GLDAS', variable: 'soil-moisture', label: 'Humedad del suelo', unit: 'm³/m³', coverage: 'Cobertura de muestra · mensual' },
  { id: 'fldas-soil', provider: 'NASA', dataset: 'FLDAS', product: 'FLDAS', variable: 'soil-moisture', label: 'Humedad del suelo', unit: 'm³/m³', coverage: 'Cobertura de muestra · mensual' },
  { id: 'noaa-temperature', provider: 'NOAA', dataset: 'CDO', product: 'CDO', variable: 'temperature', label: 'Temperatura', unit: '°C', coverage: 'Estaciones de muestra · mensual' }
];
export const methods = [
  { id: 'linear', label: 'Regresión lineal' },
  { id: 'mann-kendall', label: 'Mann-Kendall' },
  { id: 'sen', label: 'Pendiente de Sen' }
];
export const chartTypes = [
  { id: 'line', label: 'Serie temporal' }, { id: 'histogram', label: 'Histograma' },
  { id: 'comparison', label: 'Comparación' }, { id: 'scatter', label: 'Dispersión' }
];
export const sourceConfig = id => {
  const { label, coverage, ...fields } = catalog.find(item => item.id === id);
  return { ...fields, processingUnit: fields.unit, version: null, access: null, reference: null };
};
export const methodConfig = id => ({ id, parameters: {}, algorithmVersion: null, resultId: 'demo-trend' });
export const demoQuestion = '¿San Luis se está volviendo más seco?';
export const demoProposal = {
  type: 'Feature', id: 'demo-san-luis', properties: { name: 'San Luis · área de ejemplo', approximate: true },
  geometry: { type: 'Polygon', coordinates: [[[-67.13,-35.02],[-65.27,-35.02],[-65.27,-31.89],[-67.13,-31.89],[-67.13,-35.02]]] }
};
export const observations = Array.from({ length: 36 }, (_, index) => ({
  year: 2000 + index * 25 / 35,
  primary: Math.round(86 - index * 0.39 + Math.sin(index * 1.42) * 13 + Math.cos(index * 0.4) * 7),
  secondary: Math.round(77 - index * 0.22 + Math.sin(index * 1.19) * 9 + Math.cos(index * 0.3) * 4),
  trend: 86 - index * 0.39
}));
export const statistics = [
  ['Pendiente', '−0,55', 'mm/mes por año'], ['R²', '0,42', 'coef. determinación'],
  ['Valor p', '0,018', 'significancia'], ['IC 95 %', '−0,81 a −0,29', 'mm/mes por año'],
  ['Disponibilidad', '96 %', 'cobertura'], ['Observaciones', '36', 'valores de muestra']
];
