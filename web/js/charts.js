// Role: Plotly wrappers. Views pass data; this module owns the styling.
// Connects to: views/*, /static/plotly.min.js.

const COLORS = [
  "#0b6e4f",
  "#c44536",
  "#1d4e89",
  "#b07d2b",
  "#6a4c93",
  "#2a9d8f",
  "#e76f51",
  "#457b9d",
  "#8d6e63",
  "#7f9c3c",
  "#d1495b",
  "#3d5a80",
  "#a663cc",
  "#4f772d",
  "#bc6c25",
  "#5f0f40",
];

function baseLayout(title, { xTitle = "", yTitle = "", height = 380, xCategory = false } = {}) {
  return {
    title: { text: title, font: { size: 15, color: "#1f2933" }, x: 0, xanchor: "left" },
    height,
    margin: { l: 58, r: 18, t: title ? 46 : 18, b: 48 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, sans-serif", size: 12, color: "#334155" },
    hovermode: "x unified",
    legend: { orientation: "h", y: -0.22, x: 0, font: { size: 11 } },
    xaxis: {
      title: xTitle || undefined,
      type: xCategory ? "category" : undefined,
      gridcolor: "#e5e7eb",
      zeroline: false,
      automargin: true,
    },
    yaxis: {
      title: yTitle || undefined,
      gridcolor: "#e5e7eb",
      zeroline: false,
      automargin: true,
    },
  };
}

function render(div, traces, layout) {
  if (!window.Plotly) {
    div.textContent = "No se pudo cargar Plotly.";
    return;
  }
  window.Plotly.react(div, traces, layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  });
}

function eventBucket(eventDate, granularity, values) {
  if (!values.length) return null;
  const toDate = (value) => {
    if (granularity === "day") return new Date(`${value}T00:00:00Z`);
    if (granularity === "month") return new Date(`${value}-01T00:00:00Z`);
    const match = /^(\d{4})-W(\d{2})$/.exec(value);
    if (!match) return null;
    const year = Number(match[1]);
    const week = Number(match[2]);
    return new Date(Date.UTC(year, 0, 1 + week * 7));
  };
  const target = new Date(`${eventDate}T00:00:00Z`).getTime();
  let best = null;
  let bestDistance = Infinity;
  for (const value of values) {
    const parsed = toDate(value);
    if (!parsed || Number.isNaN(parsed.getTime())) continue;
    const distance = Math.abs(parsed.getTime() - target);
    if (distance < bestDistance) {
      best = value;
      bestDistance = distance;
    }
  }
  return best;
}

export function addEvents(layout, events, values, granularity) {
  if (!events?.length) return layout;
  const shapes = [];
  const annotations = [];
  for (const event of events) {
    const bucket = eventBucket(event.date, granularity, values);
    if (!bucket) continue;
    shapes.push({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: bucket,
      x1: bucket,
      y0: 0,
      y1: 1,
      line: { color: "#b91c1c", width: 1, dash: "dot" },
    });
    annotations.push({
      x: bucket,
      y: 1,
      xref: "x",
      yref: "paper",
      text: event.label,
      showarrow: false,
      xanchor: "left",
      yanchor: "bottom",
      font: { size: 10, color: "#991b1b" },
      bgcolor: "rgba(255,255,255,0.8)",
    });
  }
  layout.shapes = (layout.shapes || []).concat(shapes);
  layout.annotations = (layout.annotations || []).concat(annotations);
  return layout;
}

export function line(div, { x, series, title, yTitle = "", events = [], granularity = "month", yFormat = "" }) {
  const traces = series.map((item, index) => ({
    type: "scatter",
    mode: "lines+markers",
    name: item.name,
    x,
    y: item.y,
    line: { width: 2, color: item.color || COLORS[index % COLORS.length] },
    marker: { size: 4 },
    hovertemplate: `${item.name}: %{y:${yFormat || ".2f"}}<extra></extra>`,
  }));
  const layout = baseLayout(title, { yTitle, xCategory: true });
  if (yFormat === ".0%") layout.yaxis.tickformat = ".0%";
  render(div, traces, addEvents(layout, events, x, granularity));
}

export function bars(
  div,
  { x, y, title, yTitle = "", orientation = "v", text = null, events = [], granularity = "month" },
) {
  const trace = {
    type: "bar",
    x: orientation === "h" ? y : x,
    y: orientation === "h" ? x : y,
    orientation,
    marker: { color: COLORS[0] },
    text: text || undefined,
    textposition: "auto",
    hovertemplate:
      orientation === "h" ? "%{y}: %{x}<extra></extra>" : "%{x}: %{y}<extra></extra>",
  };
  const layout = baseLayout(title, { yTitle, xCategory: orientation !== "h" });
  if (orientation === "h") {
    layout.hovermode = "closest";
    layout.margin.l = 150;
    layout.xaxis.title = yTitle || undefined;
    layout.yaxis.title = undefined;
    layout.yaxis.automargin = true;
  } else {
    layout.xaxis.tickangle = x.length > 8 ? -30 : 0;
  }
  render(div, [trace], addEvents(layout, events, x, granularity));
}

export function groupedBars(div, { x, series, title, yTitle = "", errorBars = false }) {
  const traces = series.map((item, index) => ({
    type: "bar",
    name: item.name,
    x,
    y: item.y,
    marker: { color: item.color || COLORS[index % COLORS.length] },
    error_y: errorBars && item.error ? { type: "data", array: item.error, visible: true } : undefined,
    hovertemplate: `${item.name}: %{y:.2f}%<extra></extra>`,
  }));
  const layout = baseLayout(title, { yTitle, xCategory: true });
  layout.barmode = "group";
  layout.xaxis.tickangle = x.length > 8 ? -30 : 0;
  render(div, traces, layout);
}

export function horizontalBars(div, { labels, values, title, xTitle = "% de posts" }) {
  const trace = {
    type: "bar",
    orientation: "h",
    x: values,
    y: labels,
    marker: { color: COLORS[0] },
    hovertemplate: "%{y}: %{x:.2f}%<extra></extra>",
  };
  const layout = baseLayout(title, { xTitle });
  layout.hovermode = "closest";
  layout.margin.l = 180;
  layout.yaxis.autorange = "reversed";
  layout.xaxis.tickformat = ".0f";
  render(div, [trace], layout);
}

export function purge(div) {
  if (window.Plotly && div?.data) window.Plotly.purge(div);
}
