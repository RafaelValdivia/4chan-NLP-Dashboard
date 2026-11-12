// Role: bootstrap, URL-driven filter form and view router.
// Connects to: state.js, api.js, ui.js, views/*.
//
// Every view receives a detached stage. A stale render can keep appending to
// its own stage after the user moved on; it can never touch the live one.

import { get, isAbort } from "./api.js";
import {
  apiParams,
  filterPayload,
  readState,
  resetState,
  updateState,
} from "./state.js";
import { badge, el, errorBox, loading, notice } from "./ui.js";
import * as summary from "./views/summary.js";
import * as frames from "./views/frames.js";
import * as toxicity from "./views/toxicity.js";
import * as timeline from "./views/timeline.js";
import * as explore from "./views/explore.js";
import * as quality from "./views/quality.js";
import * as chat from "./views/chat.js";

const VIEWS = { summary, frames, toxicity, timeline, explore, quality, chat };
const NAV = [
  ["summary", "Resumen"],
  ["frames", "Marcos"],
  ["toxicity", "Toxicidad"],
  ["timeline", "Línea de tiempo"],
  ["explore", "Explorar"],
  ["quality", "Calidad"],
  ["chat", "Chat"],
];

let state = readState();
let meta = null;
let renderToken = 0;

const ctx = {
  get state() {
    return state;
  },
  get meta() {
    return meta;
  },
  params(extra = {}) {
    return { ...apiParams(state), ...extra };
  },
  filterPayload() {
    return filterPayload(state);
  },
  update(patch) {
    apply(patch);
  },
  navigate(view) {
    apply({ view }, { push: true });
  },
  frameLabel(label) {
    const list = state.level === "coarse" ? meta.frames.coarse : meta.frames.fine;
    return list.find((item) => item.id === label)?.label || label;
  },
  toxicLabel(level) {
    return (
      meta.toxicity_levels.find((item) => item.level === level)?.label ||
      String(level)
    );
  },
};

function activeForm() {
  return document.getElementById("filters");
}

function checkedValues(container) {
  return [...container.querySelectorAll("input[type=checkbox]:checked")].map(
    (input) => input.value,
  );
}

function apply(patch, options = {}) {
  state = updateState(patch, options);
  if (!VIEWS[state.view]) state = updateState({ view: "summary" });
  syncForm();
  renderFramesPicker();
  renderCurrent();
}

function buildNav() {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";
  for (const [view, label] of NAV) {
    const button = el("button", "nav-button", label);
    button.type = "button";
    button.dataset.view = view;
    button.addEventListener("click", () => ctx.navigate(view));
    nav.append(button);
  }
}

function setActiveNav(view) {
  for (const button of document.querySelectorAll(".nav-button")) {
    button.classList.toggle("active", button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
}

function renderStatus() {
  const box = document.getElementById("status");
  box.innerHTML = "";
  const corpusOk = meta.corpus.available;
  const predictionsOk = meta.predictions.available;
  box.append(
    badge(corpusOk ? "Corpus L0" : "Sin corpus L0", corpusOk ? "ok" : "error"),
    badge(predictionsOk ? "L1 cargado" : "Sin L1", predictionsOk ? "ok" : "warn"),
  );
  if (!corpusOk) {
    box.append(
      notice(
        "No se encontró el almacén L0. Construilo con `keklab ingest l0` o ajustá `KEKLAB_L0_GLOB`.",
        "error",
      ),
    );
  } else if (!predictionsOk) {
    box.append(
      notice(
        "Sin predicciones: marcos, toxicidad y series muestran volumen, no cuotas.",
        "warning",
      ),
    );
  }
}

function renderFramesPicker() {
  const container = document.getElementById("frames-list");
  if (!container || !meta) return;
  container.innerHTML = "";
  const list = state.level === "coarse" ? meta.frames.coarse : meta.frames.fine;
  for (const item of list) {
    const label = el("label", "check");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = item.id;
    input.checked = state.frames.includes(item.id);
    input.addEventListener("change", () => {
      apply({ frames: checkedValues(container) });
    });
    label.append(input, el("span", "", item.label));
    container.append(label);
  }
  const clear = el("button", "button ghost small", "Ninguno");
  clear.type = "button";
  clear.addEventListener("click", () => apply({ frames: [] }));
  container.append(clear);
}

function syncForm() {
  const form = activeForm();
  if (!form) return;
  form.elements.namedItem("start").value = state.start;
  form.elements.namedItem("end").value = state.end;
  form.elements.namedItem("level").value = state.level;
  form.elements.namedItem("denominator").value = state.denominator;
  form.elements.namedItem("granularity").value = state.granularity;
  form.elements.namedItem("toxMin").value = String(state.toxMin);
  form.elements.namedItem("toxMax").value = String(state.toxMax);
  // Do not rewrite the search box under the user's cursor: the debounced
  // apply would otherwise move the caret while typing.
  const query = form.elements.namedItem("q");
  if (document.activeElement !== query) query.value = state.q;
  form.elements.namedItem("dropEmpty").checked = state.dropEmpty;
  for (const input of document.querySelectorAll("#sources input")) {
    input.checked = state.sources.includes(input.value);
  }
  document.getElementById("frames-summary").textContent = state.frames.length
    ? `Marcos (${state.frames.length})`
    : "Marcos";
}

function bindForm() {
  const form = activeForm();
  form.addEventListener("submit", (event) => event.preventDefault());

  form.elements.namedItem("start").addEventListener("change", (event) => {
    apply({ start: event.target.value });
  });
  form.elements.namedItem("end").addEventListener("change", (event) => {
    apply({ end: event.target.value });
  });
  form.elements.namedItem("level").addEventListener("change", (event) => {
    apply({ level: event.target.value, frames: [] });
  });
  form.elements.namedItem("denominator").addEventListener("change", (event) => {
    apply({ denominator: event.target.value });
  });
  form.elements.namedItem("granularity").addEventListener("change", (event) => {
    apply({ granularity: event.target.value });
  });
  form.elements.namedItem("toxMin").addEventListener("change", (event) => {
    apply({ toxMin: Number(event.target.value) });
  });
  form.elements.namedItem("toxMax").addEventListener("change", (event) => {
    apply({ toxMax: Number(event.target.value) });
  });
  form.elements.namedItem("dropEmpty").addEventListener("change", (event) => {
    apply({ dropEmpty: event.target.checked });
  });

  let timer = null;
  form.elements.namedItem("q").addEventListener("input", (event) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => apply({ q: event.target.value.trim() }), 350);
  });

  for (const input of document.querySelectorAll("#sources input")) {
    input.addEventListener("change", () => {
      const sources = [...document.querySelectorAll("#sources input:checked")].map(
        (item) => item.value,
      );
      apply({ sources });
    });
  }

  document.getElementById("reset").addEventListener("click", () => {
    state = resetState();
    syncForm();
    renderFramesPicker();
    renderCurrent();
  });
}

async function renderCurrent() {
  const token = ++renderToken;
  const view = VIEWS[state.view] ? state.view : "summary";
  const app = document.getElementById("app");
  const stage = el("div", "view");
  const loader = loading();
  stage.append(loader);
  app.replaceChildren(stage);
  setActiveNav(view);
  document.title = `${NAV.find(([key]) => key === view)?.[1] || "Analítica"} · 4chan /pol/`;

  try {
    await VIEWS[view].render(stage, ctx);
  } catch (error) {
    if (token !== renderToken || isAbort(error)) return;
    stage.replaceChildren(errorBox(error));
    return;
  }
  if (token === renderToken) loader.remove();
}

async function boot() {
  const status = document.getElementById("status");
  try {
    const payload = await get("meta", "/api/meta");
    meta = payload.data;
  } catch (error) {
    status.append(errorBox(error));
    return;
  }

  renderStatus();
  buildNav();
  renderFramesPicker();
  bindForm();
  syncForm();
  window.addEventListener("popstate", () => {
    state = readState();
    syncForm();
    renderFramesPicker();
    renderCurrent();
  });
  await renderCurrent();
}

boot();
