# Journal PLN — Entrada 17 (10-11-2026)

## Contexto

Esta entrada registra el plan para el siguiente objetivo del proyecto: usar un
LLM local (GGUF) para etiquetar en plata un lote del orden de miles de posts de
ROTLK y, a partir de esas etiquetas, entrenar y comparar modelos de clasificación
más pequeños.

La decisión metodológica central es explícita: **la salida del LLM se trata como
plata confiada, no como oro humano**. No se revisan humanamente los miles de
posts. El oro humano de 200 posts se conserva solo como diagnóstico externo del
maestro; no valida, corrige ni bloquea la plata.

Esto se aparta de `docs/ai_annotation_protocol.md`, que establece que las
propuestas de IA no son oro. Para no cambiar el pre-registro en silencio, la
primera fase del plan escribe un protocolo nuevo de clasificación plata y una
enmienda explícita a `docs/evaluation_protocol.md`.

## Modelos GGUF disponibles

Los modelos ya están en `/home/flynn/modelos_gguf/`:

| Rol previsto | Archivo | Tamaño | SHA256 |
|---|---|---:|---|
| Maestro / etiquetador plata | `Qwen3-8B-Q4_K_M.gguf` | 5.027.783.488 B (~4,68 GiB) | `90962c51b31cd98a5d39861d082541f92af6c1e246be58fe88031a401db58a15` |
| Clasificador zero-shot | `laya-Q8_0.gguf` | 421.407.968 B (~402 MiB) | `76a5787a9c853d04db4ff214ae31fe2bd51aa15c8bef2fc886a3493f3c136dae` |
| Cabeza de Laya | `laya-head.safetensors` | 106.052.840 B (~101 MiB) | no calculado |
| Clasificación de marcos / entidades | `gliner-deberta-q8_0.gguf` | 210.402.464 B (~201 MiB) | `5d61aff620f0413c90693b39b2321ecd2f4e8d9ab55cd0e87906e198c871b357` |

`Qwen3-8B-Q4_K_M` será el maestro. `Laya` y `GLiNER` se usarán también como
clasificadores de marcos, además de las comparaciones clásicas y BERT. `GLiClass`
no está en la carpeta; queda condicionado a que se provea su checkpoint.

En el entorno actual hay `ollama` instalado, pero no `llama-cpp-python`. El plan
prioriza `llama.cpp` / `llama-cpp-python` por control de sampling, gramática JSON
y reproducibilidad; queda como prerrequisito instalarlo en el entorno del
proyecto.

## Decisiones congeladas

| Decisión | Valor |
|---|---|
| Corpus | ROTLK completo 2016–2019 |
| Muestra | 5.000 posts aleatorios, semilla 17 |
| Etiquetas | 16 marcos finos + toxicidad ordinal 0–3 |
| Cabezas gruesas | 7, derivadas con `taxonomy.py` |
| Referencia | Plata del LLM, sin revisión humana de los 5.000 |
| Oro humano 200 | Solo diagnóstico externo; no entrena ni corrige |
| Texto | Solo `text_raw`/`text_clean`; sin OP, quotes, subject ni stratum |
| Split | Por `thread_id`, 60/20/20, semilla 13 |
| Modelos comparados | TF-IDF+LR, BoW+SVM, embeddings+lineal, BERT/RoBERTa, Laya, GLiNER, GLiClass si se provee |
| Maestro | `Qwen3-8B-Q4_K_M.gguf` vía llama.cpp / llama-cpp-python |

## Fase 0 — Pre-registro de la corrida plata

Crear `docs/silver_classification_protocol.md` con:

- definición de plata confiada y de “maestro”;
- muestra, ventana, semilla y reglas de deduplicación;
- split por hilo y congelamiento del test;
- modelos comparados y presupuesto de cómputo;
- métricas y reglas de reporte;
- límites: sesgo del LLM, error heredado y marcos raros;
- uso del oro 200 solo como diagnóstico externo.

Agregar una enmienda a `docs/evaluation_protocol.md` y una entrada de Journal
posterior con los resultados. El pre-registro existente no se modifica en
silencio.

## Fase 1 — Construir la muestra de 5.000

Ajustes previstos al sampler:

- agregar `--start`/`--end` para fijar exactamente la ventana 2016-06 → 2019-11;
- para 5.000 posts, reducir el reservorio por mes a la cuota esperada, no a
  5.000 por mes, para no cargar ~200.000 hilos en RAM;
- conservar una unidad por hilo y descartar `text_clean` vacío.

Comando objetivo:

```bash
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst

keklab annotate sample \
  --source rotlk \
  --start 2016-06-01 --end 2019-11-01 \
  --random 5000 --targeted 0 --seed 17 \
  --out data/classification/samples/rotlk_5000.jsonl
```

Verificar 5.000 posts únicos, 5.000 hilos únicos, 0 textos vacíos, 0 duplicados
de `content_hash`, cobertura mensual completa y rango temporal correcto.

Construir tareas ciegas:

```bash
keklab annotate ai task \
  --input data/classification/samples/rotlk_5000.jsonl \
  --out data/classification/tasks/rotlk_5000.jsonl
```

Comprobar que el `prompt_sha256` sea
`30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769` y que no haya
`subject` ni `context` en el prompt renderizado.

## Fase 2 — Harness de inferencia LLM local

Crear `src/keklab/classification/` con:

| Archivo | Función |
|---|---|
| `backends.py` | Interfaz `LLMBackend`; `LlamaCppBackend`; backend falso para tests |
| `batch.py` | Lectura de tareas, sharding, reanudación, reintentos y salida cruda |
| `silver.py` | Conversión de salida cruda a `Annotation` con `tier="silver"` |
| `dataset.py` | Carga de plata, splits, one-hot de 16 marcos, 7 cabezas y toxicidad |
| `baselines.py` | TF-IDF+LR, BoW+SVM y embeddings+clasificador lineal |
| `transformer_model.py` | Fine-tuning BERT/RoBERTa multi-label |
| `zero_shot.py` | Adaptadores Laya, GLiClass y GLiNER como clasificadores de marcos |
| `evaluate.py` | Métricas, bootstrap por hilo y comparaciones pareadas |
| `cli.py` | Subcomandos `keklab classify ...` |
| `manifest.py` | Manifiesto reproducible de cada corrida |

Comandos objetivo:

```bash
keklab classify llm \
  --tasks data/classification/tasks/rotlk_5000.jsonl \
  --model /home/flynn/modelos_gguf/Qwen3-8B-Q4_K_M.gguf \
  --backend llama_cpp \
  --out data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
  --n-ctx 2048 --temperature 0 --seed 13 --resume --shard 1/4

keklab classify silver \
  --tasks data/classification/tasks/rotlk_5000.jsonl \
  --raw data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
  --out data/classification/silver/rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl
```

El backend debe:

- renderizar el prompt con `render_prompt(task)`;
- soportar modo `raw` y modo `chat` con la plantilla del GGUF;
- restringir la salida a JSON válido si llama.cpp lo permite;
- validar marcos, exclusividad `none`/`unclear` y toxicidad 0–3;
- reintentar una vez si el JSON falla;
- registrar fallos sin inventar etiquetas;
- guardar un manifiesto con SHA256 del GGUF, versión de llama.cpp,
  cuantización, `n_ctx`, `n_batch`, temperatura, semilla, hash del prompt, hash
  de la plantilla de chat y commit de git.

Smoke test obligatorio con 50 posts antes de los 5.000: medir tokens/s,
latencia y memoria, y extrapolar la corrida completa. `Qwen3-8B-Q4_K_M` ocupa
~5 GB; con la GTX 1070 Ti de 8 GB probablemente requiera contexto corto y
offload parcial, o correr en CPU.

## Fase 3 — Etiquetado plata de los 5.000

1. Correr el maestro en shards, con reanudación.
2. Convertir a registros plata (`Annotation`, `tier="silver"`,
   `annotator="llm/qwen3-8b-q4_k_m"`).
3. Reportar cobertura, fallos de parseo, distribución de marcos, toxicidad,
   confianza y longitud.
4. No revisar humanamente ni corregir etiquetas.
5. Diagnóstico externo separado: correr el mismo LLM sobre los 200 posts de oro
   y reportar acuerdo, Jaccard, kappa por cabeza y kappa cuadrática de
   toxicidad. Ese resultado no acepta, rechaza ni corrige la plata.

## Fase 4 — Split y dataset de modelado

- Extender `splits.py` para asignar hilos nuevos sin mover los ya asignados.
- Asignar 60/20/20 por hilo, semilla 13.
- Congelar y hashear el test antes de entrenar.
- Exportar un dataset con:
  - 16 columnas one-hot finas;
  - 7 columnas one-hot gruesas;
  - toxicidad 0–3 y versión binaria 0–1 vs 2–3;
  - `text_raw` y `text_clean`.

## Fase 5 — Modelos comparados

| Modelo | Rol | Entrenamiento | Notas |
|---|---|---|---|
| Qwen3-8B GGUF | Maestro / techo de referencia | No entrena | No se evalúa contra sus propias etiquetas |
| Laya | Zero-shot tipado | No entrena | Usar `laya-Q8_0.gguf` + `laya-head.safetensors` |
| GLiClass | Zero-shot | No entrena | Condicionado al checkpoint |
| GLiNER | Clasificación de marcos por extracción | Ajuste de umbral en dev | También puede usarse para E6 |
| TF-IDF + LR | Clásico | Train plata | Palabra y carácter n-gram; vectorizador solo en train |
| BoW + SVM lineal | Clásico | Train plata | `LinearSVC` con balanceo |
| Embeddings + LR | Clásico | Train plata | SentenceTransformers o embeddings de Laya |
| BERT/RoBERTa | Transformer fine-tuned | Train plata | Multi-label + cabeza de toxicidad; batch pequeño por 8 GB VRAM |

Reglas:

- E0: comparar `text_raw` vs `text_clean` en dev; `text_clean` solo se adopta si
  mejora de forma consistente.
- Selección de hiperparámetros en dev; una sola evaluación final en test.
- Toxicidad como tarea ordinal/multiclase separada.
- Reportar también las 7 cabezas derivadas, aunque el modelo entrene las 16
  finas.
- Los marcos con muy pocos positivos se reportan como descriptivos, no como F1
  válido.

## Fase 6 — Evaluación

Por marco fino y por cabeza gruesa:

- precisión, recall y F1 por clase;
- F1 macro y micro;
- positivos reales y predichos;
- intervalos de confianza por bootstrap de 1.000 remuestreos a nivel hilo,
  semilla 13.

Toxicidad:

- kappa cuadrática ponderada;
- MAE;
- matriz de confusión;
- versión binaria 0–1 vs 2–3.

Comparación entre modelos:

- bootstrap pareado por hilo para diferencias de F1;
- McNemar para aciertos/errores pareados si aplica;
- costo: segundos por 1.000 posts, RAM/VRAM pico, cobertura y fallos de parseo.

Reportes:

- tabla principal: modelos pequeños contra plata test;
- tabla secundaria: LLM/Laya/GLiNER/BERT contra los 200 de oro, solo como
  diagnóstico externo;
- aclarar que la tabla principal mide imitación del maestro, no verdad.

## Fase 7 — Reproducibilidad y cierre

Estructura propuesta:

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

Además:

- registrar datasets, modelos y reportes en `keklab registry`;
- persistir `prompt_sha256`, hash del GGUF y hash de la plantilla de chat;
- tests con backend falso para parseo, reanudación, sharding, conversión a
  plata, split estable, métricas y bootstrap;
- Journal con resultados y limitaciones;
- no commitear `data/annotations/` ni artefactos grandes;
- no hacer commit ni push salvo pedido explícito.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| La plata hereda sesgos y errores del LLM | Documentarlo; no llamarla oro; usar el oro 200 solo como diagnóstico |
| Evaluar modelos contra el maestro premia imitarlo, no acertar | Reportar la limitación y separar la tabla diagnóstica contra oro |
| Marcos finos raros siguen con pocos positivos | Reportarlos descriptivamente; no forzar F1 |
| 5.000 posts en 8 GB VRAM pueden tardar mucho | Smoke test, sharding, reanudación, Q4 y estimación previa |
| JSON inválido o evidencia no verbatim | Gramática JSON, validación estricta, reintento y registro de fallos |
| El prompt rinde distinto en modelos instruct | Modo `chat` con plantilla del GGUF y hash de plantilla registrado |
| El split mueve hilos al agregar datos | Asignación estable y manifiesto append-only |
| `llama-cpp-python` no está instalado | Instalarlo en el entorno del proyecto antes de la fase 2 |

## Prerrequisitos

1. Instalar `llama-cpp-python` (y `scikit-learn`, `transformers`, `torch`,
   `sentence-transformers`, adaptadores de Laya/GLiNER) en el entorno del
   proyecto. Hoy `torch`, `transformers` y `scikit-learn` están en otros
   venv (`NetworkAnalysis`, `NeuralNetworks`), no en el entorno de `keklab`.
2. Decidir el modelo BERT/RoBERTa a usar (`bert-base-uncased`,
   `roberta-base` u otro).
3. Confirmar que `GLiClass` se proveerá o que se omite de la primera corrida.
4. Implementar `--start`/`--end` en el sampler y la asignación estable de splits.

## Estado y próximos pasos

- Plan registrado en esta entrada.
- No hay cambios de código en esta entrada.
- Siguiente paso: escribir `docs/silver_classification_protocol.md`, la enmienda
  a `docs/evaluation_protocol.md` y el harness con backend falso; el smoke test
  con `Qwen3-8B-Q4_K_M` se hace cuando `llama-cpp-python` esté instalado.

## Git

- Esta entrada y el plan se agregan en un commit de documentación.
- No se incluye el cambio previo no relacionado de
  `Journal/Journal PLN. 5. 02-11-26.md`.
- Push a `origin/master` solicitado explícitamente.
