// View: Chat · the five analytics tools over the same filters as the panel.
//
// The history lives in this module, so switching views does not lose it. It
// is deliberately not persisted: a reload starts a clean conversation, but
// the URL still reproduces the window.

import { post } from "../api.js";
import { bars, line } from "../charts.js";
import {
  card,
  el,
  notice,
  renderProvenance,
  table,
} from "../ui.js";

const history = [];

function figureNode(figure) {
  const plot = el("div", "plot");
  if (!figure?.rows?.length) return plot;
  const isShare = ["cuota", "share", "toxic_share"].includes(figure.y);
  const scale = isShare ? 100 : 1;
  if (figure.kind === "lines") {
    const x = figure.rows.map((row) => row[figure.x]);
    const grouped = new Map();
    for (const row of figure.rows) {
      const key = row.marco || figure.y;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(row);
    }
    const periods = [...new Set(x)];
    const series = [...grouped.entries()].map(([name, rows]) => ({
      name,
      y: periods.map((period) => {
        const found = rows.find((row) => row[figure.x] === period);
        return found ? Number(found[figure.y]) * scale : 0;
      }),
    }));
    line(plot, {
      x: periods,
      series,
      yTitle: isShare ? "% de posts" : figure.y,
      yFormat: isShare ? ".2f" : "d",
    });
    return plot;
  }
  bars(plot, {
    x: figure.rows.map((row) => row[figure.x]),
    y: figure.rows.map((row) => row[figure.y]),
    yTitle: figure.y,
  });
  return plot;
}

function assistantMessage(message) {
  const box = el("div", "chat-message assistant");
  const head = el("div", "chat-head");
  head.append(el("span", "chat-role", "Asistente"));
  if (message.tool) head.append(el("span", "badge", message.tool));
  box.append(head);
  box.append(el("div", "chat-text", message.text || ""));
  if (message.figure) box.append(figureNode(message.figure));
  if (message.table?.length) {
    box.append(
      table(message.table, Object.keys(message.table[0]).map((key) => ({ key, label: key }))),
    );
  }
  if (message.provenance) renderProvenance(box, message.provenance);
  return box;
}

function userMessage(message) {
  const box = el("div", "chat-message user");
  const head = el("div", "chat-head");
  head.append(el("span", "chat-role", "Vos"));
  box.append(head);
  box.append(el("div", "chat-text", message.text));
  return box;
}

export async function render(root, ctx) {
  const intro = card(
    "Chat analítico",
    "Usa los mismos filtros que el resto del panel. Comandos explícitos: " +
      ctx.meta.tools.map((tool) => `/${tool.name}`).join(", "),
  );
  const help = document.createElement("details");
  help.append(el("summary", "", "Qué hace cada herramienta"));
  const list = el("ul", "tool-list");
  for (const tool of ctx.meta.tools) {
    list.append(el("li", "", `/${tool.name}: ${tool.help}`));
  }
  help.append(list);
  intro.body.append(help);
  intro.body.append(
    notice(
      "Las respuestas usan los filtros vigentes al momento de preguntar. " +
        "El enrutado es por reglas; el modelo local solo interviene en /clasificar.",
      "info",
    ),
  );
  root.append(intro.section);

  const transcript = el("div", "chat-transcript");
  root.append(transcript);

  function renderMessages() {
    transcript.innerHTML = "";
    if (!history.length) {
      transcript.append(
        notice("Probá «cuántos posts hay», «resumime la ventana» o «/entidades».", "info"),
      );
      return;
    }
    for (const message of history) {
      transcript.append(
        message.role === "user" ? userMessage(message) : assistantMessage(message),
      );
    }
    transcript.scrollTop = transcript.scrollHeight;
  }

  const form = el("form", "chat-form");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Preguntá sobre el corpus…";
  input.autocomplete = "off";
  const send = el("button", "button", "Enviar");
  send.type = "submit";
  form.append(input, send);

  async function submit(question) {
    const text = question.trim();
    if (!text) return;
    history.push({ role: "user", text });
    renderMessages();
    input.value = "";
    send.disabled = true;
    input.disabled = true;
    transcript.append(el("div", "chat-thinking", "Pensando…"));

    try {
      const result = await post("chat", "/api/chat", {
        question: text,
        filters: ctx.filterPayload(),
      });
      history.push({
        role: "assistant",
        text: result.data.text,
        tool: result.data.tool,
        figure: result.data.figure,
        table: result.data.table,
        provenance: result.provenance,
      });
    } catch (error) {
      if (error.name === "AbortError") return;
      history.push({
        role: "assistant",
        text: `No pude responder: ${error.message}`,
        tool: "error",
      });
    } finally {
      send.disabled = false;
      input.disabled = false;
      input.focus();
      renderMessages();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(input.value);
  });
  root.append(form);

  renderMessages();
  input.focus();

  // A view re-render (filter change) should preserve the transcript but stop
  // showing a stale error panel.
  if (transcript.childElementCount === 0) renderMessages();
}
