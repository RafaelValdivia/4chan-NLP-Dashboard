# Journal PLN. 33. 27-11-26

Hoy se completó GLiNER, se calculó el benchmark de desarrollo de todos los
algoritmos con predicciones disponibles y se registraron los resultados. No se
evaluó ni se marcó el test congelado.

## 1. GLiNER

- El job `20261112164154-93529e5d-gliner` terminó con código 0 en 974.4 s.
- Configuración final: 3 épocas, 1,125 pasos, micro-batch 1, acumulación 8,
  batch efectivo 8, fp32, CUDA, `token_max_length=384`, `max_width=12` y
  `max_types=25`.
- El entrenamiento reportó `train_runtime=770.9491 s`, 1.459 pasos/s y
  `train_loss=5.1674092415703665`.
- Se corrigió el runner para evitar la importación de TensorFlow/Keras, forzar
  CUDA sin fallback a CPU, contar los pasos con acumulación de gradiente, usar
  fp32 en la GPU `sm_61`, limitar los tokens a 384 y fallar ante OOM en vez de
  omitir batches con pérdida cero.
- La configuración local del tokenizer base se ajustó a `model_max_length=384`.
  Este cambio es local al checkpoint y no forma parte del repositorio.
- El modelo quedó en `data/classification/models/gliner/gliner-finetune` y las
  predicciones en `data/classification/predictions/gliner-finetune/`. El manifest
  registra los hashes; pesos y predicciones no se versionan.

## 2. Evaluación de desarrollo

- Se ejecutaron los jobs encolados de baselines clásicos y de evaluación de dev.
  Ambos terminaron con código 0.
- Se evaluaron cinco algoritmos: `tfidf-lr`, `bow-svm`, `emb-lr`,
  `laya-frozen-softce` y `gliner-finetune`.
- `gliner-finetune` quedó primero en F1 macro de dev con 0.418, seguido de
  `tfidf-lr` con 0.328. El modelo primario pre-registrado sigue siendo
  `laya-frozen-softce`; la tabla es descriptiva y no cambia esa decisión.
- La coincidencia exacta de los modelos ronda 0.70, cercana a la línea base de
  predecir siempre `{none}` (0.702). Las métricas de dev seleccionan umbrales
  sobre las mismas filas que puntúan, por lo que son optimistas.
- Solo `tfidf-lr` y `laya-frozen-softce` tienen cabeza de toxicidad; los demás
  se reportan como `n/a`, no como cero.

## 3. Corrección del evaluador

- La primera evaluación trataba las etiquetas `none` y `unclear` ausentes en las
  predicciones de GLiNER como si tuvieran probabilidad 0.0. Como el umbral
  seleccionado también era 0.0, todas las publicaciones quedaban marcadas como
  `none` y el F1 sustantivo era 0.
- `select_thresholds` ahora ignora las etiquetas ausentes y les asigna un umbral
  inutilizable de 1.0. `_postprocess` también ignora etiquetas que no están en
  el mapa de probabilidades. Se añadieron dos pruebas de regresión.
- Después de la corrección, GLiNER pasó de F1 macro 0.052 a 0.418 y F1
  sustantivo 0.000 a 0.415. Los otros modelos, que sí emiten las 16 etiquetas,
  no cambiaron.

## 4. Estado final

- Informe consolidado: `docs/benchmarks-dev.md`.
- Métricas completas: `data/classification/reports/evaluation-dev.json`.
- Manifest del benchmark: `data/classification/manifests/benchmarks-dev.json`.
- Cola: 6 jobs en `done`, 2 opcionales de Laya en `pending`, 2 jobs del test
  congelado en `blocked` y cero en `failed`.
- El hash del test congelado se verificó de nuevo:
  `afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`.
  No existe `evaluation-test.json` y no se abrió el lock de evaluación única.
- Verificación: `py_compile` y las 8 pruebas de entrenamiento/evaluación
  pasaron. La suite completa quedó en 240 pass, 14 fail y 1 error de
  importación; las fallas son las ya conocidas de DuckDB/`pytz` y la API sin
  `fastapi`, sin relación con estos cambios.
