# Protocolo de clasificación plata (pre-registro)

Fecha: 11-11-2026. Estado: pre-registrado antes de la primera corrida del
maestro. Este protocolo define cómo se generan las etiquetas plata de 5.000
posts de ROTLK y cómo se usan para entrenar y comparar clasificadores. No
reemplaza el oro humano de 200 posts ni el protocolo de evaluación original:
lo enmienda de forma explícita.

## Decisión central

La salida del LLM local se trata como **plata confiada**, no como oro humano.
Los 5.000 posts **no se revisan ni se corrigen humanamente**. El oro de 200
posts se conserva solo como **diagnóstico externo** del maestro; no valida,
corrige ni bloquea la plata.

Consecuencia metodológica: la tabla principal de resultados mide **imitación
del maestro**, no verdad. La comparación contra el oro de 200 se reporta aparte
y no se usa para seleccionar modelos ni hiperparámetros.

## Muestra

| Campo | Valor |
|---|---|
| Fuente | ROTLK `/pol/` |
| Ventana | `2016-06-01T00:00:00Z` → `2019-11-01T23:59:59Z` |
| Muestra | 5.000 posts aleatorios |
| Dirigidos | 0 |
| Semilla | 17 |
| Unidad | post; un post por hilo |
| Texto | `text_raw` y `text_clean`; sin OP, quotes, subject ni stratum |

Reglas de construcción:

- Un post y un hilo por registro; se descartan `text_clean` vacíos.
- Deduplicación por `post_id`, `thread_id` y `content_hash`.
- Cobertura mensual completa; si un mes no alcanza la cuota, se documenta y se
  redistribuye sin reemplazar posts ya elegidos.
- La muestra se genera en una sola pasada sobre el `.tar.zst`, con reservorio
  por mes acotado a la cuota esperada.

Verificación obligatoria:

- 5.000 posts únicos y 5.000 hilos únicos;
- 0 textos vacíos y 0 `content_hash` duplicados;
- rango temporal exacto y cobertura de los 42 meses;
- archivo reproducible con la misma semilla.

**Enmienda 11-11-2026.** La muestra de 5.000 se generó antes de corregir el
sampler y contiene **27 grupos con `content_hash` repetido: 91 filas, 64
sobrantes**. Son posts degenerados de 1–10 caracteres (`bump`, `kek`, `?`,
`RARE`, `Thoughts?`) repetidos en hilos distintos.

Como el etiquetado ya estaba en curso en otra máquina, la muestra **se congela
y no se remuestrea**. La garantía de unicidad de contenido se traslada al
export del dataset: `build_modeling_rows` colapsa cada grupo por `content_hash`
y conserva un representante determinista (el `post_id` numérico menor),
reportando `duplicate_groups` y `duplicate_rows_removed`. El split sigue siendo
por `thread_id`, ya sin texto duplicado entre train y test. La corrección del
sampler aplica a muestreos futuros, no a este archivo.

## Etiquetas

- 16 marcos finos binarios multi-label y toxicidad ordinal `0–3`.
- `none` y `unclear` son exclusivos con todo otro marco y entre sí.
- Las etiquetas específicas de prejuicio reemplazan a
  `ethnonationalism`/`racism`.
- `transphobia` y `homophobia` son ejes independientes de `misogyny`.
- `guideline_version = "v0.2"`, `prompt_version = "v2"`.
- El prompt es el mismo del piloto (`docs/prompts/annotation_prompt_v2.txt`);
  hash esperado `30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769`.
- Si el smoke test exige cambiar el prompt, se crea `v3`, se registra el nuevo
  hash y se repite el smoke test. No se cambia el prompt en silencio.

## Maestro

| Campo | Valor |
|---|---|
| Modelo | `qwen3-8b-q4_k_m.gguf` |
| Ruta | `models/gguf/` o `KEKLAB_MODELS_DIR` |
| Backend | `llama.cpp` / `llama-cpp-python` |
| Modo | chat con la plantilla del GGUF |
| Thinking | desactivado explícitamente y registrado |
| Temperatura | 0 |
| Semilla | 13 |
| `n_ctx` | 2048 (ajustable tras el smoke test) |
| Salida | JSON estricto validado contra el esquema |

Cada corrida guarda un manifiesto con: SHA256 del GGUF, versión de
`llama.cpp`, cuantización, `n_ctx`, `n_batch`, `n_gpu_layers`, temperatura,
semilla, hash del prompt, hash de la plantilla de chat y commit de git.

## Smoke test

Antes de los 5.000:

1. Correr 50 posts estratificados por mes.
2. Medir tokens/s, latencia, RAM/VRAM pico, fallos de parseo y evidencia
   inválida.
3. Criterios de corte: 100 % JSON válido tras un reintento, <2 % etiquetas
   inválidas, sin OOM y tiempo total proyectado aceptable.
4. Correr el maestro sobre los 200 de oro y guardar el diagnóstico aparte.

Si el smoke test falla, se ajusta gramática, prompt o configuración del modelo
y se repite. No se lanza la corrida completa con un gate fallido.

## Partición

- Split por `thread_id`, 60/20/20, semilla 13.
- El test se congela y se hashea antes de entrenar.
- Los hilos ya asignados no se mueven al agregar datos.
- Se valida que ningún hilo aparezca en más de un split.

## Modelos comparados

| Modelo | Rol | Entrenamiento |
|---|---|---|
| Qwen3-8B GGUF | Maestro / techo de referencia | No entrena |
| Laya | Zero-shot tipado | No entrena |
| GLiClass | Zero-shot | Condicionado al checkpoint |
| GLiNER | Marcos por extracción | Umbral en dev |
| TF-IDF + LR | Clásico | Train plata |
| BoW + SVM lineal | Clásico | Train plata |
| Embeddings + LR | Clásico | Train plata |
| BERT/RoBERTa | Transformer multi-label | Train plata |

Reglas:

- E0: `text_raw` vs `text_clean` en dev; la limpieza solo se adopta si mejora
  de forma consistente.
- Hiperparámetros en dev; una sola evaluación final en test.
- Toxicidad como tarea ordinal/multiclase separada.
- Reportar las 7 cabezas derivadas aunque el modelo entrene los 16 marcos.
- Marcos con muy pocos positivos: reporte descriptivo, sin F1 como métrica
  principal.

## Métricas

Por marco y por cabeza:

- precisión, recall y F1 por clase;
- F1 macro y micro;
- positivos reales y predichos;
- intervalos de confianza por bootstrap de 1.000 remuestreos a nivel hilo.

Toxicidad:

- kappa cuadrática ponderada;
- MAE;
- matriz de confusión;
- versión binaria `0–1` vs `2–3`.

Comparación entre modelos:

- bootstrap pareado por hilo para diferencias de F1;
- McNemar cuando aplique;
- costo: segundos por 1.000 posts, RAM/VRAM pico, cobertura y fallos.

## Reporte

- Tabla principal: modelos pequeños contra plata test.
- Tabla secundaria: LLM/Laya/GLiNER/BERT contra los 200 de oro, solo como
  diagnóstico externo.
- Aclaración obligatoria: la tabla principal mide imitación del maestro, no
  verdad.

## Estructura de artefactos

```text
data/classification/
  samples/rotlk_5000.jsonl
  tasks/rotlk_5000.jsonl
  llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl
  silver/rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl
  splits/rotlk_5000_threads.jsonl
  predictions/<modelo>/{dev,test}.jsonl
  reports/<modelo>.json
  manifests/<run>.json
```

Se versionan muestras, tareas, plata, splits, reportes y manifiestos pequeños.
Se ignoran las salidas crudas del LLM y las predicciones, que se regeneran
desde tareas y manifiestos.

`predictions/<modelo>/` son las predicciones sobre dev/test, para evaluación.
Son otra cosa que **L1**: las predicciones del modelo aplicadas al corpus
completo, que se guardan como Parquet mensual fuera del repositorio (ver
`docs/analytics.md`).

## Límites

- La plata hereda sesgos y errores del maestro.
- Evaluar contra el maestro premia imitarlo, no acertar.
- Los marcos finos raros siguen con pocos positivos.
- Un solo anotador humano y self test-retest pendiente en el oro.
- La ventana es histórica; no garantiza generalización a `/pol/` reciente.
