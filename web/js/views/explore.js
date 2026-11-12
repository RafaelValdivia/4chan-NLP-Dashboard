// View: Explorar · literal text search inside the active window.
// Removable module: it is the only view that reads post bodies.

import { get } from "../api.js";
import {
  card,
  dateShort,
  el,
  notice,
  number,
  renderProvenance,
  table,
} from "../ui.js";

export async function render(root, ctx) {
  const search = el("form", "search-form");
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = "Texto literal a buscar (sin distinguir mayúsculas)";
  input.value = ctx.state.q;
  const submit = el("button", "button", "Buscar");
  submit.type = "submit";
  search.append(input, submit);
  search.addEventListener("submit", (event) => {
    event.preventDefault();
    ctx.update({ q: input.value.trim() });
  });
  root.append(search);

  if (!ctx.state.q) {
    root.append(
      notice(
        "Escribí un texto para buscar dentro de la ventana activa. " +
          "El filtro se aplica también a las demás vistas.",
        "info",
      ),
    );
    return;
  }

  const params = ctx.params({
    limit: ctx.state.limit,
    offset: ctx.state.offset,
  });
  const result = await get("explore-search", "/api/search", params);

  const header = card(
    "Resultados",
    `${number(result.provenance.n)} en esta página · desde ${number(ctx.state.offset)}`,
  );
  const rows = result.data.map((row) => ({
    post_id: row.post_id,
    thread_id: row.thread_id,
    date: dateShort(row.timestamp_utc),
    is_op: row.is_op ? "Sí" : "No",
    text: row.text || "",
    text_short: row.text ? row.text.slice(0, 500) : "—",
  }));

  header.body.append(
    table(
      rows,
      [
        { key: "post_id", label: "Post", align: "right" },
        { key: "thread_id", label: "Hilo", align: "right" },
        { key: "date", label: "Fecha" },
        { key: "is_op", label: "OP" },
        { key: "text_short", label: "Texto" },
      ],
      { filename: "posts.csv" },
    ),
  );

  const navigation = el("div", "pager");
  const previous = el("button", "button ghost", "Anterior");
  previous.type = "button";
  previous.disabled = ctx.state.offset === 0;
  previous.addEventListener("click", () => {
    ctx.update({ offset: Math.max(0, ctx.state.offset - ctx.state.limit) });
  });
  const next = el("button", "button ghost", "Siguiente");
  next.type = "button";
  next.disabled = result.data.length < ctx.state.limit;
  next.addEventListener("click", () => {
    ctx.update({ offset: ctx.state.offset + ctx.state.limit });
  });
  const pageSize = el("label", "page-size", "Resultados por página ");
  const size = document.createElement("select");
  for (const value of [10, 25, 50, 100, 200]) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    option.selected = value === ctx.state.limit;
    size.append(option);
  }
  size.addEventListener("change", () => {
    ctx.update({ limit: Number(size.value), offset: 0 });
  });
  pageSize.append(size);
  navigation.append(previous, next, pageSize);
  header.body.append(navigation);

  root.append(header.section);
  renderProvenance(root, result.provenance);
}
