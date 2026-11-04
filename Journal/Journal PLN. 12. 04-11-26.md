# Journal PLN — Entrada 12 (04-11-2026)

## Contexto

La entrada 11 cerró la muestra de 200 posts para el piloto, pero la anotación
todavía no empezó. Esta entrada implementa el trabajo que no depende del oro y
que la entrada anterior había identificado como prioritario: reproducibilidad
de la muestra, taxonomía gruesa, partición pre-registrada y herramientas de
auditoría/retest. No repite la decisión de tamaño muestral ni la expansión de
marcos; solo registra lo construido mientras se espera la anotación.

## Qué se implementó

### Reproducibilidad de la muestra

La fusión de los 200 se había hecho con un script inline. Ahora existe
`keklab annotate merge`:

- valida cada fila con `SamplePost`;
- conserva la primera aparición y deduplica por `post_id` y `thread_id`;
- reporta filas leídas, duplicados, razones, fuentes, meses y rango temporal;
- permite exigir conteos con `--expect-total`, `--expect-random` y
  `--expect-targeted`.

Regenerar el archivo desde las dos fuentes produce **exactamente las mismas 200
filas, en el mismo orden**. El chequeo se corrió sobre la muestra real y dio
`same rows (exact dicts): True`.

### Auditoría

`keklab annotate audit` describe un archivo de candidatos sin anotaciones:
posts/hilos únicos, duplicados, textos vacíos, OP/reply, razones, fuentes,
países, meses, rango temporal y longitud de texto. Acepta `--start`/`--end`
para contar posts fuera de la ventana.

Auditoría del piloto de 200:

| Métrica | Valor |
|---|---:|
| Posts / hilos únicos | 200 / 200 |
| Aleatorios / dirigidos | 190 / 10 |
| `text_clean` vacíos | 0 |
| Fuera de ventana | 0 |
| Meses calendario | 25 |
| OP | 44 |
| Longitud mediana | 76.5 caracteres |
| Países principales | US 104, CA 15, GB 9 |

### Taxonomía gruesa

`src/keklab/annotation/taxonomy.py` define las 8 cabezas de modelado y el mapeo
desde los 18 marcos finos. El import falla si el vocabulario fino y el mapeo se
desincronizan. `annotate export` agrega `coarse_labels` y columnas one-hot
`coarse_*`; `annotate stats` reporta `coarse_counts`.

| Cabeza | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `antifeminism`, `transphobia`, `homophobia` |
| `eugenics_ableism` | `eugenics`, `ableism` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

### Split y retest

- `keklab annotate split` asigna train/dev/test **por hilo** (60/20/20) con
  semilla 13. El manifiesto pre-registrado quedó en
  `data/splits/rotlk_pilot_200_threads.jsonl`: **120/40/40 hilos**.
- `keklab annotate retest` selecciona el 20% para la ronda 2 de forma
  determinista. Sobre los 200 selecciona **40** (39 aleatorios + 1 dirigido).
  El dirigido no se usa para prevalencia.

La partición por hilo evita fuga entre OP y respuestas. El test queda
reservado: no se usa para elegir modelo ni hiperparámetros.

## Protocolo pre-registrado

Se escribió `docs/evaluation_protocol.md` antes de ver cualquier etiqueta. Fija:

- unidad de análisis (post) y muestra (200; 190 aleatorios + 10 dirigidos);
- taxonomía fina para anotar y gruesa para modelar;
- split 60/20/20 por hilo con semilla 13;
- métricas por cabeza (precisión, recall, F1 macro/micro, bootstrap);
- toxicidad ordinal con kappa cuadrática y MAE;
- self test-retest de 40 posts, con la limitación de que no es acuerdo
  inter-anotador;
- E0 (crudo vs saneado) y E2 (TF-IDF+LR vs BoW+SVM vs embeddings);
- reglas de soporte: ≥30 positivos en train y ≥5 en test para modelar;
- regla de parada: si tras 1,000 posts aleatorios una cabeza sigue con <5
  positivos, se reporta solo de forma descriptiva.

También se actualizaron `docs/annotation_guidelines.md` (mapeo grueso) y
`README.md` (comandos, muestra de 200 y split).

## Tests

La suite pasó de 87 a **109 pruebas**. Los tests nuevos cubren:

- taxonomía y mapeo fino → grueso;
- fusión, deduplicación y conteos esperados;
- retest determinista;
- split por hilo y manifiesto;
- auditoría de textos vacíos y ventana;
- los cuatro comandos nuevos de la CLI.

Todos los tests pasan con `~/PyVenvs/NNnPLN/bin/python -m pytest -q`.

## Estado de git

- `e4b0be8`: código y tests de taxonomía, merge, audit, split y retest.
- `13d4fae`: manifiesto de split pre-registrado.
- Este commit: documentación (`README.md`, `docs/annotation_guidelines.md`,
  `docs/pipeline_draft.md`, `docs/evaluation_protocol.md`) y esta entrada.
- Sin push a `origin` en esta entrada.

## Lo que no se hizo

- No se entrenó ningún modelo: no hay oro.
- No se construyó el harness completo de E0/E2. Solo se pre-registraron sus
  definiciones; implementarlo antes de tener etiquetas repetiría el problema
  que la entrada 5 ya había señalado.
- No se generó una pre-anotación automática, para no inducir al anotador.

## Siguiente paso

Anotar los 200 posts:

```bash
keklab annotate run \
  --input data/samples/rotlk_pilot_200.jsonl \
  --annotator flynnso \
  --guideline v0 \
  --round 1 \
  --out data/annotations/rotlk_pilot_r1.jsonl
```

Al terminar, calcular `p_hat` por cabeza separando los 190 aleatorios de los 10
dirigidos, aplicar `n = K / p_hat` y decidir si el modelo queda en 8 cabezas o
si algún marco necesita muestreo dirigido.
