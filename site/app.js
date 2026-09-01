const grid = document.getElementById("grid");
const tpl = document.getElementById("card-tpl");

function money(v, cur) {
  if (v === null || v === undefined) return "—";
  const code = cur && /^[A-Za-z]{3}$/.test(cur) ? cur.toUpperCase() : null;
  try {
    return new Intl.NumberFormat(undefined, code
      ? { style: "currency", currency: code }
      : { maximumFractionDigits: 2 }).format(v);
  } catch (_) {
    return (cur ? cur + " " : "") + v.toFixed(2);
  }
}

function fmtDate(s) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function sparkline(svg, series, low) {
  const W = 320, H = 80, pad = 6;
  svg.innerHTML = "";
  if (!series || series.length < 2) return;
  const xs = series.map((_, i) => i);
  const ys = series.map(p => p.price);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanY = maxY - minY || 1;
  const X = i => pad + (i / (series.length - 1)) * (W - 2 * pad);
  const Y = v => H - pad - ((v - minY) / spanY) * (H - 2 * pad);

  const pts = series.map((p, i) => `${X(i)},${Y(p.price)}`);
  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("class", "line");
  line.setAttribute("d", "M" + pts.join(" L"));
  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("class", "area");
  area.setAttribute("d", `M${X(0)},${H - pad} L` + pts.join(" L") + ` L${X(series.length - 1)},${H - pad} Z`);
  svg.append(area, line);

  if (low != null && low >= minY && low <= maxY) {
    const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
    ln.setAttribute("class", "low");
    ln.setAttribute("x1", pad); ln.setAttribute("x2", W - pad);
    ln.setAttribute("y1", Y(low)); ln.setAttribute("y2", Y(low));
    svg.append(ln);
  }
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("cx", X(series.length - 1));
  dot.setAttribute("cy", Y(ys[ys.length - 1]));
  dot.setAttribute("r", 2.5);
  svg.append(dot);
}

function statRow(dl, label, value) {
  const wrap = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  wrap.append(dt, dd);
  dl.append(wrap);
}

function render(data) {
  document.getElementById("generated").textContent =
    "updated " + fmtDate(data.generated) + " · " + data.products.length + " tracked";
  grid.innerHTML = "";
  if (!data.products.length) {
    grid.innerHTML = '<p class="empty">Nothing tracked yet. Add a URL to <code>data/products.json</code>.</p>';
    return;
  }
  for (const p of data.products) {
    const s = p.stats || {};
    const cur = s.currency;
    const node = tpl.content.cloneNode(true);
    const a = node.querySelector(".label");
    a.textContent = p.label; a.href = p.url;

    const trend = node.querySelector(".trend");
    if (s.is_all_time_low) { trend.textContent = "all-time low"; trend.classList.add("low"); }
    else trend.textContent = s.trend || "—";

    node.querySelector(".current").textContent = money(s.current, cur);

    const ch = node.querySelector(".change");
    if (s.change_pct != null) {
      const dir = s.change_pct < 0 ? "down" : s.change_pct > 0 ? "up" : "";
      ch.classList.add(dir);
      const sign = s.change_pct > 0 ? "+" : "";
      ch.textContent = `${sign}${money(s.change_abs, cur)} (${sign}${s.change_pct}%)`;
    } else ch.textContent = "";

    sparkline(node.querySelector(".spark"), s.series, s.all_time_low);

    const dl = node.querySelector(".stats");
    statRow(dl, "All-time low", money(s.all_time_low, cur));
    statRow(dl, "All-time high", money(s.all_time_high, cur));
    statRow(dl, "Average", money(s.average, cur));
    statRow(dl, "Median", money(s.median, cur));
    if (s.pct_above_all_time_low != null)
      statRow(dl, "Above low", s.pct_above_all_time_low + "%");
    if (s.window_30d) statRow(dl, "30-day min", money(s.window_30d.min, cur));
    statRow(dl, "Data points", s.data_points ?? 0);
    statRow(dl, "Since", fmtDate(s.tracking_since));

    const err = node.querySelector(".err");
    if (p.last_error) err.textContent = "last check failed: " + p.last_error;
    else if (!s.data_points) err.textContent = s.note || "no data yet";

    grid.appendChild(node);
  }
}

fetch("dashboard.json", { cache: "no-store" })
  .then(r => r.json())
  .then(render)
  .catch(e => {
    grid.innerHTML = '<p class="empty">Could not load dashboard.json — run the checker at least once.</p>';
    console.error(e);
  });
