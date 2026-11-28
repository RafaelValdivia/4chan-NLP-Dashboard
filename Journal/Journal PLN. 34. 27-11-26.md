# Journal PLN. 34. 27-11-26

Después del journal anterior se trasladó el informe consolidado de benchmarks a
`docs/` y se actualizaron todas las referencias al antiguo directorio. No
cambiaron métricas, predicciones ni resultados.

## 1. Cambio de ubicación

- Se movió `data/classification/reports/benchmarks-dev.md` a
  `docs/benchmarks-dev.md` con `git mv`.
- Se actualizó la ruta del informe en:
  - `data/classification/manifests/benchmarks-dev.json`.
  - `data/classification/manifests/classical-baselines.json`.
  - `data/classification/reports/classical-baselines.md`.
  - `Journal/Journal PLN. 33. 27-11-26.md`.
- El JSON de manifiesto se validó y `git diff --check` pasó. El hash del informe
  no cambió porque el contenido del archivo se conservó al moverlo.

## 2. Versionado

- El primer commit (`323a0f0`) registró el movimiento del archivo.
- Las cuatro actualizaciones de referencia quedaron fuera de ese commit porque
  aún no estaban en el índice; se confirmaron con `git status` y se registraron
  en un segundo commit (`4dbc289`).
- Ambos commits se enviaron a `origin/fix/training-env-compat-20261121`.
- No quedaron referencias al antiguo `data/classification/reports/benchmarks-dev.md`.

## 3. Estado final

- El benchmark de desarrollo sigue siendo el de cinco algoritmos entrenados:
  tres clásicos, Laya soft-CE y GLiNER.
- Las dos ablaciones opcionales de Laya siguen pendientes y sin predicciones.
- El test congelado no se evaluó ni se marcó; su hash permanece
  `afae38a9157c64197c83839812a4846918a4506f51c02c916c51ef6f8fde21b4`.
- No se modificaron modelos, predicciones, métricas ni código de entrenamiento.
