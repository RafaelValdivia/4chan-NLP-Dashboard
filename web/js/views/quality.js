// View: Calidad · what the warehouse holds, its manifest and the coverage of
// predictions.

import { get } from "../api.js";
import {
  card,
  dateShort,
  definitionList,
  el,
  metrics,
  notice,
  number,
  percent,
  renderProvenance,
} from "../ui.js";

function manifestCard(manifest, partsOnDisk) {
  if (!manifest) {
    return notice(
      "No se encontró el manifiesto de construcción de L0 (`_l0_manifest.json`).",
      "info",
    );
  }
  const totals = manifest.totals || {};
  const chunks = Object.keys(manifest.chunk_stats || {}).length;
  const box = card("Manifiesto de construcción (L0)");
  box.body.append(
    definitionList([
      ["Estado", manifest.status || "—"],
      ["Trozos", `${number(chunks)} / ${number(manifest.chunks_total || 0)}`],
      ["Posts escritos", number(totals.posts || 0)],
      ["Hilos", number(totals.threads || 0)],
      ["JSON inválido", number(totals.bad_json || 0)],
      ["Partes escritas", number(manifest.parts_written || 0)],
      ["Partes en disco", number(partsOnDisk)],
      ["Entrada", manifest.input || "—"],
      ["Bytes de entrada", number(manifest.input_bytes || 0)],
      ["Duración", `${number(manifest.elapsed_s || 0)} s`],
      ["Actualizado", dateShort(manifest.updated_utc)],
    ]),
  );
  return box.section;
}

export async function render(root, ctx) {
  const result = await get("quality", "/api/quality", ctx.params());
  const data = result.data;
  const corpus = data.corpus;

  root.append(
    metrics([
      { label: "Posts", value: number(corpus.posts) },
      { label: "Hilos", value: number(corpus.threads) },
      { label: "Posts sin texto", value: number(corpus.empty_posts) },
      { label: "Meses", value: number(corpus.months) },
    ]),
  );
  if (corpus.first_post) {
    root.append(
      el(
        "p",
        "caption",
        `Desde ${dateShort(corpus.first_post)} hasta ${dateShort(corpus.last_post)}`,
      ),
    );
  }

  root.append(manifestCard(data.manifest, data.parts_on_disk));

  const predictions = card("Predicciones");
  if (data.predictions_available) {
    predictions.body.append(
      notice("Hay predicciones L1 cargadas para las vistas de marcos y toxicidad.", "info"),
    );
  } else {
    predictions.body.append(
      notice(
        "Sin predicciones cargadas: el corpus se puede consultar por volumen y búsqueda, " +
          "pero no por marco ni toxicidad. Configurá `KEKLAB_PREDICTIONS` cuando exista L1.",
        "info",
      ),
    );
  }
  if (result.provenance.coverage !== undefined) {
    predictions.body.append(
      el("p", "caption", `Cobertura de la ventana: ${percent(result.provenance.coverage, 1)}`),
    );
  }
  root.append(predictions.section);

  renderProvenance(root, result.provenance);
}
