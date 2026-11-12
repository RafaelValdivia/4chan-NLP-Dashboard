// View: Resumen · volume and shape of the active slice.

import { get } from "../api.js";
import { line } from "../charts.js";
import {
  card,
  dateShort,
  el,
  metrics,
  notice,
  number,
  renderProvenance,
} from "../ui.js";

const GRANULARITY = { month: "mes", week: "semana", day: "día" };

export async function render(root, ctx) {
  const params = ctx.params();
  const [overview, volume] = await Promise.all([
    get("summary-overview", "/api/overview", params),
    get("summary-volume", "/api/volume", params),
  ]);
  const data = overview.data;

  root.append(
    metrics([
      { label: "Posts", value: number(data.posts) },
      { label: "Hilos", value: number(data.threads) },
      { label: "Posts de OP", value: number(data.op_posts), help: "Abren el hilo" },
      {
        label: "Longitud mediana",
        value: data.median_length ? `${number(data.median_length)} car.` : "—",
        help: "Texto limpio",
      },
      { label: "Meses cubiertos", value: number(data.months) },
    ]),
  );

  if (data.first_post) {
    root.append(
      el(
        "p",
        "caption",
        `Ventana del corpus: ${dateShort(data.first_post)} → ${dateShort(data.last_post)}`,
      ),
    );
  }

  const chart = card(`Volumen por ${GRANULARITY[ctx.state.granularity] || "mes"}`);
  const plot = el("div", "plot");
  chart.body.append(plot);
  root.append(chart.section);

  if (volume.data.length) {
    line(plot, {
      x: volume.data.map((row) => row.period),
      series: [
        { name: "Posts", y: volume.data.map((row) => row.posts) },
        { name: "Hilos", y: volume.data.map((row) => row.threads) },
      ],
      yTitle: "Publicaciones",
      yFormat: "d",
      granularity: ctx.state.granularity,
    });
  } else {
    plot.remove();
    chart.body.append(notice("El filtro no devuelve datos."));
  }

  if (data.avg_length) {
    chart.body.append(
      el("p", "caption", `Longitud media: ${number(data.avg_length)} caracteres.`),
    );
  }

  renderProvenance(root, overview.provenance);
}
