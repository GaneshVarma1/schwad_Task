import {
  linkStatus,
  destinationHost,
  fillDays,
  chartGeometry,
  nearestPoint,
  createPayload,
  paginationLabel,
  requestKey,
} from "./dashboard-core.mjs";

const paths = {
  link: "M10 13a5 5 0 0 0 7 .5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  chart: "M4 3v17h17M8 15v-4M13 15V7M18 15V4",
  lock: "M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4M12 14v3",
  book: "M4 3h13a2 2 0 0 1 2 2v16H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3M3 17h16M8 7h7M8 10h5",
  external:
    "M14 3h7v7M21 3l-11 11M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5",
  user: "M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3M8 12l3 3 5-6",
  plus: "M12 5v14M5 12h14",
  refresh:
    "M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2l1 4M4 12l1 4a8 8 0 0 0 13 2",
  cursor: "m4 3 6 17 3-7 7-3L4 3M13 13l6 6",
  activity: "M3 12h4l3-8 4 16 3-8h4",
  sun: "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1",
  search: "M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0M15 15l6 6",
  sort: "M8 4v16M4 16l4 4 4-4M16 20V4M12 8l4-4 4 4",
  left: "m14 6-6 6 6 6",
  right: "m10 6 6 6-6 6",
  close: "m6 6 12 12M6 18 18 6",
  copy: "M9 9h12v12H9zM15 5V3H3v12h2",
  pause: "M8 5v14M16 5v14",
  trending: "m3 17 6-6 4 4 8-11M15 4h6v6",
  sparkles: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3",
  moon: "M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5",
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const number = (value) => Number(value || 0).toLocaleString("en-US");
const prettyDate = (value) =>
  new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
const state = {
  key: "",
  demo: false,
  connected: false,
  days: 30,
  status: "all",
  query: "",
  offset: 0,
  limit: 7,
  epoch: 0,
  items: [],
  summary: null,
  disableCode: null,
  detailEpoch: 0,
  pendingKey: null,
  pendingPayload: null,
};
const ns = "http://www.w3.org/2000/svg";
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function svgElement(tag, attrs = {}) {
  const node = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attrs))
    node.setAttribute(key, String(value));
  return node;
}
function icon(name) {
  const svg = svgElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    "aria-hidden": "true",
    class: "icon",
  });
  svg.append(svgElement("path", { d: paths[name] || paths.link }));
  return svg;
}
$$("[data-icon]").forEach((node) => node.append(icon(node.dataset.icon)));
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 4200);
}
function showError(selector, message) {
  const node = $(selector);
  node.textContent = message || "";
  node.hidden = !message;
}
function button(label, iconName, handler, className = "icon-button") {
  const b = el("button", undefined, className);
  b.type = "button";
  b.setAttribute("aria-label", label);
  b.title = label;
  if (iconName) b.append(icon(iconName));
  b.addEventListener("click", handler);
  return b;
}
function badge(status) {
  return el(
    "span",
    status[0].toUpperCase() + status.slice(1),
    `status-badge status-${status}`,
  );
}
function setConnection(connected) {
  state.connected = connected;
  $("#connection-state").classList.toggle("connected", connected);
  $("#connection-state").replaceChildren(
    el("span"),
    document.createTextNode(
      connected
        ? state.demo
          ? "Demo workspace"
          : "Connected"
        : "Not connected",
    ),
  );
  $("#profile-name").textContent = state.demo
    ? "Demo workspace"
    : connected
      ? "Workspace connected"
      : "Workspace access";
  $("#profile-status").textContent = state.demo
    ? "Synthetic sandbox"
    : connected
      ? "Key held in memory"
      : "Connect to your service";
  $("#disconnect").hidden = !connected || state.demo;
}
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const dark = theme === "dark";
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", dark ? "#102634" : "#006fba");
  const toggle = $("#theme-toggle");
  toggle.replaceChildren(icon(dark ? "sun" : "moon"));
  const label = dark ? "Switch to light mode" : "Switch to dark mode";
  toggle.setAttribute("aria-label", label);
  toggle.title = label;
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(state.key ? { Authorization: `Bearer ${state.key}` } : {}),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    let message =
      data.detail || `Request failed (${response.status}). Please try again.`;
    if (response.status === 401)
      message = "Your API key is missing or invalid. Reconnect your workspace.";
    if (response.status === 422) {
      const field = data.errors?.[0]?.field?.at(-1);
      message =
        field === "url"
          ? "Enter a public HTTP or HTTPS URL without credentials or spaces."
          : field === "custom_alias"
            ? "Use 4–32 letters, numbers, hyphens or underscores. Reserved aliases are not allowed."
            : data.detail === "Invalid request"
              ? "Check your input and try again."
              : data.detail;
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
let chartId = 0;
function renderChart(target, daily) {
  const g = chartGeometry(daily);
  const svg = svgElement("svg", {
    viewBox: `0 0 ${g.width} ${g.height}`,
    class: "chart-svg",
    role: "img",
    "aria-label": `${number(daily.reduce((a, b) => a + b.clicks, 0))} clicks over ${daily.length} days. Counts by UTC day.`,
  });
  const title = svgElement("title");
  title.textContent = "Daily clicks, UTC";
  svg.append(title);
  const gradientId = `area-gradient-${++chartId}`;
  const defs = svgElement("defs");
  const gradient = svgElement("linearGradient", {
    id: gradientId,
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
  });
  gradient.append(
    svgElement("stop", {
      offset: "0%",
      "stop-color": "#00a0df",
      "stop-opacity": ".18",
    }),
    svgElement("stop", {
      offset: "100%",
      "stop-color": "#00a0df",
      "stop-opacity": ".01",
    }),
  );
  defs.append(gradient);
  svg.append(defs);
  for (let i = 0; i <= 4; i++) {
    const y = g.top + ((g.baseline - g.top) * i) / 4;
    svg.append(
      svgElement("line", {
        x1: g.left,
        x2: g.width - g.right,
        y1: y,
        y2: y,
        class: "chart-grid",
      }),
    );
    const text = svgElement("text", {
      x: g.left - 9,
      y: y + 4,
      "text-anchor": "end",
    });
    text.textContent = number(Math.round(g.ceiling * (1 - i / 4)));
    svg.append(text);
  }
  if (g.points.length) {
    const line = g.points
      .map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
      .join(" ");
    svg.append(
      svgElement("path", {
        d: `${line} L${g.points.at(-1).x},${g.baseline} L${g.points[0].x},${g.baseline} Z`,
        fill: `url(#${gradientId})`,
      }),
    );
    svg.append(svgElement("path", { d: line, class: "chart-line" }));
    const indices = [
      ...new Set([
        0,
        Math.floor((daily.length - 1) / 3),
        Math.floor(((daily.length - 1) * 2) / 3),
        daily.length - 1,
      ]),
    ];
    for (const i of indices) {
      const point = g.points[i];
      const text = svgElement("text", {
        x: point.x,
        y: g.height - 7,
        "text-anchor":
          i === 0 ? "start" : i === daily.length - 1 ? "end" : "middle",
      });
      text.textContent = new Date(point.date + "T00:00:00Z").toLocaleDateString(
        "en-US",
        { month: "short", day: "numeric", timeZone: "UTC" },
      );
      svg.append(text);
    }
    for (const point of g.points) {
      const circle = svgElement("circle", {
        cx: point.x,
        cy: point.y,
        r: daily.length <= 7 ? 3 : 1.5,
        class: "chart-point",
      });
      const t = svgElement("title");
      t.textContent = `${point.date}: ${number(point.clicks)} clicks`;
      circle.append(t);
      svg.append(circle);
    }
  }
  const tooltip = el("div", undefined, "chart-tooltip");
  tooltip.hidden = true;
  const showTooltip = (point) => {
    if (!point) return;
    tooltip.replaceChildren(
      el(
        "strong",
        new Date(point.date + "T00:00:00Z").toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
          timeZone: "UTC",
        }),
      ),
      el("span", `${number(point.clicks)} clicks`),
    );
    tooltip.style.left = `${Math.max(10, Math.min(90, (point.x / g.width) * 100))}%`;
    tooltip.style.top = `${Math.max(8, (point.y / g.height) * 100)}%`;
    tooltip.style.transform =
      point.y < 50
        ? "translate(-50%, 10px)"
        : "translate(-50%, calc(-100% - 10px))";
    tooltip.hidden = false;
  };
  svg.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const x = ((event.clientX - rect.left) / rect.width) * g.width;
    showTooltip(nearestPoint(g.points, x));
  });
  svg.addEventListener("pointerleave", () => {
    tooltip.hidden = true;
  });
  target.replaceChildren(svg, tooltip);
  const details = el("details", undefined, "chart-data");
  details.append(el("summary", "View daily counts"));
  const table = el("table");
  const head = el("thead");
  const tr = el("tr");
  tr.append(el("th", "Date (UTC)"), el("th", "Clicks"));
  head.append(tr);
  const body = el("tbody");
  for (const row of daily) {
    const tr = el("tr");
    tr.append(el("td", row.date), el("td", number(row.clicks)));
    body.append(tr);
  }
  table.append(head, body);
  details.append(table);
  target.append(details);
}
function renderSummary(summary) {
  state.summary = summary;
  $("#metric-clicks").textContent = number(summary.total_clicks);
  $("#metric-links").textContent = number(summary.total_links);
  $("#metric-active").textContent = number(summary.active_links);
  $("#metric-today").textContent = number(summary.clicks_today);
  $("#nav-count").textContent = number(summary.total_links);
  $("#chart-total").textContent = number(
    summary.daily.reduce((sum, p) => sum + p.clicks, 0),
  );
  renderChart($("#activity-chart"), summary.daily);
  const top = $("#top-links");
  top.replaceChildren();
  if (!summary.top_links.length) {
    top.append(
      el(
        "div",
        "Create a link to start seeing your top destinations.",
        "small-empty",
      ),
    );
    return;
  }
  summary.top_links.forEach((link, index) => {
    const row = button(
      `View analytics for ${link.code}`,
      null,
      () => openDetails(link.code),
      "top-link",
    );
    row.append(el("span", String(index + 1).padStart(2, "0"), "rank"));
    const info = el("span", undefined, "top-info");
    info.append(
      el("strong", link.code),
      el("small", destinationHost(link.url)),
    );
    row.append(info, el("span", number(link.total_clicks), "top-clicks"));
    top.append(row);
  });
}
async function copyLink(url) {
  try {
    await navigator.clipboard.writeText(url);
    toast("Short link copied to clipboard.");
  } catch {
    toast("Clipboard access is unavailable. Select and copy the short link.");
  }
}
function renderLinks(page) {
  state.items = page.items;
  $("#link-total").textContent = number(page.total);
  const rows = $("#link-rows");
  rows.replaceChildren();
  page.items.forEach((link, index) => {
    const row = el("tr");
    const destination = el("td");
    const group = el("div", undefined, "destination-cell");
    const mark = el("span", undefined, `domain-icon domain-${index % 4}`);
    mark.append(icon("link"));
    const text = el("div", undefined, "destination-copy");
    const title = button(
      `View ${link.code}`,
      null,
      () => openDetails(link.code),
      "",
    );
    title.textContent = link.code;
    const url = el("small", link.url);
    url.title = link.url;
    text.append(title, url);
    group.append(mark, text);
    destination.append(group);
    const short = el("td");
    const wrap = el("div", undefined, "short-link");
    const anchor = el("a", new URL(link.short_url).host + "/" + link.code);
    anchor.href = link.short_url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.title = link.short_url;
    wrap.append(
      anchor,
      button(`Copy ${link.code}`, "copy", () => copyLink(link.short_url)),
    );
    short.append(wrap);
    const clicks = el("td", number(link.total_clicks), "numeric click-count");
    const status = el("td");
    status.append(badge(link.status));
    const date = el("td", prettyDate(link.created_at), "created-at");
    const actions = el("td");
    const buttons = el("div", undefined, "row-actions");
    buttons.append(
      button(`Analytics for ${link.code}`, "chart", () =>
        openDetails(link.code),
      ),
    );
    if (link.status === "active")
      buttons.append(
        button(`Disable ${link.code}`, "pause", () => askDisable(link.code)),
      );
    actions.append(buttons);
    row.append(destination, short, clicks, status, date, actions);
    rows.append(row);
  });
  const empty = $("#empty-state");
  empty.hidden = page.total > 0;
  const filtered = !!state.query || state.status !== "all";
  if (!page.total) {
    empty.querySelector("h3").textContent = !state.connected
      ? "Connect to your link workspace."
      : filtered
        ? "No links match your search."
        : "Your next great link starts here.";
    empty.querySelector("p").textContent = !state.connected
      ? "Use your API key to see your links, create new ones, and explore analytics."
      : filtered
        ? "Try another search or choose a different status."
        : "Create a short link to share your destination and start tracking clicks.";
    empty.querySelector("button").hidden = filtered;
  }
  $("#pagination-label").textContent = paginationLabel(
    page.total,
    state.offset,
    state.limit,
  );
  $("#previous-page").disabled = state.offset === 0;
  $("#next-page").disabled = state.offset + state.limit >= page.total;
}
async function refresh() {
  if (!state.demo && !state.key) return;
  const epoch = ++state.epoch;
  $("#refresh").disabled = true;
  $(".links-panel").setAttribute("aria-busy", "true");
  try {
    const params = new URLSearchParams({
      q: state.query,
      status: state.status,
      offset: state.offset,
      limit: state.limit,
    });
    const [summary, page] = await Promise.all([
      api(`/api/v1/dashboard?days=${state.days}`),
      api(`/api/v1/links?${params}`),
    ]);
    if (epoch !== state.epoch) return;
    if (page.total && state.offset >= page.total) {
      state.offset = Math.floor((page.total - 1) / state.limit) * state.limit;
      return refresh();
    }
    setConnection(true);
    renderSummary(summary);
    renderLinks(page);
    showError("#page-error", "");
    $("#last-updated").textContent =
      `Updated ${new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
  } catch (error) {
    if (epoch !== state.epoch) return;
    showError("#page-error", error.message);
    if (error.status === 401) {
      disconnect(false);
      showError("#connect-error", error.message);
      openDialog("#connect-dialog");
    }
  } finally {
    if (epoch === state.epoch) {
      $("#refresh").disabled = false;
      $(".links-panel").setAttribute("aria-busy", "false");
    }
  }
}
function openDialog(selector) {
  const dialog = $(selector);
  if (!dialog.open) dialog.showModal();
}
function disconnect(notify = true) {
  state.key = "";
  state.summary = null;
  state.epoch++;
  state.detailEpoch++;
  state.offset = 0;
  setConnection(false);
  $("#api-key").value = "";
  ["clicks", "links", "active", "today"].forEach(
    (name) => ($("#metric-" + name).textContent = "—"),
  );
  $("#chart-total").textContent = "—";
  $("#nav-count").textContent = "—";
  $("#activity-chart").replaceChildren(
    el(
      "div",
      "Connect your workspace to see click activity.",
      "chart-placeholder",
    ),
  );
  $("#top-links").replaceChildren(
    el("div", "Your top links will appear here.", "small-empty"),
  );
  $("#details-content").replaceChildren();
  $("#details-dialog").close();
  renderLinks({ items: [], total: 0 });
  $("#refresh").disabled = false;
  $(".links-panel").setAttribute("aria-busy", "false");
  if (notify) toast("Workspace disconnected.");
}
$$(".close-dialog").forEach((node) =>
  node.addEventListener("click", () => node.closest("dialog").close()),
);
$$("dialog").forEach((dialog) =>
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      )
        dialog.close();
    }
  }),
);
$("#connection-button").addEventListener("click", () =>
  state.demo
    ? toast(
        "You’re exploring an isolated demo. Sample data may reset when the demo runtime restarts.",
      )
    : openDialog("#connect-dialog"),
);
$("#disconnect").addEventListener("click", () => {
  disconnect();
  $("#connect-dialog").close();
});
$("#connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  showError("#connect-error", "");
  state.key = $("#api-key").value.trim();
  try {
    await api("/api/v1/dashboard?days=1");
    $("#api-key").value = "";
    $("#connect-dialog").close();
    await refresh();
    toast("Workspace connected.");
  } catch (error) {
    disconnect(false);
    showError("#connect-error", error.message);
  } finally {
    submit.disabled = false;
  }
});
function openCreate() {
  if (!state.connected) {
    openDialog("#connect-dialog");
    return;
  }
  showError("#create-error", "");
  openDialog("#create-dialog");
  $("#destination").focus();
}
$$(".create-trigger").forEach((node) =>
  node.addEventListener("click", openCreate),
);
$("#alias").addEventListener("input", () => {
  $("#link-preview").textContent =
    state.baseUrl + "/" + ($("#alias").value || "your-short-link");
});
$("#create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = $("#create-submit");
  showError("#create-error", "");
  try {
    const payload = createPayload(
      $("#destination").value,
      $("#alias").value,
      $("#expiry").value,
    );
    const serialized = JSON.stringify(payload);
    if (serialized !== state.pendingPayload) {
      state.pendingPayload = serialized;
      state.pendingKey = requestKey();
    }
    submit.disabled = true;
    submit.textContent = "Creating…";
    const result = await api("/api/v1/links", {
      method: "POST",
      body: serialized,
      headers: { "Idempotency-Key": state.pendingKey },
    });
    $("#create-dialog").close();
    $("#create-form").reset();
    state.pendingKey = null;
    state.pendingPayload = null;
    state.query = "";
    state.status = "all";
    state.offset = 0;
    $("#search").value = "";
    updateFilters();
    toast("Your short link is ready.");
    await refresh();
    await openDetails(result.code);
  } catch (error) {
    showError("#create-error", error.message);
  } finally {
    submit.disabled = false;
    submit.replaceChildren(
      document.createTextNode("Create link"),
      icon("right"),
    );
  }
});
async function openDetails(code) {
  const epoch = ++state.detailEpoch;
  $("#details-title").textContent = code;
  $("#details-content").replaceChildren(
    el("div", "Loading link analytics…", "small-empty"),
  );
  openDialog("#details-dialog");
  try {
    const [link, stats] = await Promise.all([
      api(`/api/v1/links/${encodeURIComponent(code)}`),
      api(`/api/v1/links/${encodeURIComponent(code)}/analytics`),
    ]);
    if (epoch !== state.detailEpoch) return;
    const container = $("#details-content");
    container.replaceChildren(badge(linkStatus(link)));
    const short = el("a", link.short_url, "detail-url");
    short.href = link.short_url;
    short.target = "_blank";
    short.rel = "noopener noreferrer";
    container.append(
      short,
      el("p", "DESTINATION", "detail-label"),
      el("p", link.url, "detail-destination"),
    );
    const statrow = el("div", undefined, "detail-stats");
    const count = el("div");
    count.append(
      el("strong", number(stats.total_clicks)),
      el("span", "All-time clicks"),
    );
    const date = el("div");
    date.append(
      el(
        "strong",
        new Date(link.created_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          timeZone: "UTC",
        }),
      ),
      el("span", "Created · UTC"),
    );
    statrow.append(count, date);
    container.append(statrow);
    const chart = el("div", undefined, "detail-chart");
    chart.append(el("p", "Last 30 days", "detail-chart-title"));
    const chartBody = el("div");
    renderChart(chartBody, fillDays(stats.daily, 30));
    chart.append(chartBody);
    container.append(chart);
    if (link.expires_at)
      container.append(
        el(
          "p",
          `Expires ${new Date(link.expires_at).toLocaleString()}`,
          "details-note",
        ),
      );
    const actions = el("div", undefined, "details-actions");
    const copy = button(
      "Copy short link",
      "copy",
      () => copyLink(link.short_url),
      "button primary",
    );
    copy.append(document.createTextNode("Copy short link"));
    actions.append(copy);
    if (linkStatus(link) === "active") {
      const disable = button(
        "Disable link",
        "pause",
        () => askDisable(code),
        "button secondary",
      );
      disable.append(document.createTextNode("Disable link"));
      actions.append(disable);
    }
    container.append(
      actions,
      el(
        "p",
        "Counts include repeat requests and bots. Opening a short link records a click.",
        "details-note",
      ),
    );
  } catch (error) {
    if (epoch === state.detailEpoch)
      $("#details-content").replaceChildren(
        el("p", error.message, "form-error"),
      );
  }
}
function askDisable(code) {
  state.disableCode = code;
  $("#disable-code").textContent = code;
  showError("#disable-error", "");
  openDialog("#disable-dialog");
}
$("#confirm-disable").addEventListener("click", async () => {
  const btn = $("#confirm-disable");
  btn.disabled = true;
  showError("#disable-error", "");
  try {
    await api(`/api/v1/links/${encodeURIComponent(state.disableCode)}`, {
      method: "DELETE",
    });
    $("#disable-dialog").close();
    toast("Link disabled. Your analytics are preserved.");
    if ($("#details-dialog").open) await openDetails(state.disableCode);
    await refresh();
  } catch (error) {
    showError("#disable-error", error.message);
  } finally {
    btn.disabled = false;
  }
});
function updateFilters() {
  $$(".filter").forEach((button) => {
    const active = button.dataset.status === state.status;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}
$$(".filter").forEach((button) =>
  button.addEventListener("click", () => {
    state.status = button.dataset.status;
    state.offset = 0;
    updateFilters();
    refresh();
  }),
);
let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  state.query = $("#search").value;
  state.offset = 0;
  searchTimer = setTimeout(refresh, 230);
});
$("#previous-page").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  refresh();
});
$("#next-page").addEventListener("click", () => {
  state.offset += state.limit;
  refresh();
});
$("#chart-days").addEventListener("change", () => {
  state.days = Number($("#chart-days").value);
  refresh();
});
$("#refresh").addEventListener("click", () =>
  state.connected ? refresh() : openDialog("#connect-dialog"),
);
$("#theme-toggle").addEventListener("click", () => {
  const next =
    document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("schwab-link-theme", next);
  setTheme(next);
});
function setView() {
  const view = ["overview", "links", "analytics"].includes(
    location.hash.slice(1),
  )
    ? location.hash.slice(1)
    : "overview";
  document.body.classList.remove("view-links", "view-analytics");
  if (view !== "overview") document.body.classList.add("view-" + view);
  const names = {
    overview: "Overview",
    links: "All links",
    analytics: "Analytics",
  };
  $("#page-title").textContent = names[view];
  $("#breadcrumb-view").textContent = names[view];
  $("#page-subtitle").textContent = {
    overview: "Every link, and the impact behind it.",
    links: "Create, share, and manage your destinations.",
    analytics: "Understand the activity behind every connection.",
  }[view];
  $$("[data-view]").forEach((link) => {
    const active = link.dataset.view === view;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.title = `${names[view]} · Schwab Link Manager`;
}
window.addEventListener("hashchange", setView);
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !event.ctrlKey &&
    !event.metaKey &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) &&
    !$$("dialog[open]").length
  ) {
    event.preventDefault();
    location.hash = "links";
    $("#search").focus();
  }
});
async function initialize() {
  const savedTheme = localStorage.getItem("schwab-link-theme");
  setTheme(
    savedTheme ||
      (window.matchMedia?.("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"),
  );
  setView();
  try {
    const config = await api("/api/v1/ui-config");
    state.demo = config.demo;
    state.baseUrl = config.base_url.replace(/\/$/, "");
    $("#link-preview").textContent = state.baseUrl + "/your-short-link";
    $("#demo-banner").hidden = !state.demo;
    if (state.demo) await refresh();
    else {
      renderLinks({ items: [], total: 0 });
      openDialog("#connect-dialog");
    }
  } catch (error) {
    showError(
      "#page-error",
      `Unable to connect to the service. ${error.message}`,
    );
  }
}
initialize();
