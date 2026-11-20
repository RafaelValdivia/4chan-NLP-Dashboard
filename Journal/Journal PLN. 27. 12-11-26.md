# Journal PLN — Entrada 27 (12-11-2026)

## Contexto

Continuación de la entrada 23. El entrenamiento de Laya y GLiNER sigue bloqueado
por los cuatro wheels CUDA corruptos de `torch`, `cublas`, `cudnn` y `triton`.
Para no dejar el pipeline detenido, se ejecutaron las baselines clásicas, que
son CPU-only y no dependen de CUDA.

También se detuvo la descarga segmentada de `torch` que seguía corriendo en
segundo plano. No hay procesos de descarga activos.

## Trabajo realizado

Se ejecutó directamente `keklab.training.baselines_runner.run()` con el venv
`NetworkAnalysis`, sin pasar por la cola, porque el job `baselines` depende de
`setup` y `setup` sigue bloqueado por los wheels corruptos.

- Train: 3.000 filas.
- Dev: 1.000 filas.
- Test: 1.000 filas; se generaron predicciones, pero **no se evaluó test**.
- Semilla: 13.
- No se usaron etiquetas de test para entrenar ni para ajustar umbrales.

Modelos entrenados:

1. `tfidf-lr`: TF-IDF `(1,2)`, 50k features, LR one-vs-rest `C=2.0`, pesos
   balanceados; incluye cabeza de toxicidad de 4 clases.
2. `bow-svm`: conteos binarios `(1,2)`, 50k features, LinearSVC one-vs-rest
   `C=1.0`, pesos balanceados; sin cabeza de toxicidad.
3. `emb-lr`: TF-IDF → SVD 256 → escalado → LR one-vs-rest `C=1.0`; sin cabeza
   de toxicidad.

## Resultados dev

Los umbrales por marco se seleccionaron en dev, por lo que estas métricas son
optimistas. No son métricas de test.

| modelo | macro F1 | macro F1 sustantivo | micro F1 | exact match | etiquetas/post | tox QWK | tox MAE | tox F1 binario | IC 95% por hilo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| tfidf-lr | 0.328 | 0.313 | 0.680 | 0.701 | 1.25 | 0.544 | 0.582 | 0.609 | 0.240–0.400 |
| bow-svm | 0.303 | 0.284 | 0.685 | 0.702 | 1.21 | n/a | n/a | n/a | 0.247–0.352 |
| emb-lr | 0.255 | 0.229 | 0.654 | 0.690 | 1.27 | n/a | n/a | n/a | 0.194–0.314 |

### Aclaraciones sobre la tabla

- Son métricas **dev**, no test. Test no se evaluó.
- `exact match` es coincidencia exacta del conjunto completo de 16 etiquetas. El
  70.2 % de dev es exactamente `{none}`, y predecir siempre `{none}` da exact
  match 0.702. Por eso el ~0.70 de los modelos no demuestra habilidad
  multi-label.
- `micro F1` no es “porcentaje de posts correctos”: agrega TP/FP/FN de las 16
  decisiones. Precisión/recall micro: `tfidf-lr` 0.691/0.670, `bow-svm`
  0.707/0.664, `emb-lr` 0.659/0.650.
- `labels/post` es el promedio de etiquetas positivas predichas. El promedio
  real en dev es 1.288.
- Los hiperparámetros de los modelos se fijaron a priori; no se ajustaron. Lo
  único seleccionado en dev fueron los 16 umbrales por etiqueta.
- `n/a` en toxicidad significa “sin cabeza de toxicidad”, no cero.
- El reporte `data/classification/reports/classical-baselines.md` contiene las
  tablas de F1 por etiqueta y de umbrales por etiqueta.

Lectura rápida:

- `tfidf-lr` gana en macro F1 y macro sustantivo; es la baseline clásica más
  fuerte.
- `bow-svm` queda muy cerca y tiene el mejor micro F1 y exact match, pero no
  produce probabilidades calibradas ni toxicidad.
- `emb-lr` es la más débil; la reducción a 256 componentes pierde señal para
  marcos raros.
- `none` es el único marco con F1 alto (~0.87 en los tres modelos).
- `meta_topic` y `unclear` quedan en 0.000; `homophobia`, `transphobia` y
  `misogyny` son muy inestables.
- La toxicidad de `tfidf-lr` es moderada: QWK 0.544 y MAE 0.582.

### Umbrales

Los 16 umbrales por etiqueta de cada modelo están tabulados en
`data/classification/reports/classical-baselines.md` y en
`data/classification/reports/evaluation-dev.json`. No son parámetros aprendidos
por el clasificador: se eligen por búsqueda separada maximizando F1 por etiqueta
en dev. Test, cuando se evalúe, usará esos umbrales congelados.

### Limitación de test

`evaluate_split("test")` vuelve a evaluar todos los modelos disponibles. Si se
puntúan las baselines ahora, la evaluación final tendría que reutilizar esos
resultados o volver a puntuarlas. No es una limitación estadística: es una
limitación del código de evaluación y del lock one-shot. Hay que decidir si se
espera a Laya/GLiNER o se enmienda el flujo para reutilizar scores por modelo.

## Artefactos

- Predicciones: `data/classification/predictions/{tfidf-lr,bow-svm,emb-lr}/{dev,test}.jsonl`
- Métricas dev completas: `data/classification/reports/evaluation-dev.json`
- Reporte legible: `data/classification/reports/classical-baselines.md`
- Manifiesto de entrenamiento: `data/classification/manifests/classical-baselines.json`

## Reproducibilidad y manifiesto

El manifiesto `data/classification/manifests/classical-baselines.json` se
completó después de la corrida con hiperparámetros, versiones, commit, hashes de
datos/split/test, hashes de predicciones y rutas de salida. El runtime de pared
no se instrumentó y queda registrado como no disponible.

- Comando efectivo: `PYTHONPATH=src /home/flynn/PyVenvs/NetworkAnalysis/bin/python -c "from keklab.training import baselines_runner; import json; print(json.dumps(baselines_runner.run(), indent=2))"`
- Python 3.12.3; scikit-learn 1.9.0; numpy 2.5.0; pandas 3.0.3; scipy 1.18.0;
  joblib 1.5.3.
- Commit documentado: `58443a3`; árbol sucio con código/datos sin commit.
- Hash del test congelado: `afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`.
- No se puntuó test; no existe `evaluation-test.json`.

## Estado del pipeline

- Test sigue congelado y sin evaluar. Las predicciones de test de las baselines
  existen, pero no se han leído para seleccionar nada.
- Laya y GLiNER siguen bloqueados: `setup` no puede instalar un `torch` con
  `sm_61` porque los cuatro wheels grandes están corruptos y faltan
  dependencias transitivas en el wheelhouse.
- El job `setup` sigue en `running/` como huérfano; el worker está detenido.
- La descarga de `torch` se detuvo. Los segmentos parciales quedaron en
  `/tmp/opencode/dl_segments`.
- La GPU está libre; no hay entrenamiento GPU en curso.

## Próximos pasos

1. Recuperar wheels válidos de `torch 2.5.1+cu121`, `cublas 12.1.3.1`,
   `cudnn 9.1.0.70` y `triton 3.1.0`, verificando SHA256.
2. Completar el wheelhouse con `tokenizers==0.23.3`, `huggingface-hub==1.33.0`
   y las dependencias de `typer`/`rich`.
3. Re-ejecutar `setup`, confirmar `sm_61` y relanzar el worker.
4. Entrenar Laya frozen + soft-CE, luego RLCD; GLiNER después.
5. Decidir si se espera a Laya/GLiNER para evaluar test una vez, o se enmienda
   el flujo para puntuar y reutilizar las baselines sin re-score.

## Estado de git

- `Journal/Journal PLN. 19. 11-11-26.md` modificado.
- `models/SHA256SUMS` modificado.
- `src/keklab/common/cli.py` modificado.
- `src/keklab/training/` sin trackear.
- `tests/test_training_queue.py` y `tests/test_training_evaluate.py` sin
  trackear.
- `docs/finetuning_protocol.md` sin trackear.
- Datos, predicciones, reportes y manifiestos nuevos sin trackear.
- Esta entrada es un archivo nuevo.

No se ha evaluado test ni se ha modificado el protocolo de pre-registro. El
reporte `classical-baselines.md` y el manifiesto se actualizaron con las
aclaraciones metodológicas y de reproducibilidad.
