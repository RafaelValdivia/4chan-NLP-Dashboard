// View: Marcos · fine/coarse distribution with uncertainty and the previous
// window as baseline.

import { get } from "../api.js";
import { groupedBars, horizontalBars } from "../charts.js";
import {
  card,
  el,
  metrics,
  notice,
  number,
  percent,
  renderProvenance,
  table,
} from "../ui.js";

export async function render(root, ctx) {
  const params = ctx.params();

  if (!ctx.meta.predictions.available) {
    const overview = await get("frames-overview", "/api/overview", params);
    root.append(
      notice(
        "Todavía no hay predicciones L1 sobre el corpus: el clasificador aún no se aplicó a L0. " +
          "Esta vista mostrará la distribución de marcos en cuanto exista el primer run de predicciones.",
        "info",
      ),
    );
    const box = card("Mientras tanto: volumen de la ventana");
    box.body.append(
      metrics([
        { label: "Posts", value: number(overview.data.posts) },
        { label: "Hilos", value: number(overview.data.threads) },
        { label: "Meses", value: number(overview.data.months) },
      ]),
    );
    root.append(box.section);
    renderProvenance(root, overview.provenance);
    return;
  }

  const [distribution, comparison] = await Promise.all([
    get("frames-distribution", "/api/frames", params),
    get("frames-compare", "/api/compare", {
      ...params,
      months: ctx.state.months,
    }),
  ]);

  const rows = distribution.data
    .filter((row) => row.count > 0)
    .map((row) => ({
      label: row.label,
      label_es: ctx.frameLabel(row.label),
      count: row.count,
      share: row.share,
      ic_low: row.wilson?.low ?? null,
      ic_high: row.wilson?.high ?? null,
    }));

  const chart = card(
    ctx.state.level === "fine" ? "Marcos finos" : "Cabeceras gruesas",
    `Denominador: ${ctx.state.denominator === "all" ? "todos los posts" : "solo posts predichos"}`,
  );
  const plot = el("div", "plot");
  chart.body.append(plot);
  root.append(chart.section);

  if (rows.length) {
    horizontalBars(plot, {
      labels: rows.map((row) => row.label_es),
      values: rows.map((row) => row.share * 100),
      title: "",
    });
  } else {
    plot.remove();
    chart.body.append(notice("Ninguna predicción cae dentro del filtro."));
  }

  const tableCard = card(
    "Tabla de marcos",
    "La cuota es sobre el denominador elegido; el IC es Wilson al 95 %.",
  );
  tableCard.body.append(
    table(
      rows,
      [
        { key: "label_es", label: "Marco" },
        { key: "count", label: "Posts", align: "right", format: number },
        { key: "share", label: "Cuota", align: "right", format: (value) => percent(value) },
        {
          key: "ic_low",
          label: "IC 95 %",
          align: "right",
          format: (value, row) =>
            value === null ? "—" : `${percent(row.ic_low)}–${percent(row.ic_high)}`,
        },
      ],
      { filename: "marcos.csv" },
    ),
  );
  root.append(tableCard.section);

  const compareCard = card(
    "Comparación entre ventanas",
    `La línea base son los ${ctx.state.months} meses anteriores al inicio de la ventana activa.`,
  );
  const comparePlot = el("div", "plot");
  const compareRows = comparison.data.filter(
    (row) => row.baseline_count > 0 || row.target_count > 0,
  );
  if (compareRows.length) {
    compareCard.body.append(comparePlot);
    groupedBars(comparePlot, {
      x: compareRows.map((row) => ctx.frameLabel(row.label)),
      series: [
        {
          name: "Base",
          y: compareRows.map((row) => row.baseline_share * 100),
          color: "#94a3b8",
        },
        {
          name: "Objetivo",
          y: compareRows.map((row) => row.target_share * 100),
          color: "#0b6e4f",
        },
      ],
      yTitle: "% de posts",
    });
  } else {
    compareCard.body.append(
      notice(
        comparison.provenance.warnings?.[0] ||
          "Definí una fecha de inicio para comparar con la ventana previa.",
        "info",
      ),
    );
  }
  renderProvenance(compareCard.body, comparison.provenance);
  root.append(compareCard.section);

  renderProvenance(root, distribution.provenance);
}
