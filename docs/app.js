// =============================================================
// IKS 価格高騰トラッカー - ダッシュボードロジック
// =============================================================

const STATE = {
  rangeStart: '2000-01',
  rangeEnd: null,
  metals: null,
  sppi: null,
  wage: null,
  charts: {},
  filters: {
    metals: new Set(['aluminum', 'copper', 'nickel', 'iron_ore']),
    wage: new Set(['tochigi', 'gunma', 'ibaraki', 'tokyo', 'nationwide']),
  },
};

const COLORS = {
  aluminum:   '#6c7a89',
  copper:     '#c8702e',
  nickel:     '#2c8a7a',
  lead:       '#55607c',
  tin:        '#b7a57a',
  zinc:       '#8a9c9e',
  iron_ore:   '#8b3a2e',
  tochigi:    '#c8102e',
  gunma:      '#2c5aa0',
  ibaraki:    '#d4a017',
  saitama:    '#5a7d2a',
  tokyo:      '#1a1a1a',
  aichi:      '#8e24aa',
  osaka:      '#f57c00',
  nationwide: '#777777',
  sppi_total: '#2c5aa0',
  road_freight: '#c8102e',
};

const LABELS = {
  aluminum: 'アルミ', copper: '銅', nickel: 'ニッケル',
  lead: '鉛', tin: '錫', zinc: '亜鉛', iron_ore: '鉄鉱石',
  tochigi: '栃木', gunma: '群馬', ibaraki: '茨城',
  saitama: '埼玉', tokyo: '東京', aichi: '愛知',
  osaka: '大阪', nationwide: '全国加重平均',
  sppi_total: 'SPPI総平均', road_freight: '道路貨物輸送',
};

const UNITS = {
  aluminum: '円/kg', copper: '円/kg', nickel: '円/kg',
  lead: '円/kg', tin: '円/kg', zinc: '円/kg',
  iron_ore: 'USD/dmtu',
  tochigi: '円/時', gunma: '円/時', ibaraki: '円/時',
  saitama: '円/時', tokyo: '円/時', aichi: '円/時',
  osaka: '円/時', nationwide: '円/時',
  sppi_total: '指数(2020=100)', road_freight: '指数(2020=100)',
};

// -------------------------------------------------------------
// Data loading
// -------------------------------------------------------------
async function loadCSV(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}`);
  const text = await r.text();
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',');
  return lines.slice(1).map(line => {
    const vals = line.split(',');
    const obj = {};
    headers.forEach((h, i) => {
      const v = (vals[i] || '').trim();
      if (h === 'date' || h === 'year') {
        obj[h] = v;
      } else {
        obj[h] = v === '' ? NaN : isNaN(parseFloat(v)) ? v : parseFloat(v);
      }
    });
    return obj;
  });
}

async function loadManifest() {
  try {
    const r = await fetch('data/manifest.json');
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

async function loadAll() {
  const [metals, sppi, wage, manifest] = await Promise.all([
    loadCSV('data/metals.csv'),
    loadCSV('data/sppi.csv'),
    loadCSV('data/min_wage.csv'),
    loadManifest(),
  ]);
  STATE.metals = metals;
  STATE.sppi = sppi;
  STATE.wage = wage;
  if (manifest) {
    document.getElementById('last-updated').textContent =
      `最終更新: ${manifest.generated_at}`;
  }
}

// -------------------------------------------------------------
// Utility
// -------------------------------------------------------------
function filterRange(rows, dateKey = 'date') {
  const startStr = STATE.rangeStart || '2000-01';
  const endStr = STATE.rangeEnd || getCurrentMonth();

  if (dateKey === 'year') {
    const startYear = parseInt(startStr.substring(0, 4));
    const endYear = parseInt(endStr.substring(0, 4));
    return rows.filter(r => parseInt(r.year) >= startYear && parseInt(r.year) <= endYear);
  }

  const startDate = new Date(startStr + '-01');
  const endDate = new Date(endStr + '-28');
  return rows.filter(r => {
    const d = new Date(r[dateKey]);
    return d >= startDate && d <= endDate;
  });
}

function getCurrentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// -------------------------------------------------------------
// 線形回帰 (直近5年のデータを使用)
// -------------------------------------------------------------
function linearRegression(values) {
  // values: array of numbers (NaN/null excluded by caller)
  const n = values.length;
  if (n < 2) return { slope: 0, intercept: values[0] || 0 };
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumXX += i * i;
  }
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function forecast(rows, key, dateKey, forecastMonths) {
  // Use last 5 years of data for regression
  const valid = rows.filter(r => !isNaN(r[key]) && r[key] !== null);
  const recentCount = dateKey === 'year' ? 5 : 60; // 5 years or 60 months
  const recent = valid.slice(-recentCount);
  if (recent.length < 3) return { labels: [], values: [] };

  const vals = recent.map(r => r[key]);
  const reg = linearRegression(vals);

  // R² to assess fit quality
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  let ssTot = 0, ssRes = 0;
  vals.forEach((v, i) => {
    const predicted = reg.intercept + reg.slope * i;
    ssTot += (v - mean) ** 2;
    ssRes += (v - predicted) ** 2;
  });
  const r2 = ssTot === 0 ? 0 : 1 - ssRes / ssTot;

  // Generate forecast points
  const lastIdx = recent.length - 1;
  const steps = dateKey === 'year' ? 3 : forecastMonths;
  const labels = [];
  const values = [];

  // Start from the last actual data point for continuity
  const lastRow = valid[valid.length - 1];
  if (dateKey === 'year') {
    const lastYear = parseInt(lastRow.year);
    // Include last actual point as bridge
    labels.push(String(lastYear));
    values.push(lastRow[key]);
    for (let i = 1; i <= steps; i++) {
      labels.push(String(lastYear + i));
      const predicted = reg.intercept + reg.slope * (lastIdx + i);
      values.push(Math.max(0, Math.round(predicted * 10) / 10));
    }
  } else {
    const lastDate = new Date(lastRow.date + 'T00:00:00');
    // Include last actual point as bridge
    labels.push(new Date(lastDate));
    values.push(lastRow[key]);
    for (let i = 1; i <= steps; i++) {
      const d = new Date(lastDate);
      d.setMonth(d.getMonth() + i);
      labels.push(d);
      const predicted = reg.intercept + reg.slope * (lastIdx + i);
      values.push(Math.max(0, Math.round(predicted * 100) / 100));
    }
  }

  return { labels, values, r2 };
}

// -------------------------------------------------------------
// Chart builder
// -------------------------------------------------------------
function buildLineChart(canvasId, rows, keys, dateKey = 'date') {
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (STATE.charts[canvasId]) STATE.charts[canvasId].destroy();

  const filtered = filterRange(rows, dateKey);
  const isYearOnly = dateKey === 'year';

  // Build labels for actual data
  const labels = filtered.map(r => {
    if (isYearOnly) return String(r[dateKey]);
    return new Date(r[dateKey] + 'T00:00:00');
  });

  // Actual data datasets
  const datasets = keys.map(k => {
    const data = filtered.map(r => r[k] == null || isNaN(r[k]) ? null : r[k]);
    return {
      label: LABELS[k] || k,
      data,
      borderColor: COLORS[k] || '#999',
      backgroundColor: COLORS[k] || '#999',
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      spanGaps: true,
    };
  });

  // Forecast datasets (3 years = 36 months)
  const forecastMonths = 36;
  const forecastLabels = [];

  keys.forEach(k => {
    const fc = forecast(rows, k, dateKey, forecastMonths);
    if (fc.labels.length === 0) return;

    // Collect forecast labels to extend the chart axis
    fc.labels.forEach(l => {
      if (!forecastLabels.find(fl => String(fl) === String(l))) {
        forecastLabels.push(l);
      }
    });

    // Build forecast data array aligned to full label set
    // We'll set actual-period values to null so only forecast segment shows
    const forecastData = new Array(labels.length).fill(null);

    // Map forecast labels to their indices in extended label set
    const fcMap = {};
    fc.labels.forEach((l, i) => fcMap[String(l)] = fc.values[i]);

    datasets.push({
      label: `${LABELS[k]} 予測`,
      data: forecastData, // placeholder, will be rebuilt after label merge
      borderColor: COLORS[k] || '#999',
      backgroundColor: 'transparent',
      borderWidth: 2,
      borderDash: [8, 4],
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      spanGaps: true,
      _forecastMap: fcMap, // temporary, used below
    });
  });

  // Merge forecast labels into main labels
  const allLabels = [...labels];
  forecastLabels.forEach(fl => {
    if (!allLabels.find(l => String(l) === String(fl))) {
      allLabels.push(fl);
    }
  });

  // Sort labels
  if (isYearOnly) {
    allLabels.sort((a, b) => parseInt(a) - parseInt(b));
  } else {
    allLabels.sort((a, b) => new Date(a) - new Date(b));
  }

  // Re-align all dataset data to merged labels
  datasets.forEach(ds => {
    if (ds._forecastMap) {
      // Forecast dataset
      ds.data = allLabels.map(l => {
        const v = ds._forecastMap[String(l)];
        return v !== undefined ? v : null;
      });
      delete ds._forecastMap;
    } else {
      // Actual dataset: pad with nulls for forecast period
      const origData = ds.data;
      ds.data = allLabels.map((l, i) => {
        // Find matching index in original labels
        const origIdx = labels.findIndex(ol => String(ol) === String(l));
        return origIdx >= 0 ? origData[origIdx] : null;
      });
    }
  });

  // Determine appropriate time unit
  const spanMonths = allLabels.length;
  let timeUnit = 'year';
  if (spanMonths <= 18) timeUnit = 'month';
  else if (spanMonths <= 48) timeUnit = 'quarter';

  const xScale = isYearOnly ? {
    type: 'category',
    ticks: {
      callback: function(value) {
        return this.getLabelForValue(value) + '年';
      },
      maxTicksLimit: 15,
      autoSkip: true,
    },
    grid: { display: false },
  } : {
    type: 'time',
    time: {
      unit: timeUnit,
      displayFormats: {
        month: 'yyyy/MM',
        quarter: 'yyyy/MM',
        year: 'yyyy',
      },
      tooltipFormat: 'yyyy年MM月',
    },
    ticks: {
      maxTicksLimit: 15,
      autoSkip: true,
      font: { size: 11 },
    },
    grid: { display: false },
  };

  STATE.charts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: { labels: allLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { size: 12 },
            usePointStyle: true,
            pointStyle: 'line',
            filter: item => !item.text.includes('予測'),
          },
        },
        tooltip: {
          callbacks: {
            title: items => {
              if (isYearOnly) return items[0].label + '年';
              return items[0].label;
            },
            label: item => {
              const v = item.parsed.y;
              if (v == null) return null;
              const dsLabel = item.dataset.label;
              const isForecast = dsLabel.includes('予測');
              const fmt = v.toLocaleString('ja-JP', { maximumFractionDigits: 2 });
              // Find unit from the base key
              const baseLabel = dsLabel.replace(' 予測', '');
              const unitKey = Object.entries(LABELS).find(([, l]) => l === baseLabel)?.[0];
              const unit = UNITS[unitKey] || '';
              return `${dsLabel}: ${fmt} ${unit}${isForecast ? ' (推定)' : ''}`;
            },
          },
        },
      },
      scales: {
        x: xScale,
        y: {
          beginAtZero: false,
          grid: { color: 'rgba(0,0,0,0.06)' },
          ticks: { font: { size: 11 } },
        },
      },
    },
  });
}

// -------------------------------------------------------------
// Tab renderers
// -------------------------------------------------------------
function renderMetals() {
  const keys = [...STATE.filters.metals];
  buildLineChart('chart-metals', STATE.metals, keys);
  renderCards('metals-cards', STATE.metals, ['aluminum','copper','nickel','iron_ore']);
  renderMetalFilter();
}

function renderDifficult() {
  const keys = ['nickel', 'tin', 'zinc'];
  buildLineChart('chart-difficult', STATE.metals, keys);
  renderCards('difficult-cards', STATE.metals, keys);
}

function renderWage() {
  const keys = [...STATE.filters.wage];
  buildLineChart('chart-wage', STATE.wage, keys, 'year');
  renderCards('wage-cards', STATE.wage, ['tochigi','tokyo','nationwide'], 'year');
  renderWageFilter();
}

function renderFreight() {
  buildLineChart('chart-freight', STATE.sppi, ['sppi_total', 'road_freight']);
  renderCards('freight-cards', STATE.sppi, ['sppi_total', 'road_freight']);
}

function renderSummary() {
  const container = document.getElementById('summary-table');
  const items = [
    { key: 'aluminum', src: STATE.metals, category: '金属' },
    { key: 'copper',   src: STATE.metals, category: '金属' },
    { key: 'nickel',   src: STATE.metals, category: '金属 / 難削材指標' },
    { key: 'iron_ore', src: STATE.metals, category: '金属' },
    { key: 'tin',      src: STATE.metals, category: '金属' },
    { key: 'zinc',     src: STATE.metals, category: '金属' },
    { key: 'road_freight', src: STATE.sppi, category: '運賃' },
    { key: 'sppi_total',   src: STATE.sppi, category: '運賃' },
    { key: 'tochigi',  src: STATE.wage, category: '最低賃金', dateKey: 'year' },
    { key: 'tokyo',    src: STATE.wage, category: '最低賃金', dateKey: 'year' },
    { key: 'nationwide', src: STATE.wage, category: '最低賃金', dateKey: 'year' },
  ];

  // Add 3-year forecast to summary
  let html = '<table><thead><tr>' +
    '<th>区分</th><th>項目</th><th>2000年</th><th>最新</th><th>上昇率</th><th>3年後予測</th><th>単位</th>' +
    '</tr></thead><tbody>';

  for (const it of items) {
    const rows = it.src.filter(r => !isNaN(r[it.key]));
    if (rows.length < 2) continue;
    const first = rows[0][it.key];
    const last = rows[rows.length - 1][it.key];
    const pct = ((last - first) / first * 100);
    const pctClass = pct >= 0 ? 'change-up' : 'change-down';
    const pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
    const fmt = v => v.toLocaleString('ja-JP', { maximumFractionDigits: 1 });

    // Forecast
    const dk = it.dateKey || 'date';
    const fc = forecast(it.src, it.key, dk, 36);
    const fcLast = fc.values.length > 0 ? fc.values[fc.values.length - 1] : null;
    const fcStr = fcLast != null ? fmt(fcLast) : '-';
    const fcPct = fcLast != null ? ((fcLast - last) / last * 100) : null;
    const fcPctStr = fcPct != null ? `(${fcPct >= 0 ? '+' : ''}${fcPct.toFixed(1)}%)` : '';
    const fcPctClass = fcPct != null ? (fcPct >= 0 ? 'change-up' : 'change-down') : '';

    html += `<tr>
      <td>${it.category}</td>
      <td><strong>${LABELS[it.key]}</strong></td>
      <td class="num">${fmt(first)}</td>
      <td class="num">${fmt(last)}</td>
      <td class="num ${pctClass}">${pctStr}</td>
      <td class="num ${fcPctClass}">${fcStr} ${fcPctStr}</td>
      <td>${UNITS[it.key] || ''}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  html += '<p style="font-size:11px;color:#999;margin-top:12px">※ 3年後予測は直近5年間のデータに基づく線形回帰推定値です。</p>';
  container.innerHTML = html;
}

// -------------------------------------------------------------
// Cards
// -------------------------------------------------------------
function renderCards(containerId, rows, keys, dateKey = 'date') {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  for (const k of keys) {
    const valid = rows.filter(r => !isNaN(r[k]));
    if (!valid.length) continue;
    const first = valid[0][k];
    const last = valid[valid.length - 1][k];
    const pct = ((last - first) / first * 100);
    const cls = pct >= 0 ? 'up' : 'down';
    const sign = pct >= 0 ? '+' : '';
    const fmt = v => v.toLocaleString('ja-JP', { maximumFractionDigits: 1 });
    const unit = UNITS[k] || '';
    const html = `
      <div class="card">
        <div class="card-label">${LABELS[k]}</div>
        <div class="card-value">${fmt(last)} <span style="font-size:12px;font-weight:400;color:var(--ink-2)">${unit}</span></div>
        <div class="card-change ${cls}">${sign}${pct.toFixed(1)}% (2000年比)</div>
      </div>`;
    c.insertAdjacentHTML('beforeend', html);
  }
}

// -------------------------------------------------------------
// Filter chips
// -------------------------------------------------------------
function renderMetalFilter() {
  const all = ['aluminum','copper','nickel','iron_ore','lead','tin','zinc'];
  const c = document.getElementById('metals-filter');
  c.innerHTML = '';
  for (const k of all) {
    const active = STATE.filters.metals.has(k);
    const chip = document.createElement('div');
    chip.className = 'chip' + (active ? ' active' : ' muted');
    chip.style.background = active ? COLORS[k] : 'var(--card)';
    chip.style.borderColor = COLORS[k];
    chip.style.color = active ? 'white' : COLORS[k];
    chip.textContent = LABELS[k];
    chip.onclick = () => {
      if (STATE.filters.metals.has(k)) STATE.filters.metals.delete(k);
      else STATE.filters.metals.add(k);
      renderMetals();
    };
    c.appendChild(chip);
  }
}

function renderWageFilter() {
  const all = ['tochigi','gunma','ibaraki','saitama','tokyo','aichi','osaka','nationwide'];
  const c = document.getElementById('wage-filter');
  c.innerHTML = '';
  for (const k of all) {
    const active = STATE.filters.wage.has(k);
    const chip = document.createElement('div');
    chip.className = 'chip' + (active ? ' active' : ' muted');
    chip.style.background = active ? COLORS[k] : 'var(--card)';
    chip.style.borderColor = COLORS[k];
    chip.style.color = active ? 'white' : COLORS[k];
    chip.textContent = LABELS[k];
    chip.onclick = () => {
      if (STATE.filters.wage.has(k)) STATE.filters.wage.delete(k);
      else STATE.filters.wage.add(k);
      renderWage();
    };
    c.appendChild(chip);
  }
}

// -------------------------------------------------------------
// Tab switching
// -------------------------------------------------------------
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${name}`);
  });
  renderActiveTab();
}

function clearPresetButtons() {
  document.querySelectorAll('.preset-btn').forEach(x => x.classList.remove('active'));
}

function getActiveTab() {
  return document.querySelector('.tab-btn.active').dataset.tab;
}

function renderActiveTab() {
  const t = getActiveTab();
  if (t === 'metals') renderMetals();
  else if (t === 'difficult') renderDifficult();
  else if (t === 'labor') renderWage();
  else if (t === 'freight') renderFreight();
  else if (t === 'summary') renderSummary();
}

// -------------------------------------------------------------
// Init
// -------------------------------------------------------------
async function init() {
  await loadAll();

  document.querySelectorAll('.tab-btn').forEach(b => {
    b.addEventListener('click', () => switchTab(b.dataset.tab));
  });

  // Initialize range pickers
  const rangeEnd = document.getElementById('range-end');
  const rangeStart = document.getElementById('range-start');
  rangeEnd.value = getCurrentMonth();
  rangeEnd.max = getCurrentMonth();
  rangeStart.max = getCurrentMonth();
  STATE.rangeEnd = rangeEnd.value;

  rangeStart.addEventListener('change', (e) => {
    STATE.rangeStart = e.target.value;
    clearPresetButtons();
    renderActiveTab();
  });
  rangeEnd.addEventListener('change', (e) => {
    STATE.rangeEnd = e.target.value;
    clearPresetButtons();
    renderActiveTab();
  });

  // Preset buttons
  document.querySelectorAll('.preset-btn').forEach(b => {
    b.addEventListener('click', () => {
      const preset = b.dataset.preset;
      if (preset === 'all') {
        rangeStart.value = '2000-01';
        rangeEnd.value = getCurrentMonth();
      } else {
        const years = parseInt(preset);
        const now = new Date();
        const start = new Date(now);
        start.setFullYear(start.getFullYear() - years);
        rangeStart.value = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`;
        rangeEnd.value = getCurrentMonth();
      }
      STATE.rangeStart = rangeStart.value;
      STATE.rangeEnd = rangeEnd.value;
      document.querySelectorAll('.preset-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      renderActiveTab();
    });
  });
  document.querySelector('.preset-btn[data-preset="all"]').classList.add('active');

  renderMetals();
}

init().catch(err => {
  console.error(err);
  document.getElementById('last-updated').textContent = 'データ読み込みエラー: ' + err.message;
});
