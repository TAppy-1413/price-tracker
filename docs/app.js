// =============================================================
// IKS コストトレンドモニター - ダッシュボードロジック
// =============================================================

const STATE = {
  rangeStart: '2000-01',
  rangeEnd: null,
  metals: null,
  sppi: null,
  wage: null,
  electricity: null,
  charts: {},
  filters: {
    materials: new Set(['ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052']),
    wage: new Set(['tochigi', 'gunma', 'ibaraki', 'tokyo', 'nationwide']),
  },
  summaryBaseYear: '2000',
  summaryCompareYear: '',  // empty = latest
};

const COLORS = {
  ss400:             '#2c5aa0',
  aluminum_casting:  '#6c7a89',
  iron_casting:      '#8b3a2e',
  sus303:            '#2c8a7a',
  a5052:             '#c8702e',
  tochigi:           '#c8102e',
  gunma:             '#2c5aa0',
  ibaraki:           '#d4a017',
  saitama:           '#5a7d2a',
  tokyo:             '#1a1a1a',
  aichi:             '#8e24aa',
  osaka:             '#f57c00',
  nationwide:        '#777777',
  sppi_total:        '#2c5aa0',
  road_freight:      '#c8102e',
  tepco:             '#ff6600',
  chubu:             '#2c5aa0',
  kansai:            '#c8102e',
  national:          '#333333',
};

const LABELS = {
  ss400: 'SS400', aluminum_casting: 'アルミ鋳物', iron_casting: '鉄鋳物',
  sus303: 'SUS303', a5052: 'A5052',
  tochigi: '栃木', gunma: '群馬', ibaraki: '茨城',
  saitama: '埼玉', tokyo: '東京', aichi: '愛知',
  osaka: '大阪', nationwide: '全国加重平均',
  sppi_total: 'SPPI総平均', road_freight: '道路貨物輸送',
  tepco: '東電管内', chubu: '中部電力', kansai: '関西電力', national: '全国平均',
};

const UNITS = {
  ss400: '円/kg', aluminum_casting: '円/kg', iron_casting: '円/kg',
  sus303: '円/kg', a5052: '円/kg',
  tochigi: '円/時', gunma: '円/時', ibaraki: '円/時',
  saitama: '円/時', tokyo: '円/時', aichi: '円/時',
  osaka: '円/時', nationwide: '円/時',
  sppi_total: '指数(2020=100)', road_freight: '指数(2020=100)',
  tepco: '円/kWh', chubu: '円/kWh', kansai: '円/kWh', national: '円/kWh',
};

// -------------------------------------------------------------
// Data loading
// -------------------------------------------------------------
async function loadCSV(url) {
  const r = await fetch(url + '?t=' + Date.now());
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
    const r = await fetch('data/manifest.json?t=' + Date.now());
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

// Derive material prices from base metals
function deriveMaterials(metals) {
  return metals.map(r => {
    const usd_jpy = r.usd_jpy || 110;
    const iron_jpy = r.iron_ore * usd_jpy / 1000;
    return {
      ...r,
      ss400:             Math.round((iron_jpy * 4.8 + 31) * 100) / 100,
      aluminum_casting:  Math.round(r.aluminum * 1.3 * 100) / 100,
      iron_casting:      Math.round((iron_jpy * 5.5 + 25) * 100) / 100,
      sus303:            Math.round((r.nickel * 0.10 + iron_jpy * 0.72 + 250) * 100) / 100,
      a5052:             Math.round(r.aluminum * 1.15 * 100) / 100,
    };
  });
}

async function loadAll() {
  const [metalsRaw, sppi, wage, electricity, manifest] = await Promise.all([
    loadCSV('data/metals.csv'),
    loadCSV('data/sppi.csv'),
    loadCSV('data/min_wage.csv'),
    loadCSV('data/electricity.csv').catch(() => []),
    loadManifest(),
  ]);
  STATE.metals = deriveMaterials(metalsRaw);
  STATE.sppi = sppi;
  STATE.wage = wage;
  STATE.electricity = electricity;
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
    const sy = parseInt(startStr.substring(0, 4));
    const ey = parseInt(endStr.substring(0, 4));
    return rows.filter(r => parseInt(r.year) >= sy && parseInt(r.year) <= ey);
  }
  const sd = new Date(startStr + '-01');
  const ed = new Date(endStr + '-28');
  return rows.filter(r => { const d = new Date(r[dateKey]); return d >= sd && d <= ed; });
}

function getCurrentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// -------------------------------------------------------------
// Linear regression (last 5 years)
// -------------------------------------------------------------
function linearRegression(values) {
  const n = values.length;
  if (n < 2) return { slope: 0, intercept: values[0] || 0 };
  let sx = 0, sy = 0, sxy = 0, sxx = 0;
  for (let i = 0; i < n; i++) { sx += i; sy += values[i]; sxy += i * values[i]; sxx += i * i; }
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
  return { slope, intercept: (sy - slope * sx) / n };
}

function forecast(rows, key, dateKey, months) {
  const valid = rows.filter(r => !isNaN(r[key]) && r[key] !== null);
  const recentN = dateKey === 'year' ? 5 : 60;
  const recent = valid.slice(-recentN);
  if (recent.length < 3) return { labels: [], values: [] };
  const reg = linearRegression(recent.map(r => r[key]));
  const lastIdx = recent.length - 1;
  const steps = dateKey === 'year' ? 3 : months;
  const labels = [], values = [];
  const lastRow = valid[valid.length - 1];
  if (dateKey === 'year') {
    const ly = parseInt(lastRow.year);
    labels.push(String(ly)); values.push(lastRow[key]);
    for (let i = 1; i <= steps; i++) {
      labels.push(String(ly + i));
      values.push(Math.max(0, Math.round((reg.intercept + reg.slope * (lastIdx + i)) * 10) / 10));
    }
  } else {
    const ld = new Date(lastRow.date + 'T00:00:00');
    labels.push(new Date(ld)); values.push(lastRow[key]);
    for (let i = 1; i <= steps; i++) {
      const d = new Date(ld); d.setMonth(d.getMonth() + i);
      labels.push(d);
      values.push(Math.max(0, Math.round((reg.intercept + reg.slope * (lastIdx + i)) * 100) / 100));
    }
  }
  return { labels, values };
}

// -------------------------------------------------------------
// Chart builder
// -------------------------------------------------------------
function buildLineChart(canvasId, rows, keys, dateKey = 'date') {
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (STATE.charts[canvasId]) STATE.charts[canvasId].destroy();
  const filtered = filterRange(rows, dateKey);
  const isYear = dateKey === 'year';
  const labels = filtered.map(r => isYear ? String(r[dateKey]) : new Date(r[dateKey] + 'T00:00:00'));
  const datasets = keys.map(k => ({
    label: LABELS[k] || k,
    data: filtered.map(r => r[k] == null || isNaN(r[k]) ? null : r[k]),
    borderColor: COLORS[k] || '#999', backgroundColor: COLORS[k] || '#999',
    borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.3, spanGaps: true,
  }));

  // Forecast
  const fcLabels = [];
  keys.forEach(k => {
    const fc = forecast(rows, k, dateKey, 36);
    if (!fc.labels.length) return;
    fc.labels.forEach(l => { if (!fcLabels.find(f => String(f) === String(l))) fcLabels.push(l); });
    datasets.push({
      label: `${LABELS[k]} 予測`, data: [],
      borderColor: COLORS[k] || '#999', backgroundColor: 'transparent',
      borderWidth: 2, borderDash: [8, 4], pointRadius: 0, pointHoverRadius: 4,
      tension: 0.3, spanGaps: true, _fcMap: Object.fromEntries(fc.labels.map((l, i) => [String(l), fc.values[i]])),
    });
  });

  const all = [...labels];
  fcLabels.forEach(l => { if (!all.find(a => String(a) === String(l))) all.push(l); });
  if (isYear) all.sort((a, b) => parseInt(a) - parseInt(b));
  else all.sort((a, b) => new Date(a) - new Date(b));

  datasets.forEach(ds => {
    if (ds._fcMap) {
      ds.data = all.map(l => { const v = ds._fcMap[String(l)]; return v !== undefined ? v : null; });
      delete ds._fcMap;
    } else {
      const orig = ds.data;
      ds.data = all.map(l => { const i = labels.findIndex(o => String(o) === String(l)); return i >= 0 ? orig[i] : null; });
    }
  });

  const span = all.length;
  let unit = 'year';
  if (span <= 18) unit = 'month'; else if (span <= 48) unit = 'quarter';

  STATE.charts[canvasId] = new Chart(ctx, {
    type: 'line', data: { labels: all, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { font: { size: 12 }, usePointStyle: true, pointStyle: 'line',
            filter: item => !item.text.includes('予測') },
        },
        tooltip: {
          callbacks: {
            title: items => isYear ? items[0].label + '年' : items[0].label,
            label: item => {
              const v = item.parsed.y; if (v == null) return null;
              const lbl = item.dataset.label; const isFc = lbl.includes('予測');
              const base = lbl.replace(' 予測', '');
              const uk = Object.entries(LABELS).find(([, l]) => l === base)?.[0];
              return `${lbl}: ${v.toLocaleString('ja-JP', { maximumFractionDigits: 2 })} ${UNITS[uk] || ''}${isFc ? ' (推定)' : ''}`;
            },
          },
        },
      },
      scales: {
        x: isYear ? {
          type: 'category',
          ticks: { callback: function(v) { return this.getLabelForValue(v) + '年'; }, maxTicksLimit: 15, autoSkip: true },
          grid: { display: false },
        } : {
          type: 'time',
          time: { unit, displayFormats: { month: 'yyyy/MM', quarter: 'yyyy/MM', year: 'yyyy' }, tooltipFormat: 'yyyy年MM月' },
          ticks: { maxTicksLimit: 15, autoSkip: true, font: { size: 11 } },
          grid: { display: false },
        },
        y: { beginAtZero: false, grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

// -------------------------------------------------------------
// Tab renderers
// -------------------------------------------------------------
function renderMaterials() {
  const keys = [...STATE.filters.materials];
  buildLineChart('chart-materials', STATE.metals, keys);
  renderCards('materials-cards', STATE.metals, ['ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052']);
  renderMaterialFilter();
}

function renderWage() {
  const keys = [...STATE.filters.wage];
  buildLineChart('chart-wage', STATE.wage, keys, 'year');
  renderCards('wage-cards', STATE.wage, ['tochigi', 'tokyo', 'nationwide'], 'year');
  renderWageFilter();
}

function renderElectricity() {
  if (!STATE.electricity || !STATE.electricity.length) return;
  buildLineChart('chart-electricity', STATE.electricity, ['tepco', 'chubu', 'kansai', 'national'], 'year');
  renderCards('electricity-cards', STATE.electricity, ['tepco', 'national'], 'year');
}

function renderFreight() {
  buildLineChart('chart-freight', STATE.sppi, ['sppi_total', 'road_freight']);
  renderCards('freight-cards', STATE.sppi, ['sppi_total', 'road_freight']);
}

function renderSummary() {
  const container = document.getElementById('summary-table');
  const baseYear = STATE.summaryBaseYear;
  const compareYear = STATE.summaryCompareYear;
  const curYear = new Date().getFullYear();
  const items = [
    { key: 'ss400', src: STATE.metals, category: '材料' },
    { key: 'aluminum_casting', src: STATE.metals, category: '材料' },
    { key: 'iron_casting', src: STATE.metals, category: '材料' },
    { key: 'sus303', src: STATE.metals, category: '材料' },
    { key: 'a5052', src: STATE.metals, category: '材料' },
    { key: 'road_freight', src: STATE.sppi, category: '運賃' },
    { key: 'sppi_total', src: STATE.sppi, category: '運賃' },
    { key: 'tepco', src: STATE.electricity, category: '電気代', dateKey: 'year' },
    { key: 'national', src: STATE.electricity, category: '電気代', dateKey: 'year' },
    { key: 'tochigi', src: STATE.wage, category: '最低賃金', dateKey: 'year' },
    { key: 'tokyo', src: STATE.wage, category: '最低賃金', dateKey: 'year' },
    { key: 'nationwide', src: STATE.wage, category: '最低賃金', dateKey: 'year' },
  ];

  // Controls: base year + compare year
  let html = `<div class="summary-controls">
    <label>比較元: </label>
    <select id="summary-base-year">`;
  for (let y = 2000; y <= curYear; y++) {
    html += `<option value="${y}" ${String(y) === baseYear ? 'selected' : ''}>${y}年</option>`;
  }
  html += `</select>
    <span class="range-sep">→</span>
    <label>比較先: </label>
    <select id="summary-compare-year">
      <option value="" ${compareYear === '' ? 'selected' : ''}>最新</option>`;
  for (let y = 2000; y <= curYear; y++) {
    html += `<option value="${y}" ${String(y) === compareYear ? 'selected' : ''}>${y}年</option>`;
  }
  html += `</select></div>`;

  const compareLabel = compareYear || '最新';
  html += '<table><thead><tr>' +
    `<th>区分</th><th>項目</th><th>${baseYear}年</th><th>${compareLabel}${compareYear ? '年' : ''}</th><th>変動率</th><th>3年後予測</th><th>単位</th>` +
    '</tr></thead><tbody>';

  const fmt = v => v.toLocaleString('ja-JP', { maximumFractionDigits: 1 });

  for (const it of items) {
    if (!it.src || !it.src.length) continue;
    const dk = it.dateKey || 'date';
    const rows = it.src.filter(r => !isNaN(r[it.key]));
    if (rows.length < 2) continue;

    // Find base year row
    let baseRow;
    if (dk === 'year') baseRow = rows.find(r => String(r.year) === baseYear);
    else baseRow = rows.find(r => r.date && r.date.startsWith(baseYear));
    if (!baseRow) baseRow = rows[0];

    // Find compare year row
    let compRow;
    if (compareYear) {
      if (dk === 'year') compRow = rows.find(r => String(r.year) === compareYear);
      else compRow = rows.find(r => r.date && r.date.startsWith(compareYear));
    }
    if (!compRow) compRow = rows[rows.length - 1]; // fallback to latest

    const baseVal = baseRow[it.key];
    const compVal = compRow[it.key];
    const pct = ((compVal - baseVal) / baseVal * 100);
    const pctClass = pct >= 0 ? 'change-up' : 'change-down';
    const pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';

    const fc = forecast(it.src, it.key, dk, 36);
    const fcLast = fc.values.length > 0 ? fc.values[fc.values.length - 1] : null;
    const fcStr = fcLast != null ? fmt(fcLast) : '-';
    const lastActual = rows[rows.length - 1][it.key];
    const fcPct = fcLast != null ? ((fcLast - lastActual) / lastActual * 100) : null;
    const fcPctStr = fcPct != null ? `(${fcPct >= 0 ? '+' : ''}${fcPct.toFixed(1)}%)` : '';
    const fcClass = fcPct != null ? (fcPct >= 0 ? 'change-up' : 'change-down') : '';

    html += `<tr>
      <td>${it.category}</td><td><strong>${LABELS[it.key]}</strong></td>
      <td class="num">${fmt(baseVal)}</td><td class="num">${fmt(compVal)}</td>
      <td class="num ${pctClass}">${pctStr}</td>
      <td class="num ${fcClass}">${fcStr} ${fcPctStr}</td>
      <td>${UNITS[it.key] || ''}</td></tr>`;
  }
  html += '</tbody></table>';
  html += '<p style="font-size:11px;color:#999;margin-top:12px">※ 材料価格は国際商品価格から推定した参考値です。3年後予測は直近5年の線形回帰に基づく推定値です。</p>';
  container.innerHTML = html;

  document.getElementById('summary-base-year').addEventListener('change', e => {
    STATE.summaryBaseYear = e.target.value;
    renderSummary();
  });
  document.getElementById('summary-compare-year').addEventListener('change', e => {
    STATE.summaryCompareYear = e.target.value;
    renderSummary();
  });
}

// -------------------------------------------------------------
// Cards (期間選択の開始時点と比較)
// -------------------------------------------------------------
function renderCards(containerId, rows, keys, dateKey = 'date') {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = '';
  const filtered = filterRange(rows, dateKey);
  for (const k of keys) {
    const valid = filtered.filter(r => !isNaN(r[k]));
    if (!valid.length) continue;
    const first = valid[0][k];
    const last = valid[valid.length - 1][k];
    const pct = ((last - first) / first * 100);
    const cls = pct >= 0 ? 'up' : 'down';
    const sign = pct >= 0 ? '+' : '';
    const fmt = v => v.toLocaleString('ja-JP', { maximumFractionDigits: 1 });
    const unit = UNITS[k] || '';

    // Period label
    let periodLabel;
    if (dateKey === 'year') {
      periodLabel = `${valid[0].year}年比`;
    } else {
      const sd = valid[0].date.substring(0, 7);
      periodLabel = `${sd}比`;
    }

    c.insertAdjacentHTML('beforeend', `
      <div class="card">
        <div class="card-label">${LABELS[k]}</div>
        <div class="card-value">${fmt(last)} <span style="font-size:12px;font-weight:400;color:var(--ink-2)">${unit}</span></div>
        <div class="card-change ${cls}">${sign}${pct.toFixed(1)}% (${periodLabel})</div>
      </div>`);
  }
}

// -------------------------------------------------------------
// Filter chips
// -------------------------------------------------------------
function renderMaterialFilter() {
  const all = ['ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052'];
  const c = document.getElementById('materials-filter');
  c.innerHTML = '';
  for (const k of all) {
    const active = STATE.filters.materials.has(k);
    const chip = document.createElement('div');
    chip.className = 'chip' + (active ? ' active' : ' muted');
    chip.style.background = active ? COLORS[k] : 'var(--card)';
    chip.style.borderColor = COLORS[k];
    chip.style.color = active ? 'white' : COLORS[k];
    chip.textContent = LABELS[k];
    chip.onclick = () => {
      if (STATE.filters.materials.has(k)) STATE.filters.materials.delete(k);
      else STATE.filters.materials.add(k);
      renderMaterials();
    };
    c.appendChild(chip);
  }
}

function renderWageFilter() {
  const all = ['tochigi', 'gunma', 'ibaraki', 'saitama', 'tokyo', 'aichi', 'osaka', 'nationwide'];
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
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
  renderActiveTab();
}

function clearPresetButtons() {
  document.querySelectorAll('.preset-btn').forEach(x => x.classList.remove('active'));
}

function getActiveTab() { return document.querySelector('.tab-btn.active').dataset.tab; }

function renderActiveTab() {
  const t = getActiveTab();
  if (t === 'materials') renderMaterials();
  else if (t === 'labor') renderWage();
  else if (t === 'electricity') renderElectricity();
  else if (t === 'freight') renderFreight();
  else if (t === 'summary') renderSummary();
}

// -------------------------------------------------------------
// Update button
// -------------------------------------------------------------
async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = '更新中...';
  try {
    await loadAll();
    renderActiveTab();
    btn.textContent = '更新完了';
    setTimeout(() => { btn.textContent = 'データ更新'; btn.disabled = false; }, 2000);
  } catch (e) {
    btn.textContent = '更新失敗';
    setTimeout(() => { btn.textContent = 'データ更新'; btn.disabled = false; }, 2000);
  }
}

// -------------------------------------------------------------
// Real-time clock (JST)
// -------------------------------------------------------------
function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    const now = new Date();
    const jst = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Tokyo' }));
    const hh = String(jst.getHours()).padStart(2, '0');
    const mm = String(jst.getMinutes()).padStart(2, '0');
    const ss = String(jst.getSeconds()).padStart(2, '0');
    const y = jst.getFullYear();
    const mo = String(jst.getMonth() + 1).padStart(2, '0');
    const dd = String(jst.getDate()).padStart(2, '0');
    const days = ['日', '月', '火', '水', '木', '金', '土'];
    const day = days[jst.getDay()];
    el.innerHTML = `${hh}:${mm}:${ss}<span class="clock-date">${y}/${mo}/${dd} (${day})</span>`;
  }
  tick();
  setInterval(tick, 1000);
}

// -------------------------------------------------------------
// Init
// -------------------------------------------------------------
async function init() {
  startClock();
  await loadAll();

  document.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
  document.getElementById('refresh-btn').addEventListener('click', refreshData);

  const rangeEnd = document.getElementById('range-end');
  const rangeStart = document.getElementById('range-start');
  rangeEnd.value = getCurrentMonth();
  rangeEnd.max = getCurrentMonth();
  rangeStart.max = getCurrentMonth();
  STATE.rangeEnd = rangeEnd.value;

  rangeStart.addEventListener('change', e => { STATE.rangeStart = e.target.value; clearPresetButtons(); renderActiveTab(); });
  rangeEnd.addEventListener('change', e => { STATE.rangeEnd = e.target.value; clearPresetButtons(); renderActiveTab(); });

  document.querySelectorAll('.preset-btn').forEach(b => {
    b.addEventListener('click', () => {
      const p = b.dataset.preset;
      if (p === 'all') { rangeStart.value = '2000-01'; rangeEnd.value = getCurrentMonth(); }
      else {
        const s = new Date(); s.setFullYear(s.getFullYear() - parseInt(p));
        rangeStart.value = `${s.getFullYear()}-${String(s.getMonth() + 1).padStart(2, '0')}`;
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
  renderMaterials();
}

init().catch(err => {
  console.error(err);
  document.getElementById('last-updated').textContent = 'データ読み込みエラー: ' + err.message;
});
