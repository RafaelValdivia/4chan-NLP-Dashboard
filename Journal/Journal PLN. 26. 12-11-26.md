# Journal PLN — Entrada 26 (12-11-2026)

## Contexto

Continuación de la entrada 22. La corrida v3 de los 5.000 posts ya está hecha y
la plata está validada en memoria, pero todavía no se ha exportado a disco. El
siguiente paso es el fine-tuning comparado de Laya y GLiNER sobre esa plata.
Esta entrada fija el plan operativo **antes de tocar test** y documenta las
decisiones de entorno, datos, modelos, métricas y artefactos. Todavía no se ha
entrenado nada.

La regla central sigue siendo la del pre-registro: la plata mide **imitación del
maestro**, no verdad. Laya y GLiNER se entrenan supervisados con las etiquetas de
Qwen; el oro de 200 queda como diagnóstico externo y no se usa para seleccionar
modelos ni hiperparámetros.

## Estado de partida

### Datos

- 5.000 posts crudos; 4.998 anotaciones válidas.
- 2 `task_id` no coinciden entre tareas y crudo; se remapean por `post_id`:
  - `115110323`: `task_1225eae166fe42af` → `task_dd86b6fe34503733`.
  - `207330062`: `task_1908e38a17b64ce9` → `task_8762c5f0e270dc96`.
- 80 filas con evidencia no verbatim; se aceptan para Laya y se filtran para
  GLiNER.
- `annotation_prompt` v3, hash
  `ef251abee5137ab35ff1882817c97aee5bdcdac9c0ee52900afbbe60d68c995e`;
  `guideline_version = v0.2`.

### Modelos

- Laya completo en `/home/flynn/modelos_originales/laya-base/`:
  `model.safetensors` de 842.609.210 bytes; `encoder_config.json`,
  `rl_agent_config.json`, `tokenizer.json` y `tokenizer_config.json` presentes.
- GLiNER en `/home/flynn/modelos_originales/gliner-multi-v2.1/`:
  `model.safetensors` de 1.155.830.112 bytes; `gliner_config.json` válido
  (`microsoft/mdeberta-v3-base`, `max_len=384`, `max_width=12`, `max_types=25`).
- `config.json`, `tokenizer.json` y `tokenizer_config.json` de GLiNER están en
  0 bytes. Hay que restaurarlos desde `urchade/gliner_multi-v2.1` o
  `microsoft/mdeberta-v3-base` antes de cargar el modelo. Los pesos no se
  re-verifican: el usuario confirmó que los archivos son auténticos.

### Entorno y hardware

- GPU: GTX 1070 Ti, 8 GB, compute capability `sm_61`.
- `torch 2.12.1+cu130` solo incluye `sm_75, sm_80, sm_86, sm_90, sm_100,
  sm_120`; no puede ejecutar kernels en esta GPU. Hay que instalar un build de
  PyTorch CUDA 12.x con soporte `sm_61` en un venv dedicado.
- `llama-server` PID 32792 ocupa ~5.9 GB de VRAM; hay que detenerlo antes de
  entrenar.
- Disco libre: ~6.8 GB; ajustado para checkpoints y estados de optimizador.
- Dependencias actuales: `duckdb 2.0.0`; faltan `laya`, `gliner`, `datasets`,
  `pyarrow`, `polars`.

## Plan de fine-tuning

### Fase 0 — Datos, splits y congelación de test

1. Exportar la plata a JSONL desde las anotaciones válidas.
2. Remapear los 2 `task_id` por `post_id` y registrar el cambio.
3. Construir el split por `thread_id`, 60/20/20, semilla 13.
4. Congelar test y calcular su hash antes de cualquier entrenamiento.
5. Verificar que ningún hilo aparece en más de un split.
6. Exportar representaciones de entrada para Laya y GLiNER.
7. Guardar un manifiesto con hashes de datos, split, test, prompt y guideline.
8. No evaluar test hasta que el protocolo de fine-tuning esté registrado.

### Fase 1 — Laya

Laya no es un clasificador multi-label estándar: responde preguntas tipadas. Se
usará **un modelo con 17 preguntas por post**:

- 16 preguntas `noul` (sí/no), una por marco fino;
- 1 pregunta `score` de toxicidad `0–3`.

Cada fila de entrenamiento tendrá `state = text_clean`, las 17 `questions` y
`expected` con la respuesta de Qwen. `none` y `unclear` se mantienen como
preguntas separadas y luego se aplica una regla de exclusividad: si se predice
`none` o `unclear`, se suprimen los demás marcos; si no se predice ningún marco
sustantivo, se asigna `none`.

Configuración inicial:

| Parámetro | Valor |
|---|---|
| Checkpoint | `laya-base` local |
| `freeze_encoder` | `True` en la primera corrida |
| `loss` | `soft-ce` primero; `rlcd` como ablación después |
| `max_len` | 512 |
| `head_max_len` | 192 |
| `amp` | `True` (fp16; no bf16 en Pascal) |
| `gradient_checkpointing` | activado si hace falta |
| `micro_batch` | 1 si el encoder no está congelado; ajustar con encoder congelado |
| `grad_accum` | hasta completar un batch efectivo razonable |
| `epochs` | 4 iniciales; selección por dev |
| `label_smoothing` | 0.0 inicial; 0.05 solo si hay sobreajuste |
| Semilla | 13 |

Orden de corridas:

1. **Laya frozen encoder + soft-CE** — primera corrida viable en 8 GB.
2. **Laya frozen encoder + RLCD** — misma partición, para comparar objetivos.
3. **Laya full fine-tune** — solo si dev justifica y la VRAM lo permite;
   `gradient_checkpointing=True`, `micro_batch=1`, `grad_accum` alto.

Si full fine-tune hace OOM, el resultado primario de Laya será frozen encoder y
el OOM se documentará. No se sustituye un resultado por otro en silencio.

Calibración:

- separar 10 % de train para calibración, máximo 400 ítems;
- ajustar temperaturas por tipo (`noul`, `score`) con
  `laya.calibrate.fit_temperature_map`;
- elegir umbrales por marco en dev;
- reportar ECE, Brier y NLL antes y después de calibrar.

Los marcos raros (`unclear` 4, `meta_topic` 4, `accelerationism` 23) se reportan
de forma descriptiva; no se optimizan como métrica principal.

### Fase 2 — GLiNER

GLiNER se entrena supervisado con las mismas etiquetas de Qwen, pero necesita
spans. La operacionalización es:

- 14 marcos sustantivos como tipos de entidad; `none` y `unclear` no son tipos.
- Para cada marco positivo, usar los spans de evidencia de Qwen que aparezcan
  literalmente en `text_clean`.
- Si un marco positivo no tiene evidencia válida, usar el post completo como
  span de ese marco.
- Posts `none`/`unclear` van como negativos (`ner = []`).
- En inferencia, cualquier span detectado para un marco marca el post como
  positivo; el umbral se elige en dev.
- GLiNER no modela toxicidad; esa cabeza queda solo en Laya.

Configuración inicial:

| Parámetro | Valor |
|---|---|
| Checkpoint | `gliner-multi-v2.1` local |
| `max_len` | 384 |
| Batch | empezar pequeño; ajustar según VRAM |
| Loss | la receta estándar de GLiNER; documentar la elegida |
| Épocas | 3–5 iniciales; selección por dev |
| Semilla | 13 |

Antes de entrenar hay que restaurar `config.json`, `tokenizer.json` y
`tokenizer_config.json`, que están en 0 bytes.

### Fase 3 — Baselines y comparación

Se compararán, con el mismo split congelado y el mismo script de evaluación:

- Qwen3-8B maestro, como referencia/techo de imitación;
- Laya zero-shot y Laya fine-tuned;
- GLiNER zero-shot y GLiNER fine-tuned;
- TF-IDF + regresión logística;
- BoW + SVM lineal;
- embeddings + regresión logística;
- BERT/RoBERTa multi-label solo si el tiempo y la VRAM lo permiten.

Reglas de comparación:

- selección de hiperparámetros y umbrales solo en dev;
- test se evalúa una vez;
- mismo `text_clean` y mismas filas para todos;
- bootstrap pareado por hilo para diferencias de F1;
- McNemar cuando aplique;
- reportar coste: segundos por 1.000 posts, RAM/VRAM pico, cobertura y fallos.

### Fase 4 — Evaluación

Por marco fino y por cabeza gruesa:

- positivos reales y predichos;
- precisión, recall y F1 por etiqueta;
- F1 macro y micro;
- intervalos de confianza por bootstrap de 1.000 remuestreos a nivel hilo,
  semilla 13;
- AUPRC/ROC como métricas secundarias.

Toxicidad:

- kappa cuadrática ponderada;
- MAE;
- matriz de confusión;
- versión binaria `0–1` vs `2–3`;
- precisión/recall/F1 por nivel como apoyo.

Calibración:

- ECE, Brier y NLL;
- curvas de fiabilidad;
- temperatura y umbrales elegidos.

Comparación:

- diferencias pareadas de F1 con bootstrap;
- McNemar;
- latencia p50/p95, throughput, VRAM/RAM pico;
- fallos de parseo, ítems omitidos y cobertura.

Oro de 200: solo tabla secundaria de diagnóstico; nunca selección.

## Documentación obligatoria

Cada corrida debe dejar:

- `data/classification/manifests/<run_id>.json` con git commit, entorno,
  versiones, GPU/CUDA, rutas y tamaños de modelo, hashes de datos/split/test,
  prompt/guideline, semilla, `TrainConfig` completo, presupuesto de updates,
  épocas, tiempos, recursos y motivo de parada;
- `data/classification/predictions/<modelo>/{dev,test,gold}.jsonl`;
- `data/classification/reports/<modelo>.json` y `.md`;
- `data/classification/reports/comparison.json` y `comparison.md`;
- una entrada de journal con decisiones, fallos y resultados.

Métricas que no se pueden omitir: pérdida por época, LR, grad norm, steps,
tiempo, ítems/s, VRAM/RAM pico, calibración, umbrales, matriz de confusión,
soporte por etiqueta, predicciones positivas, bootstrap, McNemar y coste.

## Decisiones

| Decisión | Valor | Motivo |
|---|---|---|
| Objetivo de Laya | 16 marcos finos + toxicidad | Mantiene el detalle fino y permite derivar las 7 cabezas. |
| Objetivo de GLiNER | Supervisado con etiquetas de Qwen, vía spans de evidencia | Es la forma natural de entrenar un extractor con labels de post. |
| Fallback de GLiNER | Post completo si no hay evidencia válida | Evita perder positivos; se documenta como span débil. |
| Primera corrida de Laya | Frozen encoder + soft-CE | Cabe en 8 GB y es estable; RLCD queda como ablación. |
| Full fine-tune | Solo si dev lo justifica y la VRAM lo permite | Evita gastar tiempo en un OOM probable. |
| Baseline barato | TF-IDF+LR, BoW+SVM, embeddings+LR | Comparación útil sin el coste de BERT/RoBERTa. |
| Entorno | Venv dedicado con PyTorch CUDA 12.x | El torch actual no soporta `sm_61`. |
| Test | Congelado y evaluado una vez | Evita fuga y ajuste sobre test. |
| Oro de 200 | Diagnóstico externo | No válida ni selecciona la plata. |
| Marcos raros | Reporte descriptivo | Pocos positivos; F1 inestable. |

## Riesgos y bloqueos

- PyTorch actual incompatible con `sm_61`; sin build CUDA 12.x no hay
  entrenamiento GPU práctico.
- GLiNER no carga hasta restaurar sus metadatos de 0 bytes.
- `llama-server` ocupa VRAM y debe detenerse.
- Full fine-tune de Laya probablemente no cabe en 8 GB.
- Disco ajustado para checkpoints y estados de optimizador.
- Evidencia de Qwen es plana y no está ligada a cada marco; los spans de GLiNER
  son una aproximación supervisada, no una anotación de spans humana.
- La plata hereda sesgos y errores del maestro; la tabla principal mide
  imitación, no verdad.

## Próximos pasos

1. Volcar esta enmienda a `docs/finetuning_protocol.md` antes de entrenar.
2. Crear el venv dedicado, instalar PyTorch CUDA 12.x, `laya`, `gliner`,
   `datasets` y `pyarrow`; verificar un kernel CUDA pequeño.
3. Detener `llama-server` y confirmar VRAM libre.
4. Exportar plata, splits y test congelado; registrar hashes y manifiestos.
5. Entrenar Laya frozen encoder + soft-CE; evaluar dev; calibrar.
6. Entrenar Laya frozen encoder + RLCD como ablación; full fine-tune solo si
   procede.
7. Restaurar GLiNER y entrenar; ajustar umbral en dev.
8. Entrenar baselines baratos y generar comparación.
9. Evaluar test una vez y cerrar con journal, reportes y comparación.

## Estado de git

Al escribir esta entrada:

- `Journal/Journal PLN. 19. 11-11-26.md` modificado (corrección de la entrada
  19);
- `models/SHA256SUMS` modificado por el usuario;
- `data/classification/manifests/qwen3-v3-5000.json` sin trackear;
- esta entrada es un archivo nuevo.

No se ha tocado código de entrenamiento todavía.
