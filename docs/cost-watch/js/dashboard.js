// =============================================================
// Cost-Watch Dashboard — KPI cards top page
// =============================================================

const CATEGORIES = [
  { id: "fuel",        emoji: "⛽", label: "燃料",     status: "active" },
  { id: "materials",   emoji: "🔩", label: "材料費",   status: "active" },
  { id: "wages",       emoji: "👷", label: "人件費",   status: "active" },
  { id: "logistics",   emoji: "🚚", label: "物流費",   status: "active" },
  { id: "electricity", emoji: "⚡", label: "電気代",   status: "active" },
];

const FLAG_LABEL = {
  consistent: { ja: "整合",         badge: "🟢" },
  warning:    { ja: "要確認",       badge: "🟡" },
  divergent:  { ja: "ソース間乖離", badge: "🔴" },
  single:     { ja: "単一ソース",   badge: "⚪" },
};

function fmtPct(v) {
  if (v === null || v === undefined) return "-";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function pctClass(v) {
  if (v === null || v === undefined) return "cmp-flat";
  if (v > 0.05)  return "cmp-up";
  if (v < -0.05) return "cmp-down";
  return "cmp-flat";
}

function fmtArrow(v) {
  if (v === null || v === undefined) return "→";
  if (v > 0.05) return "▲";
  if (v < -0.05) return "▼";
  return "→";
}

function fmtRange(item) {
  const r = item.value_range;
  const u = item.unit || "";
  if (!r || r.min === null) return `<span style="color:#999">取得不能</span>`;
  if (r.min === r.max) return `${r.min.toFixed(1)}<span class="kpi-item-unit">${u}</span>`;
  return `${r.min.toFixed(1)}〜${r.max.toFixed(1)}<span class="kpi-item-unit">${u}</span>`;
}

function fmtFlag(item) {
  const flag = item.consistency_flag;
  const meta = FLAG_LABEL[flag] || FLAG_LABEL.single;
  const n = item.sources_count;
  if (n === 0) return `<span class="kpi-item-flag single">${meta.badge} 取得不能</span>`;
  if (flag === "single")  return `<span class="kpi-item-flag single">${meta.badge} 単一ソース</span>`;
  let txt = `${meta.badge} ${n}ソース${meta.ja}`;
  if (n > 1 && item.max_deviation_pct !== null) {
    txt += ` (最大乖離 ${item.max_deviation_pct}%)`;
  }
  return `<span class="kpi-item-flag ${flag}">${txt}</span>`;
}

function pickComparisons(item) {
  for (const s of item.sources) {
    if (s.status === "ok" && s.comparisons) {
      return { ...s.comparisons, from: s.name };
    }
  }
  return { wow_pct: null, mom_pct: null, yoy_pct: null, from: "" };
}

function renderActiveCard(catMeta, data) {
  const items = (data.items || []).slice(0, 2); // top-2 indicators on the card
  const items3 = (data.items || []).length > 2 ? `<div class="kpi-item-name" style="text-align:right;color:#999">他 ${(data.items.length - 2)} 指標</div>` : "";

  const itemsHtml = items.map(it => {
    const cmp = pickComparisons(it);
    return `
      <div class="kpi-item">
        <div class="kpi-item-name">${it.name_ja}</div>
        <div class="kpi-item-value">${fmtRange(it)}</div>
        ${fmtFlag(it)}
        <div class="kpi-item-comparisons">
          <span>WoW <span class="${pctClass(cmp.wow_pct)}">${fmtArrow(cmp.wow_pct)} ${fmtPct(cmp.wow_pct)}</span></span>
          <span>MoM <span class="${pctClass(cmp.mom_pct)}">${fmtArrow(cmp.mom_pct)} ${fmtPct(cmp.mom_pct)}</span></span>
          <span>YoY <span class="${pctClass(cmp.yoy_pct)}">${fmtArrow(cmp.yoy_pct)} ${fmtPct(cmp.yoy_pct)}</span></span>
        </div>
      </div>
    `;
  }).join("");

  return `
    <article class="kpi-card" data-cat="${catMeta.id}">
      <header class="kpi-card-header">
        <span class="kpi-card-title">${catMeta.emoji} ${catMeta.label}</span>
        <span class="kpi-card-arrow">→</span>
      </header>
      ${itemsHtml || '<div class="kpi-item-name" style="color:#999">取得データなし</div>'}
      ${items3}
    </article>
  `;
}

function renderPlaceholderCard(catMeta) {
  return `
    <article class="kpi-card placeholder">
      <header class="kpi-card-header">
        <span class="kpi-card-title">${catMeta.emoji} ${catMeta.label}</span>
        <span class="kpi-card-arrow" style="opacity:0.3">○</span>
      </header>
      <div class="kpi-item">
        <div class="kpi-item-name" style="color:#999">近日対応予定</div>
        <div class="kpi-item-value" style="color:#bbb;font-size:18px">— —</div>
      </div>
    </article>
  `;
}

function fmtUpdated(iso) {
  if (!iso) return "未取得";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  // Format as JST
  const jst = new Date(d.getTime() + 9 * 3600 * 1000);
  const y = jst.getUTCFullYear();
  const m = String(jst.getUTCMonth() + 1).padStart(2, "0");
  const day = String(jst.getUTCDate()).padStart(2, "0");
  const h = String(jst.getUTCHours()).padStart(2, "0");
  const min = String(jst.getUTCMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${h}:${min} JST`;
}

async function loadCategory(catId) {
  const res = await fetch(`../data/cost-watch/${catId}.json`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
  return res.json();
}

async function init() {
  const grid = document.getElementById("cards-grid");
  const updated = document.getElementById("last-updated");
  grid.innerHTML = "";

  let latestUpdate = null;

  for (const cat of CATEGORIES) {
    if (cat.status !== "active") {
      grid.insertAdjacentHTML("beforeend", renderPlaceholderCard(cat));
      continue;
    }
    try {
      const data = await loadCategory(cat.id);
      grid.insertAdjacentHTML("beforeend", renderActiveCard(cat, data));
      if (data.last_updated && (!latestUpdate || data.last_updated > latestUpdate)) {
        latestUpdate = data.last_updated;
      }
    } catch (e) {
      grid.insertAdjacentHTML("beforeend", `
        <article class="kpi-card placeholder">
          <header class="kpi-card-header">
            <span class="kpi-card-title">${cat.emoji} ${cat.label}</span>
            <span class="kpi-card-arrow" style="opacity:0.3">×</span>
          </header>
          <div class="kpi-item">
            <div class="kpi-item-name" style="color:#c8102e">取得失敗: ${e.message}</div>
          </div>
        </article>
      `);
    }
  }

  updated.textContent = `最終更新: ${fmtUpdated(latestUpdate)}`;

  // Wire up card clicks (active cards only)
  document.querySelectorAll(".kpi-card[data-cat]").forEach(card => {
    card.addEventListener("click", () => {
      const cat = card.dataset.cat;
      window.location.href = `category.html?cat=${cat}`;
    });
  });
}

init();
