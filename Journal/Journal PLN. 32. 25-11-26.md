# Journal PLN. 32. 25-11-26

Hoy se completó el entrenamiento primario de Laya y sus predicciones. No se
entrenó GLiNER: el usuario pidió postergarlo. Tampoco se evaluó ni se marcó el
test congelado.

## 1. Preparación local

- La versión inicial del trabajo falló porque el checkpoint base no tenía los
  subdirectorios `tokenizer/` y `encoder/` que Laya espera. Se crearon desde los
  archivos existentes de `/home/flynn/modelos_originales/laya-base`.
- El segundo intento falló porque ModernBERT activaba Triton/Inductor y este
  equipo usa una GTX 1070 Ti (`sm_61`), no soportada por Triton. Se fijó
  `"reference_compile": false` en
  `/home/flynn/modelos_originales/laya-base/encoder/config.json`.
- Estos ajustes son locales al checkpoint y no forman parte del repositorio.

## 2. Entrenamiento

- Job: `20261112164154-fc2f162b-laya`, `laya-frozen-softce`.
- Configuración: encoder congelado, `soft-ce`, 4 épocas, `micro_batch=4`,
  `grad_accum=4`, `max_len=512`, `head_max_len=192`, fp16/AMP, semilla 13 y
  calibración del 10% limitada a 400 elementos.
- El job terminó las 4 épocas y escribió el checkpoint en
  `data/classification/models/laya/laya-frozen-softce`.
- Pérdida media por época: `0.2429`, `0.2100`, `0.1944`, `0.1828`.
- Evaluación sobre los 17,000 elementos de `laya/dev.jsonl`, con 425
  elementos compartidos con entrenamiento/calibración: accuracy `0.8116 →
  0.9327`, loss `0.4382 → 0.1771`, ECE `0.0323 → 0.0093`, Brier multiclase
  `0.2697 → 0.0981`. No es una evaluación independiente.
- La calibración `score` se ajustó con solo 24 elementos; la calibración `noul`
  usó 376. Las temperaturas finales son `1.0`, `1.8146` y `1.3498`.

## 3. Predicciones

- El primer pase con `batch_size=16` agotó memoria GPU y Laya aplicó su fallback
  a CPU para una solicitud. Se detuvo ese proceso para no registrar
  predicciones mezcladas en dispositivos; el checkpoint de entrenamiento ya
  estaba guardado.
- Se reinició únicamente la fase de predicción desde ese checkpoint, con
  `batch_size=1`, `device="cuda"` y advertencias de fallback convertidas en
  error. Se generaron 1,000 predicciones de dev y 1,000 de test, sin fallback a
  CPU y con un máximo de 2,635.7 MiB de memoria GPU.
- Los hashes de pesos y predicciones quedan registrados en
  `data/classification/manifests/laya-frozen-softce.json`. Los pesos y las
  predicciones no se versionan, según la política del repositorio.
- Se verificó de nuevo el hash del test congelado:
  `afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`.
  `evaluate-test-once` y `comparison-report` siguen en `blocked`.

## 4. Estado final

- Cola: `setup`, `export` y Laya en `done`; GLiNER y las demás corridas
  pendientes siguen en `pending`; cero jobs en `failed`.
- No se hizo auditoría adicional porque el usuario indicó que no era necesaria.
- No se inició GLiNER ni ninguna evaluación del test.
