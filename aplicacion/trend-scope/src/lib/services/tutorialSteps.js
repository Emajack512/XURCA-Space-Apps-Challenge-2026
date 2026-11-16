// Guided tour. One example all the way through: linear regression of the monthly air temperature
// of San Luis (city, San Luis province) from 2024 to 2025, returning slope, intercept and error.
//
// Each step: target (data-tour name to spotlight, or null for a centred card), text per level
// (a level without text skips the step), and how it advances: `when(state)` becomes true, or the user
// clicks the target (`click: true`), or presses Next. `doIt(api)` is the optional "Hacelo por mí".

export const EXAMPLE = {
  place: 'San Luis', longitude: -66.3356, latitude: -33.3017,
  start: '2024-01-01', end: '2025-12-31', sourceId: 'power-temperature', struct: 'regression_fit',
  prompt: 'Hacé una regresión lineal de la temperatura mensual de la ciudad de San Luis entre 2024 y 2025.'
};

export const LEVELS = [
  ['novice', 'Inexperto', 'Nunca usé herramientas de datos climáticos. Quiero que me expliquen todo.'],
  ['intermediate', 'Medio', 'Conozco lo básico de datos y gráficos. Prefiero explicaciones cortas.'],
  ['expert', 'Experto', 'Trabajo con datos y estadística. Solo quiero ubicar las funciones.']
];

const hasPoint = state => state.data.geography.selection.features.some(feature => feature.geometry.type === 'Point');
const hasSource = state => state.data.sources.some(source => source.id.split('::')[0] === EXAMPLE.sourceId);

export const STEPS = [
  {
    id: 'intro', target: null,
    text: {
      novice: `Vamos a hacer juntos un ejemplo completo: ver cómo cambió la temperatura del aire en la ciudad de San Luis entre 2024 y 2025, mes a mes, y ajustarle una recta (regresión lineal). Al final vas a obtener la pendiente (cuánto sube o baja por año), la ordenada al origen (dónde arranca la recta) y el error del ajuste.\n\nMientras dure el tutorial solo se puede usar lo que está iluminado.`,
      intermediate: 'Ejemplo guiado: regresión lineal de la temperatura mensual de San Luis, 2024–2025. Resultado: pendiente, ordenada y error.',
      expert: 'Recorrido rápido con un ejemplo: regresión lineal, temperatura mensual de San Luis, 2024–2025.'
    }
  },
  // ── Left panel: where the data comes from ──
  {
    id: 'settings', target: 'settings-button', when: state => state.settingsOpen,
    text: {
      novice: 'Primero, el panel de Configuración. Es donde se elige qué datos traer: el lugar, el período y la variable. Pulsá el botón del engranaje.',
      intermediate: 'Abrí Configuración con el engranaje.',
      expert: 'Configuración (engranaje): lugar, período y variables de la consulta.'
    },
    doIt: api => api.openSettings()
  },
  {
    id: 'scope', target: 'scope', when: state => state.data.geography.scope === 'point',
    reveal: 'objective',
    text: {
      novice: 'Vamos a estudiar un lugar puntual (la ciudad), no una zona. En «Zona o punto geográfico» elegí «Punto geográfico».',
      intermediate: 'En «Zona o punto geográfico» elegí «Punto geográfico».'
    },
    doIt: api => api.setScope('point')
  },
  {
    id: 'place', target: 'coordinates-button', when: hasPoint, reveal: 'geography',
    text: {
      novice: 'Ahora el lugar. Pulsá «Ingresar coordenadas»: vamos a dejar cargadas las de la ciudad de San Luis, y solo tenés que pulsar «Agregar selección». (También podés marcar un punto haciendo clic en el mapa con la herramienta de punto.)',
      intermediate: 'Pulsá «Ingresar coordenadas» y agregá San Luis (ya quedan cargadas).'
    },
    doIt: api => api.addExamplePoint()
  },
  {
    id: 'period', target: 'time', reveal: 'time',
    when: state => state.data.time.start === EXAMPLE.start && state.data.time.end === EXAMPLE.end,
    text: {
      novice: 'El período: cambiá «Desde» a 01/01/2024 y «Hasta» a 31/12/2025. Así tomamos dos años completos, 24 meses.',
      intermediate: 'Período: del 01/01/2024 al 31/12/2025.'
    },
    doIt: api => api.setPeriod(EXAMPLE.start, EXAMPLE.end)
  },
  {
    id: 'variable', target: 'sources', when: hasSource, reveal: 'sources',
    text: {
      novice: 'La variable: en «Fuentes de información», con la categoría de clima, elegí «Temperatura del aire a 2 m» y pulsá «Agregar». Es la temperatura mensual que publica la NASA (NASA POWER).',
      intermediate: 'En Fuentes, elegí «Temperatura del aire a 2 m» (NASA POWER) y pulsá Agregar.',
      expert: 'Fuentes de información: variables por categoría. Para el ejemplo: «Temperatura del aire a 2 m».'
    },
    doIt: api => api.addExampleSource()
  },
  {
    id: 'process', target: 'process', when: state => state.running || state.hasResults,
    text: {
      novice: 'Todo listo. Pulsá «Procesar»: la app descarga los datos de la fuente original y los grafica. Si te equivocaste, mientras procesa el botón cambia a «Cancelar».',
      intermediate: 'Pulsá «Procesar» para descargar y graficar los datos.',
      expert: '«Procesar» descarga y grafica la configuración (cancelable).'
    },
    doIt: api => api.process()
  },
  {
    id: 'results', target: 'view-tabs',
    text: {
      novice: 'Cada serie descargada aparece como una pestaña acá arriba. Al abrirla vas a ver la gráfica y, debajo, un resumen en palabras de lo que estás viendo. «Espacio de trabajo» vuelve al mapa.',
      intermediate: 'Las series quedan en pestañas; debajo de cada gráfica hay un resumen.'
    }
  },
  // ── Chat ──
  {
    id: 'chat', target: 'chat-send', click: true,
    prepare: api => api.writeChat(),
    text: {
      novice: 'El asistente hace lo mismo conversando. Ya escribimos el pedido de ejemplo en el chat; solo pulsá el botón de enviar. El asistente propone el análisis, y nada se ejecuta sin que lo confirmes.',
      intermediate: 'Dejamos un pedido de ejemplo en el chat: pulsá enviar.',
      expert: 'El asistente configura consultas y propone análisis a partir de texto. Probá con el ejemplo: pulsá enviar.'
    }
  },
  {
    id: 'chat-answer', target: 'assistant',
    text: {
      novice: 'Cuando responda, vas a ver un botón para ejecutar el análisis y otro para abrirlo en el panel y cambiarlo. Si el asistente no está disponible, no pasa nada: seguimos con el panel.',
      intermediate: 'Desde la respuesta podés ejecutar el análisis o abrirlo en el panel para cambiarlo.'
    }
  },
  // ── Analysis ──
  {
    id: 'analysis', target: 'analysis-button', when: state => state.analysisVisible,
    text: {
      novice: 'Ahora el análisis estadístico, paso a paso. Pulsá el botón del matraz.',
      intermediate: 'Abrí Análisis estadístico (matraz).',
      expert: 'Análisis estadístico (matraz): tendencia, anomalías, sequía, cambios, extremos, asociación, pronóstico y regresión.'
    },
    doIt: api => api.openAnalysis()
  },
  {
    id: 'struct', target: 'analysis-struct', when: state => state.form.structId === EXAMPLE.struct,
    text: {
      novice: 'En «Análisis» elegí «Ajuste de regresión». Es el que ajusta una recta a la serie.',
      intermediate: 'Elegí «Ajuste de regresión».'
    },
    doIt: api => api.chooseAnalysis()
  },
  {
    id: 'targets', target: 'analysis-targets', when: state => state.form.targets.length > 0,
    text: {
      novice: 'En «Variable» tiene que estar marcada «Temperatura del aire a 2 m». Los demás valores (nivel de confianza, etc.) se completan solos con valores estándar.',
      intermediate: 'Verificá que la variable esté marcada; el resto usa valores por defecto.'
    },
    doIt: api => api.chooseAnalysis()
  },
  {
    id: 'run', target: 'analysis-run', click: true,
    text: {
      novice: 'Pulsá «Analizar». La app vuelve a leer los datos y calcula el ajuste.',
      intermediate: 'Pulsá «Analizar».',
      expert: '«Analizar» ejecuta el análisis elegido (cancelable).'
    }
  },
  {
    id: 'output', target: 'analysis-output',
    text: {
      novice: 'Acá aparece el resultado. La pendiente dice cuántos °C sube o baja la temperatura por año; la ordenada al origen es el valor de la recta al comienzo; el error (RMSE) es cuánto se apartan en promedio los meses de la recta. Con solo dos años, el ciclo de verano e invierno pesa mucho: por eso el error es grande y la pendiente no indica una tendencia climática.',
      intermediate: 'Resultado: pendiente (°C/año), ordenada al origen y error (RMSE, R²). Dos años son pocos: es descriptivo.',
      expert: 'Salida: parámetros, métricas, avisos y «Cómo se calculó».'
    }
  },
  // ── Export ──
  {
    id: 'export', target: 'menu-Exportar', click: true,
    text: {
      novice: 'Para guardar tu trabajo, abrí el menú «Exportar». «Guardar gráfica…» guarda la gráfica como imagen PNG; «Descargar cfg_data.json» guarda la configuración de la consulta (lugar, período, variables) y «cfg_visual.json» la apariencia, para repetirla o compartirla.',
      intermediate: 'Menú «Exportar»: gráfica en PNG y configuraciones en JSON.',
      expert: '«Exportar»: PNG de gráficas y cfg_data/cfg_visual en JSON.'
    }
  },
  {
    id: 'end', target: 'assistant',
    text: {
      novice: '¡Listo! Para tus próximas investigaciones te recomendamos empezar por el asistente: contale con tus palabras qué querés estudiar, dónde y en qué período, y él arma la consulta y te propone el análisis. Podés repetir este tutorial o cambiar el nivel desde Preferencias.',
      intermediate: 'Listo. Para próximos ensayos, probá pedírselo directamente al asistente. El tutorial está en Preferencias.',
      expert: 'Listo. El asistente es el camino más rápido para nuevas consultas. Tutorial y nivel: Preferencias.'
    }
  }
];

export function stepsFor(level) {
  return STEPS.filter(step => step.text[level]);
}
