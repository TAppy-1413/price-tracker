// =============================================================
// コストトレンドモニター - ダッシュボードロジック
// =============================================================

const STATE = {
  rangeStart: '2000-01',
  rangeEnd: null,
  metals: null,
  sppi: null,
  wage: null,
  electricity: null,  // legacy (年次シード) - 月次はmetalsから
  charts: {},
  filters: {
    materials: new Set(['ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052']),
    wage: new Set(['tochigi', 'gunma', 'ibaraki', 'tokyo', 'nationwide']),
  },
  summaryBaseYear: '2000',
  summaryCompareYear: '',  // empty = latest
  materialUnit: 'kg',  // 'kg' or 't'
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
  ocean_freight:     '#1a6b3c',
  air_freight:       '#8e24aa',
  coastal_freight:   '#f57c00',
  regular:           '#e53935',
  highoctane:        '#6a1b9a',
  diesel:            '#2e7d32',
  crude_oil:         '#1565c0',
  electricity:       '#ff6600',
  hokkaido:          '#1a6b3c', tohoku: '#2c5aa0',
  hokuriku:          '#8b3a2e', chugoku: '#6c7a89',
  shikoku:           '#d4a017', kyushu: '#c8702e',
  okinawa:           '#8e24aa',
  copper:            '#c8702e',
  diesel_national:   '#1565c0', truck_surcharge: '#c8102e',
  export_usa_20ft:   '#1a6b3c', export_eu_20ft: '#8e24aa',
  export_asia_20ft:  '#f57c00',
  tepco:             '#ff6600',
  chubu:             '#2c5aa0',
  kansai:            '#c8102e',
  national:          '#333333',
};

const LABELS = {
  ss400: 'SS400', aluminum_casting: 'アルミ鋳物', iron_casting: '鉄鋳物',
  sus303: 'SUS303', a5052: 'アルミニウム',
  tochigi: '栃木', gunma: '群馬', ibaraki: '茨城',
  saitama: '埼玉', tokyo: '東京', aichi: '愛知',
  osaka: '大阪', nationwide: '全国加重平均',
  sppi_total: 'SPPI総平均', road_freight: 'トラック運賃',
  ocean_freight: '外航船便', air_freight: '国際航空便', coastal_freight: '内航船便',
  regular: 'レギュラー', highoctane: 'ハイオク', diesel: '軽油', crude_oil: '原油',
  electricity: '事業用電力',
  hokkaido: '北海道電力', tohoku: '東北電力', hokuriku: '北陸電力',
  chugoku: '中国電力', shikoku: '四国電力', kyushu: '九州電力', okinawa: '沖縄電力',
  copper: '銅建値',
  diesel_national: '軽油(全国)', truck_surcharge: 'トラックサーチャージ',
  export_usa_20ft: '米国向け20ft', export_eu_20ft: '欧州向け20ft', export_asia_20ft: 'アジア向け20ft',
  tepco: '東電管内', chubu: '中部電力', kansai: '関西電力', national: '全国平均',
};

const UNITS = {
  ss400: '円/kg', aluminum_casting: '円/kg', iron_casting: '円/kg',
  sus303: '円/kg', a5052: '円/kg',
  tochigi: '円/時', gunma: '円/時', ibaraki: '円/時',
  saitama: '円/時', tokyo: '円/時', aichi: '円/時',
  osaka: '円/時', nationwide: '円/時',
  sppi_total: '指数(2020=100)', road_freight: '指数(2020=100)',
  ocean_freight: '円/100kg', air_freight: '円/100kg', coastal_freight: '円/100kg',
  road_freight: '円/100kg',
  regular: '円/L', highoctane: '円/L', diesel: '円/L', crude_oil: '円/L',
  electricity: '円/kWh',
  hokkaido: '円/kWh', tohoku: '円/kWh', hokuriku: '円/kWh',
  chugoku: '円/kWh', shikoku: '円/kWh', kyushu: '円/kWh', okinawa: '円/kWh',
  copper: '円/kg',
  diesel_national: '円/L', truck_surcharge: '円/車',
  export_usa_20ft: 'US$/20ft', export_eu_20ft: 'US$/20ft', export_asia_20ft: 'US$/20ft',
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

async function loadAll() {
  const [materials, sppi, wage, electricity, jSteel, jAlu, jCopper, jElec, jTruck, jSea, manifest] = await Promise.all([
    loadCSV('data/materials.csv'),
    loadCSV('data/sppi.csv'),
    loadCSV('data/min_wage.csv'),
    loadCSV('data/electricity.csv').catch(() => []),
    loadCSV('data/japia_steel.csv').catch(() => []),
    loadCSV('data/japia_aluminum.csv').catch(() => []),
    loadCSV('data/japia_copper.csv').catch(() => []),
    loadCSV('data/japia_electricity.csv').catch(() => []),
    loadCSV('data/japia_truck.csv').catch(() => []),
    loadCSV('data/japia_sea.csv').catch(() => []),
    loadManifest(),
  ]);
  STATE.japia = { steel: jSteel, alu: jAlu, copper: jCopper, elec: jElec, truck: jTruck, sea: jSea };

  // JAPIA steel/aluminum → 材料カラムに統合
  // ss400 = 熱延鋼板(千円/t = 円/kg), iron_casting = 冷延鋼板
  // a5052 = アルミ新地金, aluminum_casting = アルミ再生塊
  if (jSteel.length && materials.length) {
    const steelMap = Object.fromEntries(jSteel.map(r => [r.date, r]));
    const aluMap = Object.fromEntries(jAlu.map(r => [r.date, r]));
    const copperMap = Object.fromEntries(jCopper.map(r => [r.date, r]));
    materials.forEach(m => {
      const s = steelMap[m.date];
      const a = aluMap[m.date];
      const c = copperMap[m.date];
      if (s && !isNaN(s.hot_rolled)) m.ss400 = s.hot_rolled;
      if (s && !isNaN(s.cold_rolled)) m.iron_casting = s.cold_rolled;
      if (a && !isNaN(a.al_ingot)) m.a5052 = a.al_ingot;
      if (a && !isNaN(a.al_recycled)) m.aluminum_casting = a.al_recycled;
      if (c && !isNaN(c.copper)) m.copper = c.copper;
    });
    // JAPIA のデータ範囲の方が広い場合、2020年以前のレコードも追加
    const existingDates = new Set(materials.map(m => m.date));
    jSteel.forEach(s => {
      if (!existingDates.has(s.date) && s.date >= '2000-01-01') {
        const row = { date: s.date, ss400: s.hot_rolled, iron_casting: s.cold_rolled };
        const a = aluMap[s.date];
        if (a) { row.a5052 = a.al_ingot; row.aluminum_casting = a.al_recycled; }
        const c = copperMap[s.date];
        if (c) row.copper = c.copper;
        materials.push(row);
      }
    });
    materials.sort((a, b) => a.date.localeCompare(b.date));
  }
  STATE.metals = materials;  // materials.csv (日銀CGPI)

  // SPPI指数 → 円/100kg 換算 (2020年基準単価)
  const freightBase = { road_freight: 3500, ocean_freight: 2000, air_freight: 8000, coastal_freight: 1500 };
  sppi.forEach(r => {
    for (const [k, base] of Object.entries(freightBase)) {
      if (!isNaN(r[k])) r[k] = Math.round(r[k] * base / 100);
    }
  });
  STATE.sppi = sppi;
  STATE.wage = wage;
  STATE.electricity = electricity;
  if (manifest) {
    document.getElementById('last-updated').textContent =
      `データ生成: ${manifest.generated_at}`;
  }
  // ブラウザ取得時刻を表示
  const now = new Date();
  const jst = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Tokyo' }));
  const ts = `${jst.getFullYear()}-${String(jst.getMonth()+1).padStart(2,'0')}-${String(jst.getDate()).padStart(2,'0')} ${String(jst.getHours()).padStart(2,'0')}:${String(jst.getMinutes()).padStart(2,'0')}`;
  document.getElementById('last-fetched').textContent = `最終取得: ${ts}`;
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
function buildLineChart(canvasId, rows, keys, dateKey = 'date', unitMultiplier = 1) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  if (STATE.charts[canvasId]) STATE.charts[canvasId].destroy();
  const filtered = filterRange(rows, dateKey);
  const isYear = dateKey === 'year';
  const labels = filtered.map(r => isYear ? String(r[dateKey]) : new Date(r[dateKey] + 'T00:00:00'));
  const datasets = keys.map(k => ({
    label: LABELS[k] || k,
    data: filtered.map(r => r[k] == null || isNaN(r[k]) ? null : Math.round(r[k] * unitMultiplier * 100) / 100),
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
      tension: 0.3, spanGaps: true, _fcMap: Object.fromEntries(fc.labels.map((l, i) => [String(l), Math.round(fc.values[i] * unitMultiplier * 100) / 100])),
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

  // 実データの期間（選択範囲）からX軸の単位を決定
  const actualMonths = filtered.length;
  let unit = 'year';
  if (actualMonths <= 18) unit = 'month';
  else if (actualMonths <= 48) unit = 'quarter';

  // X軸の範囲: 実データ開始〜予測終了
  let xMin, xMax;
  if (!isYear && all.length > 0) {
    xMin = all[0];
    xMax = all[all.length - 1];
  }

  const xScale = isYear ? {
    type: 'category',
    ticks: { callback: function(v) { return this.getLabelForValue(v) + '年'; }, maxTicksLimit: 15, autoSkip: true },
    grid: { display: false },
  } : {
    type: 'time',
    min: xMin, max: xMax,
    time: { unit, displayFormats: { month: 'yyyy/MM', quarter: 'yyyy/MM', year: 'yyyy' }, tooltipFormat: 'yyyy年MM月' },
    ticks: { maxTicksLimit: 12, autoSkip: true, font: { size: 11 } },
    grid: { display: false },
  };

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
      scales: { x: xScale, y: { beginAtZero: false, grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { font: { size: 11 } } } },
    },
  });
}

// -------------------------------------------------------------
// Tab renderers
// -------------------------------------------------------------
function renderMaterials() {
  const keys = [...STATE.filters.materials];
  const mult = STATE.materialUnit === 't' ? 1000 : 1;
  const unitLabel = STATE.materialUnit === 't' ? '円/t' : '円/kg';
  document.querySelector('#tab-materials h2').textContent = `材料価格 (${unitLabel})`;
  buildLineChart('chart-materials', STATE.metals, keys, 'date', mult);
  renderCards('materials-cards', STATE.metals, ['ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052'], 'date', mult);
  renderMaterialFilter();
  renderUnitToggle();
}

function renderWage() {
  const keys = [...STATE.filters.wage];
  buildLineChart('chart-wage', STATE.wage, keys, 'year');
  renderCards('wage-cards', STATE.wage, ['tochigi', 'tokyo', 'nationwide'], 'year');
  renderWageFilter();
}

function renderElectricity() {
  // JAPIA 10社の月次データがあればそれを使用、なければ年次データフォールバック
  const japiaElec = STATE.japia?.elec || [];
  if (japiaElec.length) {
    const companies = ['tepco', 'chubu', 'kansai', 'hokkaido', 'tohoku', 'hokuriku', 'chugoku', 'shikoku', 'kyushu', 'okinawa'];
    buildLineChart('chart-electricity', japiaElec, companies);
    renderCards('electricity-cards', japiaElec, companies);
    // 2つ目のグラフは非表示 (JAPIAに全部含まれる)
    const secondCanvas = document.getElementById('chart-electricity-region');
    if (secondCanvas) secondCanvas.parentElement.parentElement.style.display = 'none';
  } else if (STATE.electricity && STATE.electricity.length) {
    buildLineChart('chart-electricity', STATE.electricity, ['tepco', 'chubu', 'kansai', 'national'], 'year');
    renderCards('electricity-cards', STATE.electricity, ['tepco', 'chubu', 'kansai', 'national'], 'year');
  }
}

function renderFreight() {
  buildLineChart('chart-freight', STATE.sppi, ['road_freight', 'ocean_freight', 'air_freight', 'coastal_freight']);
  renderCards('freight-cards', STATE.sppi, ['road_freight', 'ocean_freight', 'air_freight', 'coastal_freight']);
}

function renderFuel() {
  // JAPIA軽油(全国)データがあれば、metalsのdieselをJAPIA値で上書き
  const jTruck = STATE.japia?.truck || [];
  if (jTruck.length && STATE.metals) {
    const dieselMap = Object.fromEntries(jTruck.map(r => [r.date, r.diesel_national]));
    STATE.metals.forEach(m => {
      if (dieselMap[m.date] != null && !isNaN(dieselMap[m.date])) {
        m.diesel = dieselMap[m.date];
      }
    });
  }
  buildLineChart('chart-fuel', STATE.metals, ['regular', 'highoctane', 'diesel', 'crude_oil']);
  renderCards('fuel-cards', STATE.metals, ['regular', 'highoctane', 'diesel', 'crude_oil']);
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
    { key: 'ocean_freight', src: STATE.sppi, category: '運賃' },
    { key: 'air_freight', src: STATE.sppi, category: '運賃' },
    { key: 'coastal_freight', src: STATE.sppi, category: '運賃' },
    { key: 'regular', src: STATE.metals, category: '燃料' },
    { key: 'highoctane', src: STATE.metals, category: '燃料' },
    { key: 'diesel', src: STATE.metals, category: '燃料' },
    { key: 'crude_oil', src: STATE.metals, category: '燃料' },
    { key: 'electricity', src: STATE.metals, category: '電気代' },
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
function renderCards(containerId, rows, keys, dateKey = 'date', unitMult = 1) {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = '';
  const filtered = filterRange(rows, dateKey);
  for (const k of keys) {
    const valid = filtered.filter(r => !isNaN(r[k]));
    if (!valid.length) continue;
    const first = valid[0][k] * unitMult;
    const last = valid[valid.length - 1][k] * unitMult;
    const pct = ((last - first) / first * 100);
    const cls = pct >= 0 ? 'up' : 'down';
    const sign = pct >= 0 ? '+' : '';
    const fmt = v => v.toLocaleString('ja-JP', { maximumFractionDigits: unitMult >= 1000 ? 0 : 1 });
    let unit = UNITS[k] || '';
    if (unitMult >= 1000 && unit.includes('円/kg')) unit = '円/t';

    // Period label & 最新値の日付
    let periodLabel, latestDateLabel;
    if (dateKey === 'year') {
      periodLabel = `${valid[0].year}年比`;
      latestDateLabel = `${valid[valid.length - 1].year}年`;
    } else {
      const sd = valid[0].date.substring(0, 7);
      periodLabel = `${sd}比`;
      const ld = valid[valid.length - 1].date.substring(0, 7);
      const [y, m] = ld.split('-');
      latestDateLabel = `${y}年${parseInt(m)}月`;
    }

    c.insertAdjacentHTML('beforeend', `
      <div class="card">
        <div class="card-label">${LABELS[k]} <span style="font-weight:400;color:var(--ink-2);font-size:11px">(${latestDateLabel})</span></div>
        <div class="card-value">${fmt(last)} <span style="font-size:12px;font-weight:400;color:var(--ink-2)">${unit}</span></div>
        <div class="card-change ${cls}">${sign}${pct.toFixed(1)}% (${periodLabel})</div>
      </div>`);
  }
}

// -------------------------------------------------------------
// Filter chips
// -------------------------------------------------------------
function renderUnitToggle() {
  let el = document.getElementById('unit-toggle');
  if (!el) {
    el = document.createElement('div');
    el.id = 'unit-toggle';
    el.className = 'unit-toggle';
    const filterEl = document.getElementById('materials-filter');
    filterEl.parentElement.insertBefore(el, filterEl);
  }
  const isKg = STATE.materialUnit === 'kg';
  el.innerHTML = `
    <button class="unit-btn ${isKg ? 'active' : ''}" data-unit="kg">円/kg</button>
    <button class="unit-btn ${!isKg ? 'active' : ''}" data-unit="t">円/t</button>`;
  el.querySelectorAll('.unit-btn').forEach(b => {
    b.onclick = () => {
      STATE.materialUnit = b.dataset.unit;
      renderMaterials();
    };
  });
}

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
function getTabDataRange(name) {
  const ranges = {
    materials:   { start: STATE.metals?.[0]?.date?.substring(0, 7) || '2020-01',
                   end: STATE.metals?.[STATE.metals.length - 1]?.date?.substring(0, 7) || getCurrentMonth() },
    fuel:        { start: STATE.metals?.[0]?.date?.substring(0, 7) || '2020-01',
                   end: STATE.metals?.[STATE.metals.length - 1]?.date?.substring(0, 7) || getCurrentMonth() },
    labor:       { start: '2000-01', end: getCurrentMonth() },
    electricity: { start: STATE.japia?.elec?.[0]?.date?.substring(0, 7) || '2011-04', end: getCurrentMonth() },
    freight:     { start: '2000-01', end: getCurrentMonth() },
    summary:     { start: '2000-01', end: getCurrentMonth() },
  };
  return ranges[name] || { start: '2000-01', end: getCurrentMonth() };
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));

  const range = getTabDataRange(name);
  const rangeStart = document.getElementById('range-start');
  const rangeEnd = document.getElementById('range-end');

  // min/max を設定してデータ範囲外を選択不可に
  rangeStart.min = range.start;
  rangeEnd.min = range.start;

  // 値がデータ範囲外なら強制修正
  if (rangeStart.value < range.start) {
    rangeStart.value = range.start;
    STATE.rangeStart = range.start;
  }
  if (rangeEnd.value < range.start) {
    rangeEnd.value = range.end;
    STATE.rangeEnd = range.end;
  }

  // プリセットボタンの有効/無効
  document.querySelectorAll('.preset-btn').forEach(b => {
    const preset = b.dataset.preset;
    if (preset === 'all') {
      b.disabled = false;
    } else {
      const years = parseInt(preset);
      const presetStart = new Date();
      presetStart.setFullYear(presetStart.getFullYear() - years);
      const presetMonth = `${presetStart.getFullYear()}-${String(presetStart.getMonth() + 1).padStart(2, '0')}`;
      b.disabled = presetMonth < range.start;
      b.style.opacity = b.disabled ? '0.3' : '1';
      b.style.pointerEvents = b.disabled ? 'none' : 'auto';
    }
  });

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
  else if (t === 'fuel') renderFuel();
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
      if (p === 'all') {
        const r = getTabDataRange(getActiveTab());
        rangeStart.value = r.start; rangeEnd.value = getCurrentMonth();
      }
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
  // 初回: 材料タブのデータ範囲に合わせる
  switchTab('materials');
}

init().catch(err => {
  console.error(err);
  document.getElementById('last-updated').textContent = 'データ読み込みエラー: ' + err.message;
});
