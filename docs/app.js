// =============================================================
// IKS 価格高騰トラッカー - ダッシュボードロジック
// =============================================================

const STATE = {
  mode: 'price',     // 'price' | 'index'
  range: 'all',      // 'all' | '10y' | '5y' | '3y' | '1y'
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
  aluminum: 'アルミ',
  copper: '銅',
  nickel: 'ニッケル',
  lead: '鉛',
  tin: '錫',
  zinc: '亜鉛',
  iron_ore: '鉄鉱石',
  tochigi: '栃木',
  gunma: '群馬',
  ibaraki: '茨城',
  saitama: '埼玉',
  tokyo: '東京',
  aichi: '愛知',
  osaka: '大阪',
  nationwide: '全国加重平均',
  sppi_total: 'SPPI総平均',
  road_freight: '道路貨物輸送',
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
      const v = vals[i];
      obj[h] = isNaN(parseFloat(v)) ? v : parseFloat(v);
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
// Utility: indexing and range filtering
// -------------------------------------------------------------
function toIndex(rows, key, baseIdx = 0) {
  const base = rows[baseIdx][key];
  if (!base || isNaN(base)) return rows.map(() => null);
  return rows.map(r => r[key] == null || isNaN(r[key]) ? null : (r[key] / base) * 100);
}

function filterRange(rows, dateKey = 'date') {
  if (STATE.range === 'all') return rows;
  const yearsMap = { '10y': 10, '5y': 5, '3y': 3, '1y': 1 };
  const years = yearsMap[STATE.range];
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - years);
  return rows.filter(r => new Date(r[dateKey]) >= cutoff);
}

// -------------------------------------------------------------
// Chart builders
// -------------------------------------------------------------
function buildLineChart(canvasId, rows, keys, dateKey = 'date') {
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (STATE.charts[canvasId]) STATE.charts[canvasId].destroy();

  const filtered = filterRange(rows, dateKey);

  const datasets = keys.map(k => {
    let data;
    if (STATE.mode === 'index') {
      // Index from base = first row of *full* dataset (2000-01) not filtered
      const full = toIndex(rows, k);
      const filterStart = rows.length - filtered.length;
      data = full.slice(filterStart);
    } else {
      data = filtered.map(r => r[k] == null || isNaN(r[k]) ? null : r[k]);
    }
    return {
      label: LABELS[k] || k,
      data: data.map((v, i) => ({
        x: filtered[i][dateKey],
        y: v,
      })),
      borderColor: COLORS[k] || '#999',
      backgroundColor: COLORS[k] || '#999',
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.1,
      spanGaps: true,
    };
  });

  const isYearOnly = dateKey === 'year';

  STATE.charts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { font: { size: 12 } } },
        tooltip: {
          callbacks: {
            title: items => {
              const v = items[0].parsed.x;
              if (isYearOnly) return `${v}年`;
              const d = new Date(v);
              return `${d.getFullYear()}年${d.getMonth()+1}月`;
            },
            label: item => {
              const k = keys[item.datasetIndex];
              const v = item.parsed.y;
              if (v == null) return null;
              if (STATE.mode === 'index') {
                return `${LABELS[k]}: ${v.toFixed(1)} (2000年=100)`;
              }
              return `${LABELS[k]}: ${v.toLocaleString('ja-JP', {maximumFractionDigits: 2})} ${UNITS[k] || ''}`;
            },
          },
        },
      },
      scales: {
        x: isYearOnly ? {
          type: 'linear',
          ticks: { callback: v => v + '年' },
        } : {
          type: 'time',
          time: { unit: STATE.range === '1y' ? 'month' : 'year' },
        },
        y: {
          beginAtZero: STATE.mode === 'index',
          title: {
            display: true,
            text: STATE.mode === 'index' ? '2000年=100 指数' : '',
          },
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

  let html = '<table><thead><tr>' +
    '<th>区分</th><th>項目</th><th>2000年</th><th>最新</th><th>上昇率</th><th>単位</th>' +
    '</tr></thead><tbody>';

  for (const it of items) {
    const rows = it.src.filter(r => !isNaN(r[it.key]));
    if (rows.length < 2) continue;
    const first = rows[0][it.key];
    const last = rows[rows.length-1][it.key];
    const pct = ((last - first) / first * 100);
    const pctClass = pct >= 0 ? 'change-up' : 'change-down';
    const pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
    const fmt = v => v.toLocaleString('ja-JP', {maximumFractionDigits: 1});
    html += `<tr>
      <td>${it.category}</td>
      <td><strong>${LABELS[it.key]}</strong></td>
      <td class="num">${fmt(first)}</td>
      <td class="num">${fmt(last)}</td>
      <td class="num ${pctClass}">${pctStr}</td>
      <td>${UNITS[it.key] || ''}</td>
    </tr>`;
  }
  html += '</tbody></table>';
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
    const last = valid[valid.length-1][k];
    const pct = ((last - first) / first * 100);
    const cls = pct >= 0 ? 'up' : 'down';
    const sign = pct >= 0 ? '+' : '';
    const fmt = v => v.toLocaleString('ja-JP', {maximumFractionDigits: 1});
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
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.addEventListener('click', () => {
      STATE.mode = b.dataset.mode;
      document.querySelectorAll('.mode-btn').forEach(x =>
        x.classList.toggle('active', x === b));
      renderActiveTab();
    });
  });
  document.getElementById('range-select').addEventListener('change', (e) => {
    STATE.range = e.target.value;
    renderActiveTab();
  });

  renderMetals();
}

init().catch(err => {
  console.error(err);
  document.getElementById('last-updated').textContent = 'データ読み込みエラー: ' + err.message;
});
