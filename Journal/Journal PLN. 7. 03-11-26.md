# Journal PLN — Entrada 7 (03-11-2026)

## Contexto

La entrada 6 cerró con el sampler de ROTLK implementado y validado, pero con el
código y la documentación todavía sin commit, y con el piloto recién lanzado.
Esta entrada registra la consolidación del repositorio y la ejecución del
piloto real. No repite el diseño del sampler, el hallazgo del dump ni la
cobertura de pruebas, que ya quedaron documentados en la entrada 6.

## Consolidación del repositorio

- Se revisó el diff completo de `common/io.py`, `annotation/sampler.py`,
  `annotation/cli.py`, `common/paths.py`, `pyproject.toml` y los tests nuevos.
- La suite completa volvió a pasar: **80 pruebas**, 2 advertencias de pandas.
- El código, los tests y la dependencia opcional `zstandard` se commitearon
  juntos como:

  ```
  8d59ce6 feat: stream ROTLK tar.zst directly for annotation sampling
  ```

- README, documentación y journal se dejaron fuera de ese commit para mantener
  la separación entre código y documentación. Nada se empujó a `origin`.

## Ejecución del piloto real

Se lanzó la pasada completa de 20 posts aleatorios + 10 dirigidos con la
semilla 13 sobre el dump externo. El comando es el documentado en la entrada 6;
aquí solo se registra la operación.

Observaciones durante la ejecución:

- El archivo de salida `data/samples/rotlk_pilot.jsonl` no se crea hasta que
  termina el muestreo; no hay resultados parciales que inspeccionar mientras
  corre.
- Rendimiento sostenido: alrededor de **1,670 hilos/s** y **65,000 posts/s**.
  A las 2.4M de hilos y 93.6M de posts, el tiempo activo de stream era
  **1,437 s**.
- El tiempo de reloj de pared (~11 h) no refleja el trabajo real: la máquina
  estuvo suspendida durante la noche. El tiempo de CPU del proceso era de
  ~25 min.
- El proceso seguía en estado `R` y avanzando al momento de escribir esta
  entrada. Con ~3.7M de hilos estimados, restaba poco más de un tercio de la
  pasada.

Al cierre de esta entrada el piloto **todavía no había terminado**, así que la
distribución final por motivo, mes y marco sigue pendiente. El marcador de la
entrada 6 se completa cuando el proceso termine.

## Estado de git

- `8d59ce6` contiene únicamente código, tests y `pyproject.toml`.
- Este segundo commit incluye README, `docs/annotation_guidelines.md`,
  `docs/pipeline_draft.md` y las entradas 6 y 7 del journal.
- No se hizo `push`.

## Siguiente paso

Cuando el proceso termine:

1. Contar los 30 samples por `reason`, mes y marco.
2. Verificar que no haya posts vacíos inesperados ni hilos repetidos.
3. Completar el resultado del piloto en la entrada 6.
4. Commitear el JSONL del piloto por separado.
5. Empezar la anotación interactiva con `keklab annotate run`.
