# Journal PLN — Entrada 7 (03-11-2026)

## Contexto

La entrada 6 dejó el sampler de ROTLK implementado y validado, el código sin
commit y el piloto corriendo. Esta entrada cierra esa ejecución y documenta la
auditoría del resultado. No repite el diseño del sampler, el hallazgo del dump
ni la cobertura original de pruebas: se concentra en lo que apareció al
inspeccionar la muestra real.

## Consolidación del repositorio

- Se revisó el diff completo de `common/io.py`, `annotation/sampler.py`,
  `annotation/cli.py`, `common/paths.py`, `pyproject.toml` y los tests nuevos.
- La suite completa pasó con **80 pruebas**.
- Código, tests y la dependencia opcional `zstandard` se commitearon juntos:

  ```
  8d59ce6 feat: stream ROTLK tar.zst directly for annotation sampling
  ```

- README, documentación y journal quedaron en un commit separado:

  ```
  5763f24 docs: document ROTLK streaming validation and pilot execution
  ```

- Nada se empujó a `origin`.

## Primera ejecución completa

El primer piloto terminó con:

```
3,397,911 hilos / 134,529,233 posts / 2,068.8 s
30 samples: 20 random + 10 targeted
```

El tiempo de reloj de pared fue mucho mayor porque la máquina estuvo suspendida
durante la noche; el tiempo activo de stream fue de ~34 min. El archivo de
salida no existe hasta que termina el muestreo, así que no hay resultados
parciales que revisar mientras corre.

## Auditoría 1: borde de la ventana

Al revisar los 30 samples aparecieron dos posts con mes `2017-11`, mientras la
documentación hablaba de una ventana `2017-12 → 2019-11`.

La causa era el filtro por cadena de mes: un post del mes de corte pero anterior
al día de corte pasaba igual. El cálculo real del dump es:

```
último timestamp: 2019-11-01T10:15:36Z
ventana (24 meses): 2017-11-11T10:15:36Z → 2019-11-01T10:15:36Z
```

La corrección fue en `71e9438 fix: filter ROTLK pilot window by exact timestamp`:

- nuevo helper `_windowed()` que compara `SamplePost.timestamp_utc` contra el
  cutoff exacto;
- el filtro se aplica a random, dirigido y posts vacíos;
- la ventana calculada se registra en el log;
- tests para el borde exacto y para un post del mes de corte anterior al día de
  corte.

La suite subió a **82 pruebas**.

## Auditoría 2: calidad del texto y balance dirigido

La segunda pasada ya no tenía posts fuera de ventana, pero mostró dos problemas
más:

1. Un sample aleatorio era solo un quote link; tras la limpieza quedaba con
   `text_clean` vacío y no servía para anotar marcos.
2. El reparto dirigido quedó 4/4/2 porque el primer marco consumía el cupo
   completo antes de pasar al siguiente.

La corrección fue en
`32689cb fix: skip empty cleaned posts and balance targeted ROTLK samples`:

- `_thread_sample(..., require_text=True)` descarta posts cuyo texto limpio
  queda vacío; los samples vacíos explícitos usan `require_text=False`;
- el cupo dirigido se reparte con `divmod` sobre los marcos, sin que el primero
  acapare el remanente;
- test para un hilo que solo contiene un quote link.

La suite quedó en **83 pruebas**.

## Ejecución final

La tercera pasada, ya con ambas correcciones, terminó con:

```
3,397,911 hilos / 134,529,233 posts / 2,025.0 s
ventana: 2017-11-11T10:15:36Z -> 2019-11-01T10:15:36Z
30 samples: 20 random + 10 targeted
```

Distribución verificada:

- 20 aleatorios, un post por mes, en 20 meses distintos.
- 10 dirigidos: 4 `rusophobia`, 3 `sinophobia`, 3 `accelerationism`.
- 30 posts y 30 hilos únicos.
- 0 samples fuera de la ventana.
- 0 samples con `text_clean` vacío.
- 27 con contexto de OP; los otros 3 son el propio OP.
- 21 posts padre citados.

El resultado final quedó registrado en la entrada 6.

## Estado de git

- `8d59ce6`: código, tests y `pyproject.toml`.
- `5763f24`: README, documentación y entradas 6–7.
- `71e9438`: filtro exacto de ventana.
- `32689cb`: filtro de texto limpio y balance dirigido.
- El JSONL del piloto se commitea aparte de este journal.
- No se hizo `push`.

## Siguiente paso

Anotar los 30 samples con la CLI interactiva:

```bash
keklab annotate run \
  --input data/samples/rotlk_pilot.jsonl \
  --annotator flynnso \
  --guideline v0 \
  --round 1 \
  --out data/annotations/rotlk_pilot_r1.jsonl
```

Después: self test-retest del ~20% y revisión del codebook antes de congelar
`v1`. E0/E2 siguen bloqueados hasta que existan anotaciones humanas.
