# Journal PLN — Entrada 11 (03-11-2026)

## Contexto

La entrada 10 fijó la fórmula `n = K / p` y concluyó que 200 posts eran el
primer corte útil para reemplazar supuestos de prevalencia por datos. Esta
entrada ejecuta ese corte con la opción A: conservar la muestra auditada de 30
y agregar 170 posts aleatorios. No repite el cálculo de tamaño muestral ni el
cambio `gender` → `antifeminism`; solo registra la decisión, la ejecución y la
verificación del archivo final.

## Decisión

Se adopta **opción A con 200 posts en total**:

- 30 existentes: 20 aleatorios + 10 dirigidos.
- 170 nuevos aleatorios sobre la misma ventana.
- Mezcla final: **190 aleatorios + 10 dirigidos = 200 posts y 200 hilos
  únicos**.

La ventana se mantiene anclada al máximo del dump:
`2017-11-11T10:15:36Z → 2019-11-01T10:15:36Z`.

Razones para 200:

- Es el primer punto donde `K=10` es alcanzable para un marco con prevalencia
  ≥5% (`10 / 0.05 = 200`).
- A 15–20% de prevalencia produce 30–40 positivos por marco, suficiente para
  una primera versión del modelo grueso.
- Conserva los 30 posts ya verificados en las entradas 6 y 7.
- Los 10 dirigidos se excluyen de las estimaciones de prevalencia; solo
  entrenan/calibran.

## Ejecución

Comando de muestreo:

```bash
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
keklab annotate sample --source rotlk --months 24 \
  --random 170 --targeted 0 --seed 17 \
  --out data/samples/rotlk_pilot_extra.jsonl
```

Resultado de la pasada completa del dump:

```
3,397,911 hilos / 134,529,233 posts en 1,703.6 s
170 samples -> data/samples/rotlk_pilot_extra.jsonl
by reason: {"random": 170}
```

La fusión se hizo con un script que recorre primero los 30 y después los 170,
deduplicando por `post_id` y `thread_id`. **No hubo colisiones**: 0 posts y 0
hilos compartidos entre ambas muestras, así que no hizo falta reponer desde el
reservorio. El archivo final quedó en:

```
data/samples/rotlk_pilot_200.jsonl
```

El archivo de 30 se conserva como procedencia, y el de 170 como salida cruda
del muestreo.

## Verificación

Todos los chequeos de aceptación pasaron:

| Chequeo | Resultado |
|---|---:|
| Posts totales | 200 |
| Posts únicos | 200 |
| Hilos únicos | 200 |
| Aleatorios | 190 |
| Dirigidos | 10 |
| `text_clean` vacíos | 0 |
| Timestamps fuera de ventana | 0 |
| Meses calendario cubiertos | 25 |
| Duplicados de `content_hash` | 0 |
| Duplicados de `text_raw` | 0 |

El conteo de meses es **25, no 24**, porque la ventana de 24 meses exactos
empieza el 11-11-2017 y termina el 01-11-2019: noviembre de 2017 y noviembre de
2019 quedan parciales. Cada bucket tiene entre 6 y 10 posts. El criterio de
aceptación se corrigió en `docs/pipeline_draft.md` para reflejarlo.

Los campos de los 200 registros coinciden con los del archivo base y los del
extra (`content_hash`, `context`, `country`, `is_op`, `period`, `post_id`,
`quotes`, `source`, `stratum`, `subject`, `text_clean`, `text_raw`,
`thread_id`, `timestamp_utc`). Todos tienen `source: kek`.

## Soporte esperado

Con 200 posts, la probabilidad de alcanzar `K` positivos por marco es:

| Prevalencia | Positivos esperados | P(≥10) | P(≥20) | P(≥30) |
|---:|---:|---:|---:|---:|
| 5% | 10 | 0.545 | 0.003 | 0.000 |
| 10% | 20 | 0.996 | 0.534 | 0.016 |
| 15% | 30 | 1.000 | 0.985 | 0.530 |
| 20% | 40 | 1.000 | 1.000 | 0.972 |

Si los marcos nuevos están en 15–20%, la tanda alcanza para una primera versión
del modelo de 8 cabezas. Los que queden por debajo de 5% van a necesitar
muestreo dirigido específico, no más posts aleatorios a ciegas.

## Estado de git

- Commit del sample: `data: expand ROTLK pilot to 200 posts`, con
  `rotlk_pilot_200.jsonl` y `rotlk_pilot_extra.jsonl`. La fusión se hizo con un
  script inline, no versionado.
- Commit de documentación: este journal y `docs/pipeline_draft.md`.
- Se empuja a `origin` al cerrar la entrada, según lo pedido.

## Siguiente paso

Anotar los 200 posts como ronda 1:

```bash
keklab annotate run \
  --input data/samples/rotlk_pilot_200.jsonl \
  --annotator flynnso \
  --guideline v0 \
  --round 1 \
  --out data/annotations/rotlk_pilot_r1.jsonl
```

Al terminar, calcular `p_hat` por marco separando los 190 aleatorios de los 10
dirigidos y recalcular `n = K / p_hat` para la próxima tanda.
