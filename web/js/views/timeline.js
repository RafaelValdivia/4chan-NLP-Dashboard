// View: Línea de tiempo · frame shares over time (or volume without L1),
// with the curated external milestones marked on the axis.

import { get } from "../api.js";
import { line } from "../charts.js";
import { card, dateShort, el, notice, renderProvenance } from "../ui.js";

const GRANULARITY = { month: "mes", week: "semana", day: "día" };

function eventSummary(events) {
  if (!events.length) return "Sin hitos externos dentro de la ventana.";
  return (
    "Hitos externos: " +
    events
      .map((event) => `${dateShort(event.date)} ${event.label}`)
      .join(" · ")
  );
}

export async function render(root, ctx) {
  const params = ctx.params();
  const [series, eventsResult] = await Promise.all([
    get("timeline-series", "/api/series", params),
    get("timeline-events", "/api/events", params),
  ]);
  const events = eventsResult.data || [];
  root.append(el("p", "caption", eventSummary(events)));

  const chart = card(
    series.mode === "frames"
      ? `Cuota por marco (${GRANULARITY[ctx.state.granularity] || ctx.state.granularity})`
      : `Volumen por ${GRANULARITY[ctx.state.granularity] || ctx.state.granularity}`,
  );
  const plot = el("div", "plot");
  chart.body.append(plot);
  root.append(chart.section);

  if (series.mode === "frames") {
    const periods = series.data.series.map((row) => row.period);
    if (!periods.length) {
      plot.remove();
      chart.body.append(notice("Ninguna predicción cae dentro de la ventana."));
      return;
    }
    const wanted = ctx.state.frames.length
      ? new Set(ctx.state.frames)
      : null;
    const labels = new Set();
    for (const period of series.data.series) {
      for (const frame of period.frames) {
        if (frame.count > 0 && (!wanted || wanted.has(frame.label))) {
          labels.add(frame.label);
        }
      }
    }
    const traces = [...labels].map((label) => ({
      name: ctx.frameLabel(label),
      y: series.data.series.map((period) => {
        const frame = period.frames.find((item) => item.label === label);
        return frame ? frame.share * 100 : 0;
      }),
    }));
    line(plot, {
      x: periods,
      series: traces,
      yTitle: "% de posts",
      yFormat: ".2f",
      events,
      granularity: ctx.state.granularity,
    });
  } else {
    const rows = series.data;
    if (!rows.length) {
      plot.remove();
      chart.body.append(notice("El filtro no devuelve datos."));
      return;
    }
    line(plot, {
      x: rows.map((row) => row.period),
      series: [
        { name: "Posts", y: rows.map((row) => row.posts) },
        { name: "Hilos", y: rows.map((row) => row.threads) },
      ],
      yTitle: "Publicaciones",
      yFormat: "d",
      events,
      granularity: ctx.state.granularity,
    });
  }

  renderProvenance(root, series.provenance);
}
