// Role: filters and navigation live in the URL query string.
// Connects to: api.js, main.js, views/*.
//
// A link is a view: reloading it reproduces the same slice. Nothing here
// depends on the browser session; `history.replaceState` keeps the URL current
// without filling the back button.

const DEFAULTS = {
  view: "summary",
  start: "",
  end: "",
  sources: [],
  frames: [],
  level: "fine",
  denominator: "all",
  granularity: "month",
  toxMin: 0,
  toxMax: 3,
  q: "",
  dropEmpty: false,
  limit: 50,
  offset: 0,
  months: 12,
};

function splitList(value) {
  if (!value) return [];
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toNumber(value, fallback) {
  if (value === null || value === "" || value === undefined) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function readState() {
  const params = new URLSearchParams(window.location.search);
  return {
    view: params.get("view") || DEFAULTS.view,
    start: params.get("start") || "",
    end: params.get("end") || "",
    sources: splitList(params.get("sources")),
    frames: splitList(params.get("frames")),
    level: params.get("level") === "coarse" ? "coarse" : "fine",
    denominator: params.get("denominator") === "labeled" ? "labeled" : "all",
    granularity: ["month", "week", "day"].includes(params.get("granularity"))
      ? params.get("granularity")
      : DEFAULTS.granularity,
    toxMin: Math.min(3, Math.max(0, toNumber(params.get("toxMin"), DEFAULTS.toxMin))),
    toxMax: Math.min(3, Math.max(0, toNumber(params.get("toxMax"), DEFAULTS.toxMax))),
    q: params.get("q") || "",
    dropEmpty: params.get("dropEmpty") === "1",
    limit: Math.min(200, Math.max(10, toNumber(params.get("limit"), DEFAULTS.limit))),
    offset: Math.max(0, toNumber(params.get("offset"), DEFAULTS.offset)),
    months: Math.min(120, Math.max(1, toNumber(params.get("months"), DEFAULTS.months))),
  };
}

function toSearch(state) {
  const params = new URLSearchParams();
  if (state.view !== DEFAULTS.view) params.set("view", state.view);
  if (state.start) params.set("start", state.start);
  if (state.end) params.set("end", state.end);
  if (state.sources.length) params.set("sources", state.sources.join(","));
  if (state.frames.length) params.set("frames", state.frames.join(","));
  if (state.level !== DEFAULTS.level) params.set("level", state.level);
  if (state.denominator !== DEFAULTS.denominator) {
    params.set("denominator", state.denominator);
  }
  if (state.granularity !== DEFAULTS.granularity) {
    params.set("granularity", state.granularity);
  }
  if (state.toxMin > 0) params.set("toxMin", String(state.toxMin));
  if (state.toxMax < 3) params.set("toxMax", String(state.toxMax));
  if (state.q) params.set("q", state.q);
  if (state.dropEmpty) params.set("dropEmpty", "1");
  if (state.limit !== DEFAULTS.limit) params.set("limit", String(state.limit));
  if (state.offset > 0) params.set("offset", String(state.offset));
  if (state.months !== DEFAULTS.months) params.set("months", String(state.months));
  return params.toString();
}

export function writeState(state, { push = false } = {}) {
  const search = toSearch(state);
  const url = search ? `?${search}` : window.location.pathname;
  if (push) window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
}

export function updateState(patch, options = {}) {
  const state = { ...readState(), ...patch };
  if (!("offset" in patch)) state.offset = 0;
  if (state.toxMin > state.toxMax) {
    [state.toxMin, state.toxMax] = [state.toxMax, state.toxMin];
  }
  writeState(state, options);
  return state;
}

export function resetState() {
  const state = { ...DEFAULTS, view: readState().view };
  writeState(state);
  return state;
}

// Parameters the analytics service understands. UI-only options (view,
// offset, months) are added by the view that needs them.
export function apiParams(state) {
  const params = {};
  if (state.start) params.start = state.start;
  if (state.end) params.end = state.end;
  if (state.sources.length) params.sources = state.sources.join(",");
  if (state.frames.length) params.frames = state.frames.join(",");
  params.level = state.level;
  params.denominator = state.denominator;
  params.granularity = state.granularity;
  if (state.toxMin > 0) params.toxicity_min = state.toxMin;
  if (state.toxMax < 3) params.toxicity_max = state.toxMax;
  if (state.q) params.query = state.q;
  if (state.dropEmpty) params.min_text_length = 1;
  return params;
}

// The chat body mirrors `Filters`, not the query string.
export function filterPayload(state) {
  return {
    start: state.start || null,
    end: state.end || null,
    sources: state.sources,
    frames: state.frames,
    frame_level: state.level,
    toxicity_min: state.toxMin > 0 ? state.toxMin : null,
    toxicity_max: state.toxMax < 3 ? state.toxMax : null,
    query: state.q || null,
    min_text_length: state.dropEmpty ? 1 : null,
  };
}
