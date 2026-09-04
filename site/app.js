"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  data: null,
  sort: "drop",
  filter: "",
  detail: null,      // product id currently open
  range: 0,          // days; 0 = all
};

/* ---------- repo links (derived from the Pages URL) ---------- */
const REPO = (() => {
  const host = location.hostname;                       // <owner>.github.io
  const owner = host.endsWith("github.io") ? host.split(".")[0] : "OWNER";
  const repo = location.pathname.split("/").filter(Boolean)[0] || "REPO";
  return { owner, repo, base: `https://github.com/${owner}/${repo}` };
})();

/* ---------- formatting ---------- */
function money(v, cur) {
  if (v == null || isNaN(v)) return "—";
  const code = cur && /^[A-Za-z]{3}$/.test(cur) ? cur.toUpperCase() : null;
  try {
    return new Intl.NumberFormat(undefined,
      code ? { style: "currency", currency: code, maximumFractionDigits: 2 }
           : { maximumFractionDigits: 2 }).format(v);
  } catch { return (cur ? cur + " " : "") + Number(v).toFixed(2); }
}
const curSymbol = (cur) => money(0, cur).replace(/[\d.,\s]/g, "") || (cur || "");
function fdate(s, opts = { month: "short", day: "numeric", year: "numeric" }) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, opts);
}
const pct = (n) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(1)}%`);
function axisNum(v) {
  const abs = Math.abs(v);
  if (abs >= 1000) return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(v);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: abs < 100 ? 2 : 0 }).format(v);
}

/* ---------- target price (local overrides live in the browser) ---------- */
const tkey = (id) => `pt.target.${id}`;
function localTarget(id) {
  try { const v = localStorage.getItem(tkey(id)); return v == null ? null : Number(v); }
  catch { return null; }
}
function setLocalTarget(id, v) {
  try { v == null ? localStorage.removeItem(tkey(id)) : localStorage.setItem(tkey(id), String(v)); }
  catch {}
}
const effTarget = (p) => (p.target != null ? Number(p.target) : localTarget(p.id));
const targetFromFile = (p) => p.target != null;

/* ---------- status ---------- */
function statusOf(p) {
  const s = p.stats || {};
  if (p.last_error || (s.data_points === 0)) return { cls: "fail", label: "check failing" };
  const t = effTarget(p);
  if (t != null && s.current != null && s.current <= t) return { cls: "hit", label: "target met" };
  if (s.is_all_time_low && s.data_points > 1) return { cls: "low", label: "all-time low" };
  if (s.change_pct != null && s.change_pct <= -0.5) return { cls: "drop", label: "dropped" };
  if (s.change_pct != null && s.change_pct >= 0.5) return { cls: "up", label: "up" };
  return { cls: "flat", label: s.trend || "flat" };
}

/* =====================================================================
   CHART  — hand-rolled SVG line chart, optional axis + hover crosshair
   ===================================================================== */
function chart(el, series, opt = {}) {
  const o = { axis: false, low: null, target: null, hover: true, ...opt };
  el.innerHTML = "";
  const pts = (series || []).filter((p) => p.price != null)
    .map((p) => ({ t: Date.parse(p.date), v: p.price, date: p.date }));
  if (pts.length < 2) {
    el.innerHTML = `<p class="muted sm" style="padding:8px 2px">Not enough data yet — one point so far.</p>`;
    return;
  }
  const W = el.clientWidth || 320;
  const H = el.clientHeight || 96;
  const padL = o.axis ? 52 : 2, padR = o.axis ? 12 : 2;
  const padT = 8, padB = o.axis ? 22 : 5;
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  const vals = pts.map((p) => p.v);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (o.target != null) { lo = Math.min(lo, o.target); hi = Math.max(hi, o.target); }
  const span = hi - lo || 1;
  lo -= span * 0.08; hi += span * 0.08;

  const X = (t) => padL + (t1 === t0 ? 0.5 : (t - t0) / (t1 - t0)) * (W - padL - padR);
  const Y = (v) => H - padB - (v - lo) / (hi - lo) * (H - padT - padB);

  const line = pts.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)} ${Y(p.v).toFixed(1)}`).join(" ");
  const area = `${line} L${X(t1).toFixed(1)} ${Y(lo).toFixed(1)} L${X(t0).toFixed(1)} ${Y(lo).toFixed(1)} Z`;

  const parts = [`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`];
  parts.push(`<path class="c-area" d="${area}"/>`);

  if (o.low != null && o.low >= lo && o.low <= hi)
    parts.push(`<line class="c-low" x1="${padL}" x2="${W - padR}" y1="${Y(o.low).toFixed(1)}" y2="${Y(o.low).toFixed(1)}"/>`);
  if (o.target != null && o.target >= lo && o.target <= hi)
    parts.push(`<line class="c-target" x1="${padL}" x2="${W - padR}" y1="${Y(o.target).toFixed(1)}" y2="${Y(o.target).toFixed(1)}"/>`);

  parts.push(`<path class="c-line" d="${line}"/>`);

  // all-time-low marker dot
  const loPt = pts.reduce((a, b) => (b.v < a.v ? b : a));
  parts.push(`<circle class="c-lowdot" cx="${X(loPt.t).toFixed(1)}" cy="${Y(loPt.v).toFixed(1)}" r="3"/>`);

  if (o.axis) {
    parts.push(`<line class="c-axis" x1="${padL}" x2="${padL}" y1="${padT}" y2="${H - padB}"/>`);
    parts.push(`<line class="c-axis" x1="${padL}" x2="${W - padR}" y1="${H - padB}" y2="${H - padB}"/>`);
    const flatV = Math.max(...vals) === Math.min(...vals);
    const seenY = new Set();
    for (let i = 0; i <= 3; i++) {
      const v = flatV ? vals[0] : lo + (hi - lo) * (i / 3);
      const lbl = axisNum(v);
      if (flatV ? i !== 2 : seenY.has(lbl)) continue;
      seenY.add(lbl);
      parts.push(`<text class="c-tick" x="${padL - 7}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end">${lbl}</text>`);
    }
    const seenX = new Set();
    for (let i = 0; i <= 3; i++) {
      const t = t0 + (t1 - t0) * (i / 3);
      const lbl = fdate(new Date(t).toISOString(), { month: "short", day: "numeric" });
      if (seenX.has(lbl)) continue;
      seenX.add(lbl);
      const anchor = i === 0 ? "start" : i === 3 ? "end" : "middle";
      parts.push(`<text class="c-tick" x="${X(t).toFixed(1)}" y="${H - padB + 14}" text-anchor="${anchor}">${lbl}</text>`);
    }
  }

  // hover layer
  parts.push(`<g class="c-cursor-g" style="display:none">
      <line class="c-cursor" y1="${padT}" y2="${H - padB}"/>
      <circle class="c-dot" r="4"/></g>`);
  parts.push(`<rect x="0" y="0" width="${W}" height="${H}" fill="transparent" class="c-hit"/>`);
  parts.push(`</svg><div class="chart-tip"></div>`);
  el.innerHTML = parts.join("");

  if (!o.hover) return;
  const svg = $("svg", el), g = $(".c-cursor-g", el);
  const dot = $(".c-dot", g), vline = $(".c-cursor", g), tip = $(".chart-tip", el);
  const hit = $(".c-hit", el);

  function move(clientX) {
    const r = svg.getBoundingClientRect();
    const px = (clientX - r.left) / r.width * W;           // into viewBox units
    let best = pts[0], bd = Infinity;
    for (const p of pts) { const d = Math.abs(X(p.t) - px); if (d < bd) { bd = d; best = p; } }
    const cx = X(best.t), cy = Y(best.v);
    g.style.display = "";
    vline.setAttribute("x1", cx); vline.setAttribute("x2", cx);
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
    tip.textContent = `${money(best.v, o.cur)} · ${fdate(best.date)}`;
    tip.style.left = (cx / W * 100) + "%";
    tip.style.top = (cy / H * 100) + "%";
    tip.classList.add("on");
  }
  const end = () => { g.style.display = "none"; tip.classList.remove("on"); };
  hit.addEventListener("mousemove", (e) => move(e.clientX));
  hit.addEventListener("mouseleave", end);
  hit.addEventListener("touchmove", (e) => { if (e.touches[0]) move(e.touches[0].clientX); }, { passive: true });
  hit.addEventListener("touchend", end);
}

/* =====================================================================
   SUMMARY STRIP
   ===================================================================== */
function renderSummary(products) {
  const wrap = $("#summary");
  const priced = products.filter((p) => p.stats && p.stats.current != null);
  const lows = priced.filter((p) => p.stats.is_all_time_low && p.stats.data_points > 1);
  const failing = products.filter((p) => p.last_error || (p.stats && p.stats.data_points === 0));
  const hits = priced.filter((p) => { const t = effTarget(p); return t != null && p.stats.current <= t; });
  const biggest = priced
    .filter((p) => p.stats.change_pct != null && p.stats.change_pct < 0)
    .sort((a, b) => a.stats.change_pct - b.stats.change_pct)[0];

  const chips = [
    { k: "Tracking", v: products.length },
    { k: "At all-time low", v: lows.length, cls: lows.length ? "good" : "" },
    { k: "Target met", v: hits.length, cls: hits.length ? "good" : "" },
  ];
  if (biggest)
    chips.push({ k: "Biggest drop", v: `${biggest.stats.change_pct.toFixed(1)}%`, cls: "good" });
  if (failing.length)
    chips.push({ k: "Needs attention", v: failing.length, cls: "warn" });

  wrap.innerHTML = chips.map((c) =>
    `<div class="stat-chip ${c.cls || ""}"><div class="k">${c.k}</div><div class="v num">${c.v}</div></div>`
  ).join("");
  wrap.hidden = false;
}

/* =====================================================================
   CARD GRID
   ===================================================================== */
function sortProducts(list) {
  const f = state.filter.toLowerCase();
  let out = list.filter((p) => p.label.toLowerCase().includes(f));
  const g = (p) => p.stats || {};
  const cmp = {
    drop: (a, b) => (g(a).change_pct ?? 0) - (g(b).change_pct ?? 0),
    abovelow: (a, b) => (g(b).pct_above_all_time_low ?? 0) - (g(a).pct_above_all_time_low ?? 0),
    "price-desc": (a, b) => (g(b).current ?? 0) - (g(a).current ?? 0),
    "price-asc": (a, b) => (g(a).current ?? 1e12) - (g(b).current ?? 1e12),
    name: (a, b) => a.label.localeCompare(b.label),
    added: (a, b) => (b.added || "").localeCompare(a.added || ""),
    target: (a, b) => distToTarget(a) - distToTarget(b),
  }[state.sort];
  return out.sort(cmp);
}
function distToTarget(p) {
  const t = effTarget(p), c = p.stats && p.stats.current;
  if (t == null || c == null) return Infinity;
  return Math.max(0, (c - t) / t);
}

function card(p) {
  const s = p.stats || {};
  const cur = s.currency;
  const node = $("#card-tpl").content.cloneNode(true);
  const root = $(".card", node);
  root.dataset.id = p.id;

  $(".card-title", node).textContent = p.label;

  const st = statusOf(p);
  const pill = $(".status", node);
  pill.textContent = st.label;
  pill.className = `pill status ${st.cls}`;

  $(".price-now", node).textContent = money(s.current, cur);
  const d = $(".delta", node);
  if (s.change_pct != null && s.data_points > 1) {
    const dir = s.change_pct < -0.05 ? "down" : s.change_pct > 0.05 ? "up" : "flat";
    d.className = `delta ${dir}`;
    const sign = s.change_abs > 0 ? "+" : "";
    d.textContent = `${sign}${money(s.change_abs, cur)} (${pct(s.change_pct)})`;
  } else d.textContent = "";

  $(".s-low", node).textContent = money(s.all_time_low, cur);
  $(".s-avg", node).textContent = money(s.average, cur);

  const t = effTarget(p);
  const tb = $(".s-target", node);
  if (t == null) { tb.textContent = "set"; tb.className = "s-target none"; }
  else if (s.current != null && s.current <= t) { tb.textContent = `${money(t, cur)} ✓`; tb.className = "s-target met"; }
  else { tb.textContent = money(t, cur); tb.className = "s-target"; }

  const fill = $(".abovebar-fill", node);
  const above = Math.max(0, Math.min(100, s.pct_above_all_time_low ?? 0));
  fill.style.width = (s.all_time_high && s.all_time_low)
    ? Math.max(3, Math.min(100, (s.current - s.all_time_low) / (s.all_time_high - s.all_time_low || 1) * 100)) + "%"
    : "3%";

  if (p.last_error) {
    const n = $(".card-note", node);
    n.hidden = false;
    n.textContent = "Last check failed — " + p.last_error;
  }

  // chart after insertion (needs layout width) — see renderGrid
  return { node, product: p };
}

function renderGrid() {
  const grid = $("#grid");
  grid.innerHTML = "";
  const list = sortProducts(state.data.products);
  if (!list.length) {
    grid.innerHTML = `<p class="empty">${state.data.products.length ? "No products match that filter." : "Nothing tracked yet — hit “Track a product”."}</p>`;
    return;
  }
  const built = list.map(card);
  built.forEach((b) => grid.appendChild(b.node));
  // charts once cards are in the DOM
  built.forEach((b) => {
    const el = grid.querySelector(`.card[data-id="${b.product.id}"] .chart-wrap`);
    const s = b.product.stats || {};
    chart(el, s.series, { low: s.all_time_low, target: effTarget(b.product), cur: s.currency });
  });
  $$(".card", grid).forEach((el) => {
    el.addEventListener("click", () => openDetail(el.dataset.id));
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(el.dataset.id); } });
  });
}

/* =====================================================================
   DETAIL SHEET
   ===================================================================== */
function productById(id) { return state.data.products.find((p) => p.id === id); }

function openDetail(id) {
  const p = productById(id);
  if (!p) return;
  state.detail = id;
  state.range = 0;
  const s = p.stats || {};
  const cur = s.currency;

  $("#d-title").textContent = p.label;
  $("#d-open").href = p.url;
  $("#d-price").textContent = money(s.current, cur);

  const dd = $("#d-delta");
  if (s.change_pct != null && s.data_points > 1) {
    const dir = s.change_pct < -0.05 ? "down" : s.change_pct > 0.05 ? "up" : "flat";
    dd.className = `delta ${dir}`;
    dd.textContent = `${s.change_abs > 0 ? "+" : ""}${money(s.change_abs, cur)} (${pct(s.change_pct)}) since last check`;
  } else dd.textContent = "";

  const st = statusOf(p);
  $("#d-status").textContent = st.label;
  $("#d-status").className = `pill status ${st.cls}`;

  $("#d-low").textContent = money(s.all_time_low, cur);
  $("#d-high").textContent = money(s.all_time_high, cur);
  $("#d-avg").textContent = money(s.average, cur);
  $("#d-median").textContent = money(s.median, cur);
  $("#d-abovelow").textContent = s.pct_above_all_time_low != null ? s.pct_above_all_time_low.toFixed(1) + "%" : "—";
  $("#d-range30").textContent = s.window_30d ? `${money(s.window_30d.min, cur)} – ${money(s.window_30d.max, cur)}` : "—";
  $("#d-points").textContent = s.data_points ?? 0;
  $("#d-since").textContent = fdate(s.tracking_since);

  // target editor
  const t = effTarget(p);
  $("#d-target-cur").textContent = curSymbol(cur);
  $("#d-target-input").value = t != null ? t : "";
  updateTargetHint(p);

  $$("#d-range button").forEach((b) => b.classList.toggle("on", Number(b.dataset.days) === state.range));

  const ov = $("#overlay");
  ov.hidden = false;                 // must be visible before charts measure width
  document.body.style.overflow = "hidden";
  drawDetailChart(p);
  renderHistory(p);
  $("#d-close").focus();
}

function updateTargetHint(p) {
  const s = p.stats || {};
  const t = effTarget(p);
  const hint = $("#d-target-hint");
  if (t == null) { hint.textContent = "No target set."; return; }
  const where = targetFromFile(p)
    ? "From products.json — email alerts are active for this target."
    : "Saved in this browser only. To get email alerts, add \"target\": " + t + " to this product in data/products.json.";
  let rel = "";
  if (s.current != null) {
    rel = s.current <= t
      ? ` ✅ Current price is at or below target (${money(s.current - t, s.currency)}).`
      : ` ${money(s.current - t, s.currency)} to go (${((s.current - t) / t * 100).toFixed(1)}% above).`;
  }
  hint.textContent = where + rel;
}

function drawDetailChart(p) {
  const s = p.stats || {};
  let series = s.series || [];
  if (state.range) {
    const cutoff = Date.now() - state.range * 864e5;
    const f = series.filter((x) => Date.parse(x.date) >= cutoff);
    if (f.length >= 2) series = f;
  }
  chart($("#d-chart"), series, {
    axis: true, hover: true, low: s.all_time_low, target: effTarget(p), cur: s.currency,
  });
}

function renderHistory(p) {
  const s = p.stats || {};
  const rows = (s.series || []).slice().reverse();
  $("#d-hist-count").textContent = rows.length;
  const body = $("#d-hist tbody");
  body.innerHTML = rows.map((r, i) => {
    const prev = rows[i + 1];
    let cell = "<td>—</td>";
    if (prev) {
      const diff = r.price - prev.price;
      const cls = diff < 0 ? "dn" : diff > 0 ? "upp" : "";
      cell = `<td class="${cls}">${diff === 0 ? "—" : (diff > 0 ? "+" : "") + money(diff, r.currency)}</td>`;
    }
    return `<tr><td>${fdate(r.date)}</td><td>${money(r.price, r.currency)}</td>${cell}</tr>`;
  }).join("");
}

function closeDetail() {
  $("#overlay").hidden = true;
  document.body.style.overflow = "";
  state.detail = null;
}

/* ---------- detail events ---------- */
$("#d-close").addEventListener("click", closeDetail);
$("#overlay").addEventListener("click", (e) => { if (e.target === $("#overlay")) closeDetail(); });
$("#add-overlay").addEventListener("click", (e) => { if (e.target === $("#add-overlay")) $("#add-overlay").hidden = true; });
$("#a-close").addEventListener("click", () => { $("#add-overlay").hidden = true; });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeDetail(); $("#add-overlay").hidden = true; }
});
$$("#d-range button").forEach((b) => b.addEventListener("click", () => {
  state.range = Number(b.dataset.days);
  $$("#d-range button").forEach((x) => x.classList.toggle("on", x === b));
  drawDetailChart(productById(state.detail));
}));
$("#d-target-save").addEventListener("click", () => {
  const p = productById(state.detail);
  const v = parseFloat($("#d-target-input").value);
  if (isNaN(v) || v <= 0) return;
  if (targetFromFile(p)) { alert("This target comes from data/products.json. Edit it there to change the alerting target."); return; }
  setLocalTarget(p.id, v);
  updateTargetHint(p); drawDetailChart(p); renderSummary(state.data.products); renderGrid();
});
$("#d-target-clear").addEventListener("click", () => {
  const p = productById(state.detail);
  if (targetFromFile(p)) { alert("Remove the \"target\" field from data/products.json to clear this."); return; }
  setLocalTarget(p.id, null);
  $("#d-target-input").value = "";
  updateTargetHint(p); drawDetailChart(p); renderSummary(state.data.products); renderGrid();
});

/* ---------- add dialog ---------- */
$("#add-btn").addEventListener("click", () => {
  $("#a-workflow").href = `${REPO.base}/actions/workflows/check-prices.yml`;
  $("#a-editfile").href = `${REPO.base}/edit/main/data/products.json`;
  $("#a-snippet").textContent =
`{
  "id": "any-unique-id",
  "url": "https://…the product page…",
  "label": "Short name",
  "target": 0
}`;
  $("#add-overlay").hidden = false;
});

/* ---------- toolbar ---------- */
$("#sort").addEventListener("change", (e) => { state.sort = e.target.value; renderGrid(); });
let ft;
$("#filter").addEventListener("input", (e) => {
  clearTimeout(ft);
  ft = setTimeout(() => { state.filter = e.target.value.trim(); renderGrid(); }, 120);
});
window.addEventListener("resize", () => {
  clearTimeout(window._rz);
  window._rz = setTimeout(() => { renderGrid(); if (state.detail) drawDetailChart(productById(state.detail)); }, 150);
});

/* ---------- boot ---------- */
fetch("dashboard.json", { cache: "no-store" })
  .then((r) => r.json())
  .then((data) => {
    state.data = data;
    $("#updated").textContent =
      `Updated ${fdate(data.generated, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
    $("#foot-count").textContent = `${data.products.length} product${data.products.length === 1 ? "" : "s"}`;
    $("#repo-link").href = REPO.base;
    if (data.products.length) { $("#toolbar").hidden = false; }
    renderSummary(data.products);
    renderGrid();
  })
  .catch((e) => {
    $("#grid").innerHTML = `<p class="empty">Couldn't load dashboard.json — the checker needs to run at least once.</p>`;
    console.error(e);
  });
