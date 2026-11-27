document.documentElement.classList.remove('no-js');
document.documentElement.classList.add('js-ready');

/* ========== Theme Button Web Component (Annotated, use action-btn style instead) ========== */
/*
(() => {
  const themeButtonFunc = (root, initTheme, changeTheme) => {
    const checkbox = root.querySelector('.theme-checkbox');
    // initialization state
    if (initTheme === 'dark') {
      checkbox.checked = true;
    }
    // Core interaction: Check to switch dark/light, external synchronization through changeTheme callbackTheme
    checkbox.addEventListener('change', (e) => {
      const isDark = e.target.checked;
      changeTheme(isDark ? 'dark' : 'light');
    });
  };

  class ThemeButton extends HTMLElement {
    constructor() { super(); }
    connectedCallback() {
      const initTheme = this.getAttribute("value") || "light";
      const size = +this.getAttribute("size") || 1.5;

      const shadow = this.attachShadow({ mode: "closed" });
      const container = document.createElement("div");
      container.setAttribute("class", "container");
      container.style.fontSize = `${size * 10}px`;

      // Component structure：checkbox + label，label Contains sky/stars/clouds and moon dots, which are visually the Theme switching buttons.
      container.textContent = '';
      container.insertAdjacentHTML('beforeend', [
        '<div class="toggle-wrapper">',
        '  <input type="checkbox" class="theme-checkbox" id="theme-toggle-input">',
        '  <label for="theme-toggle-input" class="toggle-label">',
        '    <div class="toggle-background">',
        '      <div class="stars">',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '      </div>',
        '      <div class="clouds">',
        '        <span class="cloud"></span>',
        '        <span class="cloud"></span>',
        '      </div>',
        '    </div>',
        '    <div class="toggle-circle">',
        '      <div class="moon-crater"></div>',
        '      <div class="moon-crater"></div>',
        '      <div class="moon-crater"></div>',
        '    </div>',
        '  </label>',
        '</div>'
      ].join(''));

      const style = document.createElement("style");
      style.textContent = [
        '* { box-sizing: border-box; margin: 0; padding: 0; }',
        '.container { display: inline-block; position: relative; width: 5.4em; height: 2.6em; vertical-align: middle; }',
        '.toggle-wrapper { width: 100%; height: 100%; }',
        '.theme-checkbox { display: none; }',
        '.toggle-label { display: block; width: 100%; height: 100%; border-radius: 2.6em; background-color: #87CEEB; cursor: pointer; position: relative; overflow: hidden; transition: background-color 0.5s ease; box-shadow: inset 0 0.1em 0.3em rgba(0,0,0,0.2); }',
        '.theme-checkbox:checked + .toggle-label { background-color: #1F2937; }',
        '.toggle-circle { position: absolute; top: 0.2em; left: 0.2em; width: 2.2em; height: 2.2em; border-radius: 50%; background-color: #FFD700; box-shadow: 0 0.1em 0.2em rgba(0,0,0,0.3); transition: transform 0.5s cubic-bezier(0.4, 0.0, 0.2, 1), background-color 0.5s ease; z-index: 2; }',
        '.theme-checkbox:checked + .toggle-label .toggle-circle { transform: translateX(2.8em); background-color: #F3F4F6; box-shadow: inset -0.2em -0.2em 0.2em rgba(0,0,0,0.1), 0 0.1em 0.2em rgba(255,255,255,0.2); }',
        '.moon-crater { position: absolute; background-color: rgba(200, 200, 200, 0.6); border-radius: 50%; opacity: 0; transition: opacity 0.3s ease; }',
        '.theme-checkbox:checked + .toggle-label .toggle-circle .moon-crater { opacity: 1; }',
        '.moon-crater:nth-child(1) { width: 0.6em; height: 0.6em; top: 0.4em; left: 0.8em; }',
        '.moon-crater:nth-child(2) { width: 0.4em; height: 0.4em; top: 1.2em; left: 0.4em; }',
        '.moon-crater:nth-child(3) { width: 0.3em; height: 0.3em; top: 1.4em; left: 1.2em; }',
        '.toggle-background { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }',
        '.clouds { position: absolute; width: 100%; height: 100%; transition: transform 0.5s ease, opacity 0.5s ease; opacity: 1; }',
        '.theme-checkbox:checked + .toggle-label .clouds { transform: translateY(100%); opacity: 0; }',
        '.cloud { position: absolute; background-color: #fff; border-radius: 2em; opacity: 0.9; }',
        '.cloud::before { content: ""; position: absolute; top: -40%; left: 15%; width: 50%; height: 100%; background-color: inherit; border-radius: 50%; }',
        '.cloud::after { content: ""; position: absolute; top: -55%; left: 45%; width: 50%; height: 120%; background-color: inherit; border-radius: 50%; }',
        '.cloud:nth-child(1) { width: 1.4em; height: 0.5em; top: 0.8em; right: 1.0em; }',
        '.cloud:nth-child(2) { width: 1.0em; height: 0.4em; top: 1.6em; right: 2.0em; opacity: 0.7; }',
        '.stars { position: absolute; width: 100%; height: 100%; transition: transform 0.5s ease, opacity 0.5s ease; transform: translateY(-100%); opacity: 0; }',
        '.theme-checkbox:checked + .toggle-label .stars { transform: translateY(0); opacity: 1; }',
        '.star { position: absolute; background-color: #FFF; border-radius: 50%; width: 0.15em; height: 0.15em; box-shadow: 0 0 0.2em #FFF; animation: twinkle 2s infinite ease-in-out; }',
        '.star:nth-child(1) { top: 0.6em; left: 1.0em; animation-delay: 0s; }',
        '.star:nth-child(2) { top: 1.6em; left: 1.8em; width: 0.1em; height: 0.1em; animation-delay: 0.5s; }',
        '.star:nth-child(3) { top: 0.8em; left: 2.4em; width: 0.12em; height: 0.12em; animation-delay: 1s; }',
        '.star:nth-child(4) { top: 1.8em; left: 0.8em; width: 0.08em; height: 0.08em; animation-delay: 1.5s; }',
        '@keyframes twinkle { 0%, 100% { opacity: 0.4; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.2); } }'
      ].join(' ');

      const changeThemeWrapper = (detail) => {
        this.dispatchEvent(new CustomEvent("change", { detail }));
      };

      themeButtonFunc(container, initTheme, changeThemeWrapper);
      shadow.appendChild(style);
      shadow.appendChild(container);
    }
  }
  customElements.define("theme-button", ThemeButton);
})();
*/
/* ========== End Theme Button Web Component ========== */

 const chartRegistry = [];
const wordCloudRegistry = new Map();
const STABLE_CHART_TYPES = ['line', 'bar'];
const CHART_TYPE_LABELS = {
  line: 'Line chart',
  bar: 'bar chart',
  doughnut: 'donut chart',
  pie: 'pie chart',
  radar: 'radar chart',
  polarArea: 'polar regions map'
};

// Color replacement/brightening rules consistent with PDF vector rendering
const DEFAULT_CHART_COLORS = [
  '#4A90E2', '#E85D75', '#50C878', '#FFB347',
  '#9B59B6', '#3498DB', '#E67E22', '#16A085',
  '#F39C12', '#D35400', '#27AE60', '#8E44AD'
];
const CSS_VAR_COLOR_MAP = {
  'var(--chart-color-green)': '#4BC0C0',
  'var(--chart-color-red)': '#FF6384',
  'var(--chart-color-blue)': '#36A2EB',
  'var(--color-accent)': '#4A90E2',
  'var(--re-accent-color)': '#4A90E2',
  'var(--re-accent-color-translucent)': 'rgba(74, 144, 226, 0.08)',
  'var(--color-kpi-down)': '#E85D75',
  'var(--re-danger-color)': '#E85D75',
  'var(--re-danger-color-translucent)': 'rgba(232, 93, 117, 0.08)',
  'var(--color-warning)': '#FFB347',
  'var(--re-warning-color)': '#FFB347',
  'var(--re-warning-color-translucent)': 'rgba(255, 179, 71, 0.08)',
  'var(--color-success)': '#50C878',
  'var(--re-success-color)': '#50C878',
  'var(--re-success-color-translucent)': 'rgba(80, 200, 120, 0.08)',
  'var(--color-accent-positive)': '#50C878',
  'var(--color-accent-negative)': '#E85D75',
  'var(--color-text-secondary)': '#6B7280',
  'var(--accentPositive)': '#50C878',
  'var(--accentNegative)': '#E85D75',
  'var(--sentiment-positive, #28A745)': '#28A745',
  'var(--sentiment-negative, #E53E3E)': '#E53E3E',
  'var(--sentiment-neutral, #FFC107)': '#FFC107',
  'var(--sentiment-positive)': '#28A745',
  'var(--sentiment-negative)': '#E53E3E',
  'var(--sentiment-neutral)': '#FFC107',
  'var(--color-primary)': '#3498DB',
  'var(--color-secondary)': '#95A5A6'
};
const WORDCLOUD_CATEGORY_COLORS = {
  positive: '#10b981',
  negative: '#ef4444',
  neutral: '#6b7280',
  controversial: '#f59e0b'
};

function normalizeColorToken(color) {
  if (typeof color !== 'string') return color;
  const trimmed = color.trim();
  if (!trimmed) return null;
  // support var(--token, degrade) form, parsing firstdegrade
  const varWithDegrade = trimmed.match(/^var\(\s*--[^,)+]+,\s*([^)]+)\)/i);
  if (varWithDegrade && varWithDegrade[1]) {
    const degrade = varWithDegrade[1].trim();
    const normalizedDegrade = normalizeColorToken(degrade);
    if (normalizedDegrade) return normalizedDegrade;
  }
  if (CSS_VAR_COLOR_MAP[trimmed]) {
    return CSS_VAR_COLOR_MAP[trimmed];
  }
  if (trimmed.startsWith('var(')) {
    if (/accent|primary/i.test(trimmed)) return '#4A90E2';
    if (/danger|down|error/i.test(trimmed)) return '#E85D75';
    if (/warning/i.test(trimmed)) return '#FFB347';
    if (/success|up/i.test(trimmed)) return '#50C878';
    return '#3498DB';
  }
  return trimmed;
}

function hexToRgb(color) {
  if (typeof color !== 'string') return null;
  const normalized = color.replace('#', '');
  if (!(normalized.length === 3 || normalized.length === 6)) return null;
  const hex = normalized.length === 3 ? normalized.split('').map(c => c + c).join('') : normalized;
  const intVal = parseInt(hex, 16);
  if (Number.isNaN(intVal)) return null;
  return [(intVal >> 16) & 255, (intVal >> 8) & 255, intVal & 255];
}

function parseRgbString(color) {
  if (typeof color !== 'string') return null;
  const match = color.match(/rgba?\s*\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(',').map(p => parseFloat(p.trim())).filter(v => !Number.isNaN(v));
  if (parts.length < 3) return null;
  return [parts[0], parts[1], parts[2]].map(v => Math.max(0, Math.min(255, v)));
}

function alphaFromColor(color) {
  if (typeof color !== 'string') return null;
  const raw = color.trim();
  if (!raw) return null;
  if (raw.toLowerCase() === 'transparent') return 0;

  const extractAlpha = (source) => {
    const match = source.match(/rgba?\s*\(([^)]+)\)/i);
    if (!match) return null;
    const parts = match[1].split(',').map(p => p.trim());
    if (source.toLowerCase().startsWith('rgba') && parts.length >= 2) {
      const alphaToken = parts[parts.length - 1];
      const isPercent = /%$/.test(alphaToken);
      const alphaVal = parseFloat(alphaToken.replace('%', ''));
      if (!Number.isNaN(alphaVal)) {
        const normalizedAlpha = isPercent ? alphaVal / 100 : alphaVal;
        return Math.max(0, Math.min(1, normalizedAlpha));
      }
    }
    if (parts.length >= 3) return 1;
    return null;
  };

  const rawAlpha = extractAlpha(raw);
  if (rawAlpha !== null) return rawAlpha;

  const normalized = normalizeColorToken(raw);
  if (typeof normalized === 'string' && normalized !== raw) {
    const normalizedAlpha = extractAlpha(normalized);
    if (normalizedAlpha !== null) return normalizedAlpha;
  }

  return null;
}

function rgbFromColor(color) {
  const normalized = normalizeColorToken(color);
  return hexToRgb(normalized) || parseRgbString(normalized);
}

function colorLuminance(color) {
  const rgb = rgbFromColor(color);
  if (!rgb) return null;
  const [r, g, b] = rgb.map(v => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function lightenColor(color, ratio) {
  const rgb = rgbFromColor(color);
  if (!rgb) return color;
  const factor = Math.min(1, Math.max(0, ratio || 0.25));
  const mixed = rgb.map(v => Math.round(v + (255 - v) * factor));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
}

function ensureAlpha(color, alpha) {
  const rgb = rgbFromColor(color);
  if (!rgb) return color;
  const clamped = Math.min(1, Math.max(0, alpha));
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${clamped})`;
}

function liftDarkColor(color) {
  const normalized = normalizeColorToken(color);
  const lum = colorLuminance(normalized);
  if (lum !== null && lum < 0.12) {
    return lightenColor(normalized, 0.35);
  }
  return normalized;
}

function mixColors(colorA, colorB, amount) {
  const rgbA = rgbFromColor(colorA);
  const rgbB = rgbFromColor(colorB);
  if (!rgbA && !rgbB) return colorA || colorB;
  if (!rgbA) return colorB;
  if (!rgbB) return colorA;
  const t = Math.min(1, Math.max(0, amount || 0));
  const mixed = rgbA.map((v, idx) => Math.round(v * (1 - t) + rgbB[idx] * t));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
}

function pickComputedColor(keys, degrade, styles) {
  const styleRef = styles || getComputedStyle(document.body);
  for (const key of keys) {
    const val = styleRef.getPropertyValue(key);
    if (val && val.trim()) {
      const normalized = normalizeColorToken(val.trim());
      if (normalized) return normalized;
    }
  }
  return degrade;
}

function resolveWordcloudTheme() {
  const styles = getComputedStyle(document.body);
  const isDark = document.body.classList.contains('dark-mode');
  const text = pickComputedColor(['--text-color'], isDark ? '#e5e7eb' : '#111827', styles);
  const secondary = pickComputedColor(['--secondary-color', '--color-text-secondary'], isDark ? '#cbd5e1' : '#475569', styles);
  const accent = liftDarkColor(
    pickComputedColor(['--primary-color', '--color-accent', '--re-accent-color'], '#4A90E2', styles)
  );
  const cardBg = pickComputedColor(
    ['--card-bg', '--paper-bg', '--bg', '--bg-color', '--background', '--page-bg'],
    isDark ? '#0f172a' : '#ffffff',
    styles
  );
  return { text, secondary, accent, cardBg, isDark };
}

function normalizeDatasetColors(payload, chartType) {
  const changes = [];
  const data = payload && payload.data;
  if (!data || !Array.isArray(data.datasets)) {
    return changes;
  }
  const type = chartType || 'bar';
  const needsArrayColors = type === 'pie' || type === 'doughnut' || type === 'polarArea';
  const MIN_PIE_ALPHA = 0.6;
  const pickColor = (value, degrade) => {
    if (Array.isArray(value) && value.length) return value[0];
    return value || degrade;
  };

  data.datasets.forEach((dataset, idx) => {
    if (!isPlainObject(dataset)) return;
    if (type === 'line') {
      dataset.fill = true;  // Force filling on for line charts to facilitate regional comparisons
    }
    const paletteColor = normalizeColorToken(DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length]);
    const borderInput = dataset.borderColor;
    const backgroundInput = dataset.backgroundColor;
    const borderIsArray = Array.isArray(borderInput);
    const bgIsArray = Array.isArray(backgroundInput);
    const baseCandidate = pickColor(borderInput, pickColor(backgroundInput, dataset.color || paletteColor));
    const liftedBase = liftDarkColor(baseCandidate || paletteColor);

    if (needsArrayColors) {
      const labelCount = Array.isArray(data.labels) ? data.labels.length : 0;
      const rawColors = bgIsArray ? backgroundInput : [];
      const dataLength = Array.isArray(dataset.data) ? dataset.data.length : 0;
      const total = Math.max(labelCount, rawColors.length, dataLength, 1);
      const normalizedColors = [];
      let fixedTransparentCount = 0;
      for (let i = 0; i < total; i++) {
        const degradeColor = DEFAULT_CHART_COLORS[(idx + i) % DEFAULT_CHART_COLORS.length];
        const normalizedRaw = normalizeColorToken(rawColors[i]);
        const alpha = alphaFromColor(normalizedRaw);
        const isInvisible = typeof normalizedRaw === 'string' && normalizedRaw.toLowerCase() === 'transparent';
        if (alpha === 0 || isInvisible) {
          fixedTransparentCount += 1;
        }
        const baseColor = (!normalizedRaw || isInvisible) ? degradeColor : normalizedRaw;
        const targetAlpha = alpha === null ? 1 : alpha;
        const normalizedColor = ensureAlpha(
          liftDarkColor(baseColor),
          Math.max(MIN_PIE_ALPHA, targetAlpha)
        );
        normalizedColors.push(normalizedColor);
      }
      dataset.backgroundColor = normalizedColors;
      dataset.borderColor = normalizedColors.map(col => ensureAlpha(liftDarkColor(col), 1));
      const changeLabel = fixedTransparentCount
        ? `dataset${idx}: Correction${fixedTransparentCount}transparent sectors`
        : `dataset${idx}: Normalized sector color(${normalizedColors.length})`;
      changes.push(changeLabel);
      return;
    }

    if (!borderInput) {
      dataset.borderColor = liftedBase;
      changes.push(`dataset${idx}: Completion border color`);
    } else if (borderIsArray) {
      dataset.borderColor = borderInput.map(col => liftDarkColor(col));
    } else {
      dataset.borderColor = liftDarkColor(borderInput);
    }

    const typeAlpha = type === 'line'
      ? (dataset.fill ? 0.25 : 0.18)
      : type === 'radar'
        ? 0.25
        : type === 'scatter' || type === 'bubble'
          ? 0.6
          : type === 'bar'
            ? 0.85
            : null;

    if (typeAlpha !== null) {
      if (bgIsArray && dataset.backgroundColor.length) {
        dataset.backgroundColor = backgroundInput.map(col => ensureAlpha(liftDarkColor(col), typeAlpha));
      } else {
        const bgSeed = pickColor(backgroundInput, pickColor(dataset.borderColor, paletteColor));
        dataset.backgroundColor = ensureAlpha(liftDarkColor(bgSeed), typeAlpha);
      }
      if (dataset.fill || type !== 'line') {
        changes.push(`dataset${idx}: Apply fade fill to avoid occlusion`);
      }
    } else if (!dataset.backgroundColor) {
      dataset.backgroundColor = ensureAlpha(liftedBase, 0.85);
    } else if (bgIsArray) {
      dataset.backgroundColor = backgroundInput.map(col => liftDarkColor(col));
    } else if (!bgIsArray) {
      dataset.backgroundColor = liftDarkColor(dataset.backgroundColor);
    }

    if (type === 'line' && !dataset.pointBackgroundColor) {
      dataset.pointBackgroundColor = Array.isArray(dataset.borderColor)
        ? dataset.borderColor[0]
        : dataset.borderColor;
    }
  });

  if (changes.length) {
    payload._colorAudit = changes;
  }
  return changes;
}

function getThemePalette() {
  const styles = getComputedStyle(document.body);
  return {
    text: styles.getPropertyValue('--text-color').trim(),
    grid: styles.getPropertyValue('--border-color').trim()
  };
}

function applyChartTheme(chart) {
  if (!chart) return;
  try {
    chart.update('none');
  } catch (err) {
    console.error('Chart refresh failed', err);
  }
}

function isPlainObject(value) {
  return Object.prototype.toString.call(value) === '[object Object]';
}

function cloneDeep(value) {
  if (Array.isArray(value)) {
    return value.map(cloneDeep);
  }
  if (isPlainObject(value)) {
    const obj = {};
    Object.keys(value).forEach(key => {
      obj[key] = cloneDeep(value[key]);
    });
    return obj;
  }
  return value;
}

function mergeOptions(base, override) {
  const result = isPlainObject(base) ? cloneDeep(base) : {};
  if (!isPlainObject(override)) {
    return result;
  }
  Object.keys(override).forEach(key => {
    const overrideValue = override[key];
    if (Array.isArray(overrideValue)) {
      result[key] = cloneDeep(overrideValue);
    } else if (isPlainObject(overrideValue)) {
      result[key] = mergeOptions(result[key], overrideValue);
    } else {
      result[key] = overrideValue;
    }
  });
  return result;
}

function resolveChartTypes(payload) {
  const explicit = payload && payload.props && payload.props.type;
  const widgetType = payload && payload.widgetType ? payload.widgetType : 'chart.js/bar';
  const derived = widgetType && widgetType.includes('/') ? widgetType.split('/').pop() : widgetType;
  const extra = Array.isArray(payload && payload.preferredTypes) ? payload.preferredTypes : [];
  const pipeline = [explicit, derived, ...extra, ...STABLE_CHART_TYPES].filter(Boolean);
  const result = [];
  pipeline.forEach(type => {
    if (type && !result.includes(type)) {
      result.push(type);
    }
  });
  return result.length ? result : ['bar'];
}

function describeChartType(type) {
  return CHART_TYPE_LABELS[type] || type || 'chart';
}

function setChartDegradeNote(card, fromType, toType) {
  if (!card) return;
  card.setAttribute('data-chart-state', 'degraded');
  let note = card.querySelector('.chart-note');
  if (!note) {
    note = document.createElement('p');
    note.className = 'chart-note';
    card.appendChild(note);
  }
  note.textContent = `${describeChartType(fromType)}Rendering Failed, has automatically switched to${describeChartType(toType)}to ensure compatibility。`;
}

function clearChartDegradeNote(card) {
  if (!card) return;
  card.removeAttribute('data-chart-state');
  const note = card.querySelector('.chart-note');
  if (note) {
    note.remove();
  }
}

function isWordCloudWidget(payload) {
  const type = payload && payload.widgetType;
  return typeof type === 'string' && type.toLowerCase().includes('wordcloud');
}

function hashString(str) {
  let h = 0;
  if (!str) return h;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return h;
}

function normalizeWordcloudItems(payload) {
  const sources = [];
  const props = payload && payload.props;
  const dataField = payload && payload.data;
  if (props) {
    ['data', 'items', 'words', 'sourceData'].forEach(key => {
      if (props[key]) sources.push(props[key]);
    });
  }
  if (dataField) {
    sources.push(dataField);
  }

  const seen = new Map();
  const pushItem = (word, weight, category) => {
    if (!word) return;
    let numeric = 1;
    if (typeof weight === 'number' && Number.isFinite(weight)) {
      numeric = weight;
    } else if (typeof weight === 'string') {
      const parsed = parseFloat(weight);
      numeric = Number.isFinite(parsed) ? parsed : 1;
    }
    if (!(numeric > 0)) numeric = 1;
    const cat = (category || '').toString().toLowerCase();
    const key = `${word}__${cat}`;
    const existing = seen.get(key);
    const payloadItem = { word: String(word), weight: numeric, category: cat };
    if (!existing || numeric > existing.weight) {
      seen.set(key, payloadItem);
    }
  };

  const consume = (raw) => {
    if (!raw) return;
    if (Array.isArray(raw)) {
      raw.forEach(item => {
        if (!item) return;
        if (Array.isArray(item)) {
          pushItem(item[0], item[1], item[2]);
        } else if (typeof item === 'object') {
          pushItem(item.word || item.text || item.label, item.weight, item.category);
        } else if (typeof item === 'string') {
          pushItem(item, 1, '');
        }
      });
    } else if (typeof raw === 'object') {
      Object.entries(raw).forEach(([word, weight]) => pushItem(word, weight, ''));
    }
  };

  sources.forEach(consume);

  const items = Array.from(seen.values());
  items.sort((a, b) => (b.weight || 0) - (a.weight || 0));
  return items.slice(0, 150);
}

function wordcloudColor(category) {
  const key = typeof category === 'string' ? category.toLowerCase() : '';
  const palette = resolveWordcloudTheme();
  const base = WORDCLOUD_CATEGORY_COLORS[key] || palette.accent || palette.secondary || '#334155';
  return liftDarkColor(base);
}

function renderWordCloudDegrade(canvas, items, reason) {
  // The display form when the word cloud Failed: hide the canvas, display the badge list (word+weight), ensuring "visible data" rather than blank
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  if (!card) return;
  const wrapper = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (wrapper) {
    wrapper.style.display = 'none';
  } else {
    canvas.style.display = 'none';
  }
  let degrade = card.querySelector('.chart-degrade[data-dynamic="true"]');
  if (!degrade) {
    degrade = card.querySelector('.chart-degrade');
  }
  if (!degrade) {
    degrade = document.createElement('div');
    card.appendChild(degrade);
  }
  degrade.className = 'chart-degrade wordcloud-degrade';
  degrade.setAttribute('data-dynamic', 'true');
  degrade.style.display = 'block';
  degrade.textContent = '';
  card.setAttribute('data-chart-state', 'degrade');
  const buildBadge = (item, maxWeight) => {
    const badge = document.createElement('span');
    badge.className = 'wordcloud-badge';
    const clampedWeight = Math.max(0.5, (item.weight || 1));
    const normalized = Math.min(1, clampedWeight / (maxWeight || 1));
    const fontSize = 0.85 + normalized * 0.9;
    badge.style.fontSize = `${fontSize}rem`;
    badge.style.background = `linear-gradient(135deg, ${lightenColor(wordcloudColor(item.category), 0.05)} 0%, ${lightenColor(wordcloudColor(item.category), 0.15)} 100%)`;
    badge.style.borderColor = lightenColor(wordcloudColor(item.category), 0.25);
    badge.textContent = item.word;
    if (item.weight !== undefined && item.weight !== null) {
      const meta = document.createElement('small');
      meta.textContent = item.weight >= 0 && item.weight <= 1.5
        ? `${(item.weight * 100).toFixed(0)}%`
        : item.weight.toFixed(1).replace(/\.0+$/, '').replace(/0+$/, '').replace(/\.$/, '');
      badge.appendChild(meta);
    }
    return badge;
  };

  if (reason) {
    const notice = document.createElement('p');
    notice.className = 'chart-degrade__notice';
    notice.textContent = `Word cloud failed to render${reason ? `（${reason}）` : ''}，Displayed keyword list。`;
    degrade.appendChild(notice);
  }
  if (!items || !items.length) {
    const empty = document.createElement('p');
    empty.textContent = 'No data available yet。';
    degrade.appendChild(empty);
    return;
  }
  const badges = document.createElement('div');
  badges.className = 'wordcloud-badges';
  const maxWeight = items.reduce((max, item) => Math.max(max, item.weight || 0), 1);
  items.forEach(item => {
    badges.appendChild(buildBadge(item, maxWeight));
  });
  degrade.appendChild(badges);
}

function renderWordCloud(canvas, payload, skipRegistry) {
  const items = normalizeWordcloudItems(payload);
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  const container = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (!items.length) {
    renderWordCloudDegrade(canvas, items, 'No valid data');
    return;
  }
  if (typeof WordCloud === 'undefined') {
    renderWordCloudDegrade(canvas, items, 'Word cloud dependency not loaded');
    return;
  }
  const theme = resolveWordcloudTheme();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(260, (container ? container.clientWidth : canvas.clientWidth || canvas.width || 320));
  const height = Math.max(120, Math.round(width / 5)); // 5:1 aspect ratio
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  canvas.style.backgroundColor = 'transparent';

  const resolveBgColor = () => {
    const cardEl = card || container || document.body;
    const style = getComputedStyle(cardEl);
    const tokens = ['--card-bg', '--panel-bg', '--paper-bg', '--bg', '--background', '--page-bg'];
    for (const key of tokens) {
      const val = style.getPropertyValue(key);
      if (val && val.trim() && val.trim() !== 'transparent') return val.trim();
    }
    if (style.backgroundColor && style.backgroundColor !== 'rgba(0, 0, 0, 0)') return style.backgroundColor;
    const bodyStyle = getComputedStyle(document.body);
    for (const key of tokens) {
      const val = bodyStyle.getPropertyValue(key);
      if (val && val.trim() && val.trim() !== 'transparent') return val.trim();
    }
    if (bodyStyle.backgroundColor && bodyStyle.backgroundColor !== 'rgba(0, 0, 0, 0)') {
      return bodyStyle.backgroundColor;
    }
    return 'transparent';
  };
  const bgColor = resolveBgColor() || theme.cardBg || 'transparent';

  const maxWeight = items.reduce((max, item) => Math.max(max, item.weight || 0), 0) || 1;
  const weightLookup = new Map();
  const categoryLookup = new Map();
  items.forEach(it => {
    weightLookup.set(it.word, it.weight || 1);
    categoryLookup.set(it.word, it.category || '');
  });
  const list = items.map(item => [item.word, item.weight && item.weight > 0 ? item.weight : 1]);
  try {
    WordCloud(canvas, {
      list,
      gridSize: Math.max(3, Math.floor(Math.sqrt(canvas.width * canvas.height) / 170)),
      weightFactor: (val) => {
        const normalized = Math.max(0, val) / maxWeight;
        const cap = Math.min(width, height);
        const base = Math.max(9, cap / 5.5);
        const size = base * (0.8 + normalized * 1.3);
        return size * dpr;
      },
      color: (word) => {
        const w = weightLookup.get(word) || 1;
        const ratio = Math.max(0, Math.min(1, w / (maxWeight || 1)));
        const category = categoryLookup.get(word) || '';
        const base = wordcloudColor(category);
        const target = theme.isDark ? '#ffffff' : (theme.text || '#111827');
        const mixAmount = theme.isDark
          ? 0.28 + (1 - ratio) * 0.22
          : 0.12 + (1 - ratio) * 0.35;
        const mixed = mixColors(base, target, mixAmount);
        return ensureAlpha(mixed || base, theme.isDark ? 0.95 : 1);
      },
      rotateRatio: 0,
      rotationSteps: 0,
      shuffle: false,
      shrinkToFit: true,
      drawOutOfBound: false,
      shape: 'square',
      ellipticity: 0.45,
      clearCanvas: true,
      backgroundColor: bgColor
    });
    if (container) {
      container.style.display = '';
      container.style.minHeight = `${height}px`;
      container.style.background = 'transparent';
    }
    const degrade = card && card.querySelector('.chart-degrade');
    if (degrade) {
      degrade.style.display = 'none';
    }
    card && card.removeAttribute('data-chart-state');
    if (!skipRegistry) {
      wordCloudRegistry.set(canvas, () => renderWordCloud(canvas, payload, true));
    }
  } catch (err) {
    console.error('WordCloud renderingFailed', err);
    renderWordCloudDegrade(canvas, items, err && err.message ? err.message : '');
  }
}

function createDegradeTable(labels, datasets) {
  if (!Array.isArray(datasets) || !datasets.length) {
    return null;
  }
  const primaryDataset = datasets.find(ds => Array.isArray(ds && ds.data));
  const resolvedLabels = Array.isArray(labels) && labels.length
    ? labels
    : (primaryDataset && primaryDataset.data ? primaryDataset.data.map((_, idx) => `data points ${idx + 1}`) : []);
  if (!resolvedLabels.length) {
    return null;
  }
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  const categoryHeader = document.createElement('th');
  categoryHeader.textContent = 'category';
  headRow.appendChild(categoryHeader);
  datasets.forEach((dataset, index) => {
    const th = document.createElement('th');
    th.textContent = dataset && dataset.label ? dataset.label : `series${index + 1}`;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  resolvedLabels.forEach((label, rowIdx) => {
    const row = document.createElement('tr');
    const labelCell = document.createElement('td');
    labelCell.textContent = label;
    row.appendChild(labelCell);
    datasets.forEach(dataset => {
      const cell = document.createElement('td');
      const series = dataset && Array.isArray(dataset.data) ? dataset.data[rowIdx] : undefined;
      if (typeof series === 'number') {
        cell.textContent = series.toLocaleString();
      } else if (series !== undefined && series !== null && series !== '') {
        cell.textContent = series;
      } else {
        cell.textContent = '—';
      }
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  return table;
}

function renderChartDegrade(canvas, payload, reason) {
  // Display form when chart Failed: switch to tabular data (categories x series), and mark the degrade state on the card
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  if (!card) return;
  clearChartDegradeNote(card);
  const wrapper = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (wrapper) {
    wrapper.style.display = 'none';
  } else {
    canvas.style.display = 'none';
  }
  let degrade = card.querySelector('.chart-degrade[data-dynamic="true"]');
  let prebuilt = false;
  if (!degrade) {
    degrade = card.querySelector('.chart-degrade');
    if (degrade) {
      prebuilt = degrade.hasAttribute('data-prebuilt');
    }
  }
  if (!degrade) {
    degrade = document.createElement('div');
    degrade.className = 'chart-degrade';
    degrade.setAttribute('data-dynamic', 'true');
    card.appendChild(degrade);
  } else if (!prebuilt) {
    degrade.textContent = '';
  }
  const titleFromOptions = payload && payload.props && payload.props.options &&
    payload.props.options.plugins && payload.props.options.plugins.title &&
    payload.props.options.plugins.title.text;
  const degradeTitle = titleFromOptions ||
    (payload && payload.props && payload.props.title) ||
    (payload && payload.widgetId) ||
    canvas.getAttribute('id') ||
    'chart';
  const existingNotice = degrade.querySelector('.chart-degrade__notice');
  if (existingNotice) {
    existingNotice.remove();
  }
  const notice = document.createElement('p');
  notice.className = 'chart-degrade__notice';
  notice.textContent = `${degradeTitle}：Chart failed to render, tabular data has been displayed${reason ? `（${reason}）` : ''}`;
  degrade.insertBefore(notice, degrade.firstChild || null);
  if (!prebuilt) {
    const table = createDegradeTable(
      payload && payload.data && payload.data.labels,
      payload && payload.data && payload.data.datasets
    );
    if (table) {
      degrade.appendChild(table);
    }
  }
  degrade.style.display = 'block';
  card.setAttribute('data-chart-state', 'degrade');
}

function buildChartOptions(payload) {
  const rawLegend = payload && payload.props ? payload.props.legend : undefined;
  let legendConfig;
  if (isPlainObject(rawLegend)) {
    legendConfig = mergeOptions({
      display: rawLegend.display !== false,
      position: rawLegend.position || 'top'
    }, rawLegend);
  } else {
    legendConfig = {
      display: rawLegend === 'hidden' ? false : true,
      position: typeof rawLegend === 'string' ? rawLegend : 'top'
    };
  }
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: legendConfig
    }
  };
  if (payload && payload.props && payload.props.title) {
    baseOptions.plugins.title = {
      display: true,
      text: payload.props.title
    };
  }
  const overrideOptions = payload && payload.props && payload.props.options;
  return mergeOptions(baseOptions, overrideOptions);
}

function validateChartData(payload, type) {
  /**
   * Front-end validation chart data
   * return: { valid: boolean, errors: string[] }
   */
  const errors = [];

  if (!payload || typeof payload !== 'object') {
    errors.push('Invalidpayload');
    return { valid: false, errors };
  }

  const data = payload.data;
  if (!data || typeof data !== 'object') {
    errors.push('missing data field');
    return { valid: false, errors };
  }

  // Special chart types（scatter, bubble）
  const specialTypes = { 'scatter': true, 'bubble': true };
  if (specialTypes[type]) {
    // These types require special data formats {x, y} or {x, y, r}
    // Skip standard validation
    return { valid: true, errors };
  }

  // Standard chart type validation
  const datasets = data.datasets;
  if (!Array.isArray(datasets)) {
    errors.push('datasetsMust be an array');
    return { valid: false, errors };
  }

  if (datasets.length === 0) {
    errors.push('datasetsArray is empty');
    return { valid: false, errors };
  }

  // Verify eachdataset
  for (let i = 0; i < datasets.length; i++) {
    const dataset = datasets[i];
    if (!dataset || typeof dataset !== 'object') {
      errors.push(`datasets[${i}]Not an object`);
      continue;
    }

    if (!Array.isArray(dataset.data)) {
      errors.push(`datasets[${i}].datanot an array`);
    } else if (dataset.data.length === 0) {
      errors.push(`datasets[${i}].datais empty`);
    }
  }

  // Chart type that requires labels
  const labelRequiredTypes = {
    'line': true, 'bar': true, 'radar': true,
    'polarArea': true, 'pie': true, 'doughnut': true
  };

  if (labelRequiredTypes[type]) {
    const labels = data.labels;
    if (!Array.isArray(labels)) {
      errors.push('labels array missing');
    } else if (labels.length === 0) {
      errors.push('labelsArray is empty');
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

function instantiateChart(ctx, payload, optionsTemplate, type) {
  if (!ctx) {
    return null;
  }
  if (ctx.canvas && typeof Chart !== 'undefined' && typeof Chart.getChart === 'function') {
    const existing = Chart.getChart(ctx.canvas);
    if (existing) {
      existing.destroy();
    }
  }
  const data = cloneDeep(payload && payload.data ? payload.data : {});
  const config = {
    type,
    data,
    options: cloneDeep(optionsTemplate)
  };
  return new Chart(ctx, config);
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(null, args), wait || 200);
  };
}

function hydrateCharts() {
  document.querySelectorAll('canvas[data-config-id]').forEach(canvas => {
    const configScript = document.getElementById(canvas.dataset.configId);
    if (!configScript) return;
    let payload;
    try {
      payload = JSON.parse(configScript.textContent);
    } catch (err) {
      console.error('Widget JSON parseFailed', err);
      renderChartDegrade(canvas, { widgetId: canvas.dataset.configId }, 'Configuration analysisFailed');
      return;
    }
    if (isWordCloudWidget(payload)) {
      renderWordCloud(canvas, payload);
      return;
    }
    if (typeof Chart === 'undefined') {
      renderChartDegrade(canvas, payload, 'Chart.js not loaded');
      return;
    }
    const chartTypes = resolveChartTypes(payload);
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      renderChartDegrade(canvas, payload, 'Canvas initializationFailed');
      return;
    }

    // Front-end data validation
    const desiredType = chartTypes[0];
    const card = canvas.closest('.chart-card') || canvas.parentElement;
    const colorAdjustments = normalizeDatasetColors(payload, desiredType);
    if (colorAdjustments.length && card) {
      card.setAttribute('data-chart-color-fixes', colorAdjustments.join(' | '));
    }
    const validation = validateChartData(payload, desiredType);
    if (!validation.valid) {
      console.warn('Chart data validationFailed:', validation.errors);
      // Validate Failed but still try to render because of possible degradationSuccess
    }

    const optionsTemplate = buildChartOptions(payload);
    let chartInstance = null;
    let selectedType = null;
    let lastError;
    for (const type of chartTypes) {
      try {
        chartInstance = instantiateChart(ctx, payload, optionsTemplate, type);
        selectedType = type;
        break;
      } catch (err) {
        lastError = err;
        console.error('Chart renderingFailed', type, err);
      }
    }
    if (chartInstance) {
      chartRegistry.push(chartInstance);
      try {
        applyChartTheme(chartInstance);
      } catch (err) {
        console.error('ThemesynchronousFailed', selectedType || desiredType || payload && payload.widgetType || 'chart', err);
      }
      if (selectedType && selectedType !== desiredType) {
        setChartDegradeNote(card, desiredType, selectedType);
      } else {
        clearChartDegradeNote(card);
      }
    } else {
      const reason = lastError && lastError.message ? lastError.message : '';
      renderChartDegrade(canvas, payload, reason);
    }
  });
}

function getExportOverlayParts() {
  const overlay = document.getElementById('export-overlay');
  if (!overlay) {
    return null;
  }
  return {
    overlay,
    status: overlay.querySelector('.export-status')
  };
}

function showExportOverlay(message) {
  const parts = getExportOverlayParts();
  if (!parts) return;
  if (message && parts.status) {
    parts.status.textContent = message;
  }
  parts.overlay.classList.add('active');
  document.body.classList.add('exporting');
}

function updateExportOverlay(message) {
  if (!message) return;
  const parts = getExportOverlayParts();
  if (parts && parts.status) {
    parts.status.textContent = message;
  }
}

function hideExportOverlay(delay) {
  const parts = getExportOverlayParts();
  if (!parts) return;
  const close = () => {
    parts.overlay.classList.remove('active');
    document.body.classList.remove('exporting');
  };
  if (delay && delay > 0) {
    setTimeout(close, delay);
  } else {
    close();
  }
}

// exportPdfRemoved
function exportPdf() {
  // Export button interaction: disable button+To open the mask, use html2canvas + jsPDF Render main, then restore buttons and masks
  const target = document.querySelector('main');
  if (!target || typeof jspdf === 'undefined' || typeof jspdf.jsPDF !== 'function') {
    alert('PDFExport dependencies are not ready');
    return;
  }
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.disabled = true;
  }
  showExportOverlay('Exporting PDF, please wait....');
  document.body.classList.add('exporting');
  const pdf = new jspdf.jsPDF('p', 'mm', 'a4');
  try {
    if (window.pdfFontData) {
      pdf.addFileToVFS('SourceHanSerifSC-Medium.ttf', window.pdfFontData);
      pdf.addFont('SourceHanSerifSC-Medium.ttf', 'SourceHanSerif', 'normal');
      pdf.setFont('SourceHanSerif');
      console.log('PDFFont has been successfully loaded');
    } else {
      console.warn('PDFFont data not found, default font will be used');
    }
  } catch (err) {
    console.warn('Custom PDF font setup failed, degrade to default', err);
  }
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pxWidth = Math.max(
    target.scrollWidth,
    document.documentElement.scrollWidth,
    Math.round(pageWidth * 3.78)
  );
  const restoreButton = () => {
    if (exportBtn) {
      exportBtn.disabled = false;
    }
    document.body.classList.remove('exporting');
  };
  let renderTask;
  try {
    // force charts to rerender at full width before capture
    chartRegistry.forEach(chart => {
      if (chart && typeof chart.resize === 'function') {
        chart.resize();
      }
    });
    wordCloudRegistry.forEach(fn => {
      if (typeof fn === 'function') {
        try {
          fn();
        } catch (err) {
          console.error('word cloud re-renderingFailed', err);
        }
      }
    });
    renderTask = pdf.html(target, {
      x: 8,
      y: 12,
      width: pageWidth - 16,
      margin: [12, 12, 20, 12],
      autoPaging: 'text',
      windowWidth: pxWidth,
      html2canvas: {
        scale: Math.min(1.5, Math.max(1.0, pageWidth / (target.clientWidth || pageWidth))),
        useCORS: true,
        scrollX: 0,
        scrollY: -window.scrollY,
        logging: false,
        allowTaint: true,
        backgroundColor: '#ffffff'
      },
      pagebreak: {
        mode: ['css', 'legacy'],
        avoid: [
          '.chapter > *',
          '.callout',
          '.chart-card',
          '.table-wrap',
          '.kpi-grid',
          '.hero-section'
        ],
        before: '.chapter-divider'
      },
      callback: (doc) => doc.save('report.pdf')
    });
  } catch (err) {
    console.error('PDF ExportFailed', err);
    updateExportOverlay('Export Failed, please waitRetry');
    hideExportOverlay(1200);
    restoreButton();
    alert('PDFExport Failed, please waitRetry');
    return;
  }
  if (renderTask && typeof renderTask.then === 'function') {
    renderTask.then(() => {
      updateExportOverlay('ExportCompleted, saving...');
      hideExportOverlay(800);
      restoreButton();
    }).catch(err => {
      console.error('PDF ExportFailed', err);
      updateExportOverlay('Export Failed, please waitRetry');
      hideExportOverlay(1200);
      restoreButton();
      alert('PDFExport Failed, please waitRetry');
    });
  } else {
    hideExportOverlay();
    restoreButton();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const rerenderWordclouds = debounce(() => {
    wordCloudRegistry.forEach(fn => {
      if (typeof fn === 'function') {
        fn();
      }
    });
  }, 260);
  // Legacy Web Component Theme button (annotated）
  // const themeBtn = document.getElementById('theme-toggle');
  // if (themeBtn) {
  //   themeBtn.addEventListener('change', (e) => {
  //     if (e.detail === 'dark') {
  //       document.body.classList.add('dark-mode');
  //     } else {
  //       document.body.classList.remove('dark-mode');
  //     }
  //     chartRegistry.forEach(applyChartTheme);
  //     rerenderWordclouds();
  //   });
  // }

  // New version of action-btn style Theme button
  const themeBtnNew = document.getElementById('theme-toggle-btn');
  if (themeBtnNew) {
    const sunIcon = themeBtnNew.querySelector('.sun-icon');
    const moonIcon = themeBtnNew.querySelector('.moon-icon');
    let isDark = document.body.classList.contains('dark-mode');

    const updateThemeUI = () => {
      if (isDark) {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
      } else {
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
      }
    };
    updateThemeUI();

    themeBtnNew.addEventListener('click', () => {
      isDark = !isDark;
      if (isDark) {
        document.body.classList.add('dark-mode');
      } else {
        document.body.classList.remove('dark-mode');
      }
      updateThemeUI();
      chartRegistry.forEach(applyChartTheme);
      rerenderWordclouds();
    });
  }
  const printBtn = document.getElementById('print-btn');
  if (printBtn) {
    // Print button: directly call the browser to print, depending on @media print Control layout
    printBtn.addEventListener('click', () => window.print());
  }
  // Add mouse tracking halo effect to All action-btn
  document.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('mousemove', (e) => {
      const rect = btn.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      btn.style.setProperty('--mouse-x', x + '%');
      btn.style.setProperty('--mouse-y', y + '%');
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.setProperty('--mouse-x', '50%');
      btn.style.setProperty('--mouse-y', '50%');
    });
  });
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    // Export button: call exportPdf（html2canvas + jsPDF），and drive the mask/progress prompt
    exportBtn.addEventListener('click', exportPdf);
  }
  window.addEventListener('resize', rerenderWordclouds);
  hydrateCharts();
});
