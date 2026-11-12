// Role: small DOM builders shared by every view.
// Connects to: main.js, views/*.
//
// No framework: each helper returns a node the caller can append. Text always
// goes through textContent, so a post body cannot inject markup.

const numberFormat = new Intl.NumberFormat("es");
const percentFormat = new Intl.NumberFormat("es", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const percentFormat1 = new Intl.NumberFormat("es", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function number(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return numberFormat.format(Number(value));
}

export function percent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return (digits === 1 ? percentFormat1 : percentFormat).format(Number(value));
}

export function dateShort(value) {
  return value ? String(value).slice(0, 10) : "—";
}

export function timestamp(value) {
  return value ? String(value).replace("T", " ").slice(0, 19) : "—";
}

export function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = String(text);
  return node;
}

export function metric(label, value, help = "") {
  const box = el("div", "metric");
  box.append(el("span", "metric-label", label));
  box.append(el("strong", "metric-value", value));
  if (help) box.append(el("span", "metric-help", help));
  return box;
}

export function metrics(items) {
  const grid = el("div", "metrics");
  for (const item of items) {
    grid.append(metric(item.label, item.value, item.help || ""));
  }
  return grid;
}

export function notice(message, kind = "info") {
  return el("div", `notice notice-${kind}`, message);
}

export function badge(text, kind = "neutral") {
  return el("span", `badge badge-${kind}`, text);
}

export function loading(message = "Cargando…") {
  const box = el("div", "loading");
  box.append(el("span", "spinner"));
  box.append(el("span", "", message));
  return box;
}

export function errorBox(error) {
  const box = el("div", "notice notice-error");
  box.append(el("strong", "", "No se pudo cargar la vista. "));
  box.append(document.createTextNode(error?.message || String(error)));
  return box;
}

export function card(title, subtitle = "") {
  const section = el("section", "card");
  if (title) {
    const header = el("div", "card-header");
    header.append(el("h2", "", title));
    if (subtitle) header.append(el("p", "card-subtitle", subtitle));
    section.append(header);
  }
  const body = el("div", "card-body");
  section.append(body);
  return { section, body };
}

export function renderProvenance(container, provenance, extra = "") {
  if (!provenance) return;
  const footer = el("div", "provenance");
  const parts = [];
  if (provenance.n !== undefined && provenance.n !== null) {
    parts.push(`n=${number(provenance.n)}`);
  }
  if (provenance.denominator !== undefined && provenance.denominator !== null) {
    parts.push(`denominador=${number(provenance.denominator)}`);
  }
  if (provenance.run_id) parts.push(`run_id=${provenance.run_id}`);
  if (provenance.generated_utc) {
    parts.push(`generado ${timestamp(provenance.generated_utc)} UTC`);
  }
  if (extra) parts.push(extra);
  if (parts.length) footer.append(el("p", "provenance-line", parts.join(" · ")));
  for (const warning of provenance.warnings || []) {
    footer.append(notice(warning, "warning"));
  }
  container.append(footer);
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export function downloadCSV(rows, columns, filename) {
  if (!rows.length) return;
  const header = columns.map((column) => csvCell(column.label)).join(",");
  const lines = rows.map((row) =>
    columns.map((column) => csvCell(row[column.key])).join(","),
  );
  const blob = new Blob([`${header}\n${lines.join("\n")}\n`], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function table(rows, columns, { filename = "", caption = "" } = {}) {
  const block = el("div", "table-block");
  if (caption) block.append(el("p", "table-caption", caption));
  if (!rows.length) {
    block.append(notice("Sin filas para mostrar."));
    return block;
  }
  const tableNode = el("table", "data-table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of columns) {
    headRow.append(el("th", column.align === "right" ? "right" : "", column.label));
  }
  head.append(headRow);
  tableNode.append(head);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const raw = row[column.key];
      const value = column.format ? column.format(raw, row) : raw ?? "—";
      tr.append(el("td", column.align === "right" ? "right" : "", value));
    }
    body.append(tr);
  }
  tableNode.append(body);

  const scroll = el("div", "table-scroll");
  scroll.append(tableNode);
  block.append(scroll);

  if (filename) {
    const button = el("button", "button ghost small", "Descargar CSV");
    button.type = "button";
    button.addEventListener("click", () => downloadCSV(rows, columns, filename));
    block.append(button);
  }
  return block;
}

export function definitionList(items) {
  const list = el("dl", "definition-list");
  for (const [label, value] of items) {
    list.append(el("dt", "", label));
    list.append(el("dd", "", value));
  }
  return list;
}
