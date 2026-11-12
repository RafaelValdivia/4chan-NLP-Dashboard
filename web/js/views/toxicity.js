// View: Toxicidad · ordinal 0–3 and the share above the toxic threshold.

import { get } from "../api.js";
import { bars } from "../charts.js";
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
    const overview = await get("toxicity-overview", "/api/overview", params);
    root.append(
      notice(
        "Todavía no hay predicciones L1 sobre el corpus: la distribución de toxicidad " +
          "aparecerá con el primer run del clasificador.",
        "info",
      ),
    );
    root.append(
      metrics([
        { label: "Posts", value: number(overview.data.posts) },
        { label: "Hilos", value: number(overview.data.threads) },
      ]),
    );
    renderProvenance(root, overview.provenance);
    return;
  }

  const result = await get("toxicity", "/api/toxicity", params);
  const data = result.data;
  const coverage = result.provenance.coverage ?? 0;

  root.append(
    metrics([
      { label: "Posts predichos", value: number(result.provenance.n) },
      {
        label: "Tóxicos (≥ 2)",
        value: number(data.toxic_count),
        help: percent(data.toxic_share),
      },
      {
        label: "IC 95 % de la cuota tóxica",
        value: `${percent(data.toxic_wilson.low)}–${percent(data.toxic_wilson.high)}`,
      },
      { label: "Cobertura", value: percent(coverage, 1), help: "Posts con predicción" },
    ]),
  );

  const chart = card(
    "Distribución de toxicidad",
    "0 = neutro · 1 = leve · 2 = explícita · 3 = amenaza o incitación",
  );
  const plot = el("div", "plot");
  chart.body.append(plot);
  root.append(chart.section);

  bars(plot, {
    x: data.levels.map((row) => `Nivel ${row.level}`),
    y: data.levels.map((row) => row.count),
    title: "",
    yTitle: "Posts",
  });

  const rows = data.levels.map((row) => ({
    level: row.level,
    label: ctx.toxicLabel(row.level),
    count: row.count,
    share: row.share,
    ic_low: row.wilson?.low ?? null,
    ic_high: row.wilson?.high ?? null,
  }));

  const tableCard = card("Tabla ordinal");
  tableCard.body.append(
    table(
      rows,
      [
        { key: "level", label: "Nivel", align: "right" },
        { key: "label", label: "Etiqueta" },
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
      { filename: "toxicidad.csv" },
    ),
  );
  root.append(tableCard.section);

  if (coverage < 1) {
    root.append(
      notice(
        `Solo el ${percent(coverage, 1)} de los posts del filtro tiene predicción. ` +
          "Las cuotas usan el denominador elegido, no la cobertura.",
        "warning",
      ),
    );
  }

  renderProvenance(root, result.provenance);
}
