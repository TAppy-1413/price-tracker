// =============================================================
// Cost-Watch Category Detail Page
// =============================================================

const FLAG_LABEL = {
  consistent: { ja: "整合",         badge: "🟢" },
  warning:    { ja: "要確認",       badge: "🟡" },
  divergent:  { ja: "ソース間乖離", badge: "🔴" },
  single:     { ja: "単一ソース",   badge: "⚪" },
};

const SOURCE_COLORS = [
  "#c8102e", // IKS red
  "#2c5aa0", // blue
  "#d4a017", // gold
  "#1a6b3c", // green
  "#8e24aa", // purple
];

function getQueryParam(name) {
  const u = new URL(window.location.href);
  return u.searchParams.get(name);
}

function fmtPct(v) {
  if (v === null || v === undefined) return "-";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtUpdated(iso) {
  if (!iso) return "未取得";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const jst = new Date(d.getTime() + 9 * 3600 * 1000);
  const y = jst.getUTCFullYear();
  const m = String(jst.getUTCMonth() + 1).padStart(2, "0");
  const day = String(jst.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtFlag(item) {
  const flag = item.consistency_flag;
  const meta = FLAG_LABEL[flag] || FLAG_LABEL.single;
  const n = item.sources_count;
  if (n === 0) return `${meta.badge} 取得不能`;
  if (flag === "single") return `${meta.badge} 単一ソース`;
  let s = `${meta.badge} ${n}ソース${meta.ja}`;
  if (n > 1 && item.max_deviation_pct !== null) s += ` (最大乖離 ${item.max_deviation_pct}%)`;
  return s;
}

function buildSourceTable(item) {
  const head = `
    <thead>
      <tr>
        <th>ソース</th>
        <th>状態</th>
        <th>現在値 (${item.unit})</th>
        <th>前週比</th>
        <th>前月比</th>
        <th>前年比</th>
        <th>取得日</th>
      </tr>
    </thead>
  `;
  const rows = item.sources.map(s => {
    const cmp = s.comparisons || {};
    const statusJa = { ok: "正常", stale: "古い", failed: "失敗" }[s.status] || s.status;
    const cls = `status-${s.status}`;
    return `
      <tr>
        <td>${s.url ? `<a href="${s.url}" target="_blank" rel="noopener">${s.name}</a>` : s.name}</td>
        <td class="${cls}">${statusJa}</td>
        <td>${s.current !== null && s.current !== undefined ? s.current.toFixed(2) : "-"}</td>
        <td>${fmtPct(cmp.wow_pct)}</td>
        <td>${fmtPct(cmp.mom_pct)}</td>
        <td>${fmtPct(cmp.yoy_pct)}</td>
        <td>${fmtUpdated(s.fetched_at)}</td>
      </tr>
    `;
  }).join("");
  return `<table class="source-table">${head}<tbody>${rows}</tbody></table>`;
}

function buildChart(canvasId, item, periodYears) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  // Cutoff date based on period
  let cutoffMs = null;
  if (periodYears && periodYears !== "all") {
    cutoffMs = Date.now() - periodYears * 365.25 * 24 * 3600 * 1000;
  }

  const datasets = item.sources
    .filter(s => s.history && s.history.length > 0)
    .map((s, i) => {
      const points = s.history
        .filter(h => !cutoffMs || new Date(h.date).getTime() >= cutoffMs)
        .map(h => ({ x: h.date, y: h.value }));
      return {
        label: s.name,
        data: points,
        borderColor: SOURCE_COLORS[i % SOURCE_COLORS.length],
        backgroundColor: SOURCE_COLORS[i % SOURCE_COLORS.length] + "20",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.1,
        spanGaps: true,
      };
    });

  // Destroy existing chart if any
  if (ctx._chart) ctx._chart.destroy();

  ctx._chart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "time",
          time: { unit: periodYears && periodYears <= 1 ? "month" : "year", tooltipFormat: "yyyy-MM-dd" },
          grid: { color: "#eee" },
        },
        y: {
          title: { display: true, text: item.unit },
          grid: { color: "#eee" },
        },
      },
      plugins: {
        legend: { position: "bottom", labels: { font: { size: 12 } } },
        tooltip: { callbacks: { title: (items) => items[0].parsed.x ? new Date(items[0].parsed.x).toISOString().slice(0,10) : "" } },
      },
    },
  });
}

function renderIndicator(item, idx) {
  const id = `chart-${idx}`;
  const range = item.value_range
    ? (item.value_range.min === item.value_range.max
        ? `${item.value_range.min.toFixed(2)} ${item.unit}`
        : `${item.value_range.min.toFixed(2)}〜${item.value_range.max.toFixed(2)} ${item.unit}`)
    : "取得不能";

  return `
    <section class="indicator-block" data-idx="${idx}">
      <h2>${item.name_ja}</h2>
      <div class="indicator-summary">
        <div>
          <div style="font-size:12px;color:var(--ink-2)">現在値（範囲）</div>
          <div class="big-value">${range}</div>
        </div>
        <div>
          <div style="font-size:12px;color:var(--ink-2)">整合性</div>
          <div style="margin-top:4px">${fmtFlag(item)}</div>
        </div>
      </div>
      ${buildSourceTable(item)}
      <div style="display:flex;gap:8px;margin:16px 0 8px;flex-wrap:wrap">
        <button class="period-btn" data-period="1">直近1年</button>
        <button class="period-btn" data-period="3">直近3年</button>
        <button class="period-btn" data-period="5">直近5年</button>
        <button class="period-btn" data-period="all">全期間</button>
      </div>
      <div class="chart-wrapper"><canvas id="${id}"></canvas></div>
    </section>
  `;
}

function styleActivePeriodBtn(scope, period) {
  scope.querySelectorAll(".period-btn").forEach(b => {
    if (String(b.dataset.period) === String(period)) {
      b.style.cssText = "padding:6px 12px;font-size:12px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer;font-family:inherit;";
    } else {
      b.style.cssText = "padding:6px 12px;font-size:12px;background:#fff;color:var(--ink);border:1px solid var(--border);border-radius:4px;cursor:pointer;font-family:inherit;";
    }
  });
}

async function init() {
  const cat = getQueryParam("cat") || "fuel";
  const main = document.getElementById("detail-main");
  const updated = document.getElementById("last-updated");
  const titleEl = document.getElementById("category-title");

  let data;
  try {
    const res = await fetch(`../data/cost-watch/${cat}.json`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    main.innerHTML = `<div class="loading" style="color:#c8102e">データ取得に失敗しました: ${e.message}</div>`;
    return;
  }

  titleEl.textContent = `📊 ${data.category_name_ja}`;
  updated.textContent = `最終更新: ${fmtUpdated(data.last_updated)}`;
  document.title = `${data.category_name_ja} — コストウォッチ`;

  if (!data.items || data.items.length === 0) {
    main.innerHTML = `<div class="loading">指標データがございません</div>`;
    return;
  }

  main.innerHTML = data.items.map((it, i) => renderIndicator(it, i)).join("");

  // Render charts (default 3-year)
  data.items.forEach((it, idx) => {
    const block = document.querySelector(`.indicator-block[data-idx="${idx}"]`);
    buildChart(`chart-${idx}`, it, 3);
    styleActivePeriodBtn(block, 3);

    block.querySelectorAll(".period-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = btn.dataset.period === "all" ? "all" : Number(btn.dataset.period);
        buildChart(`chart-${idx}`, it, p);
        styleActivePeriodBtn(block, p);
      });
    });
  });
}

init();
