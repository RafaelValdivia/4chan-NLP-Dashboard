# Journal PLN — Entrada 6 (02-11-2026)

## Contexto

La entrada 5 dejó el sampler de ROTLK preparado pero bloqueado: el dump no
estaba localizado y solo se había probado con parquet sintético. En esta
iteración se encontró el archivo en el disco externo de la computadora y se
validó el camino completo de lectura y muestreo.

## Hallazgo del dump

El disco `/dev/sda1` (ext4, etiqueta `Archivos`) está montado en:

```
/run/media/flynnso/Archivos
```

Contiene un único archivo:

```
/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
```

Características verificadas:

- 22.4 GiB comprimidos en un solo frame zstd.
- Un miembro tar: `pol_062016-112019_labeled.ndjson`.
- 113.86 GB descomprimidos.
- Una línea NDJSON = un hilo completo con lista `posts`.
- Cobertura temporal 2016-06 → 2019-11; el archivo está ordenado
  cronológicamente.
- Muestra de los primeros 5 GB: 161,509 hilos y 6.25M posts, todos con
  UTF-8/JSON válidos. Extrapolación: ~3.7M hilos y ~142M posts.
- Los posts incluyen `perspectives` (scores de Perspective API), `entities` y
  la variante con typo `entitites` (NER), además de campos nativos de 4chan.
- **No hay etiquetas humanas de marcos.** El sufijo `labeled` se refiere a
  etiquetas automáticas auxiliares, no al conjunto oro.

## Decisión: leer en sitio, sin copiar

El dump no se copia al repositorio, no se extrae y no se convierte
preliminarmente a parquet. El sampler abre el `.tar.zst` directamente:

```
zstd (stdlib de Python 3.14 o fallback) → tarfile en modo streaming → NDJSON
```

`iter_ndjson()` ahora reconoce `.tar.zst`, `.tar.zstd`, `.tzst`, `.zst`, `.gz`
y `.bz2`. Para el tar recorre únicamente miembros `.ndjson`/`.jsonl`, decodifica
con reemplazo ante bytes inválidos y omite líneas JSON malformadas.

La lectura completa del stream descomprimido tarda ~155 s. El costo real del
muestreo es el parseo JSON y la búsqueda de términos; por eso se implementó una
sola pasada con reservorios.

## Implementación

### Sampler directo

`sample_rotlk_stream()` en `annotation/sampler.py`:

- Una sola pasada sobre el archivo.
- Reservorio uniforme por mes para la muestra aleatoria.
- Reservorio por marco y por mes para la muestra dirigida.
- Reservorio separado para posts vacíos/solo-imagen (`--include-empty`).
- Construye el `SamplePost` con contexto de OP y posts citados solo cuando un
  candidato entra al reservorio; no canonicaliza hilos descartados.
- La ventana se ancla al último timestamp del corpus. Con `--months 24` y este
  dump, la ventana es **2017-12 → 2019-11**.
- La muestra dirigida también se filtra a la ventana, a diferencia del sampler
  anterior sobre parquet.
- El término buscado se registra en `stratum.term`; el marco en
  `stratum.frame`.

### Optimización

La primera versión usaba una regex case-insensitive sobre cada post y convertía
cada timestamp a `datetime`. El smoke test de 5,000 hilos tardaba 9.5 s. Se
cambió a:

- minúsculas una vez por post y comparación de subcadenas;
- extracción numérica barata del epoch en el loop caliente;
- conversión a `datetime` solo para candidatos seleccionados o que hicieron
  match.

El mismo smoke test bajó a **3.6 s** para 5,000 hilos / 211,894 posts. Eso deja
una pasada completa en el orden de decenas de minutos, no horas.

### CLI

```bash
export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst

# smoke test
keklab annotate sample --source rotlk --limit-threads 5000 \
  --random 2 --targeted 2 --out /tmp/opencode/rotlk_smoke.jsonl

# piloto
keklab annotate sample --source rotlk --months 24 --random 20 --targeted 10 \
  --seed 13 --out data/samples/rotlk_pilot.jsonl
```

- `--dataset` sobrescribe `KEKLAB_ROTLK_DATASET`.
- `--limit-threads` corta la pasada para validación.
- `--parquet` sigue disponible para un parquet canónico ya existente.
- Si se pasan `--dataset` y `--parquet` juntos, la CLI rechaza la combinación.

### Tests

La suite pasa de 68 a **80 pruebas**. Las nuevas cubren:

- lectura de `.tar.zst` con uno y varios miembros NDJSON;
- lectura de `.ndjson.zst`;
- omisión de líneas malformadas dentro del tar;
- muestreo aleatorio estratificado por mes;
- muestreo dirigido por término, marco y contexto OP/padres;
- posts vacíos, `--limit-threads`, determinismo por semilla;
- parsing de la CLI con `--dataset` y `--limit-threads`.

## Resultados del dump real

Smoke test real:

```
5000 hilos, 211,894 posts, 3.6 s
4 samples -> /tmp/opencode/rotlk_smoke.jsonl
by reason: {"random": 2, "targeted": 2}
```

El piloto completo de 20 aleatorios + 10 dirigidos se lanzó con salida en:

```
data/samples/rotlk_pilot.jsonl
```

(Resultado y distribución final se registran al cierre de la ejecución.)

## Limitaciones

- Cada muestra nueva requiere una pasada completa; no hay índice aleatorio
  dentro del frame zstd.
- Si se necesitan muchas consultas repetidas, conviene construir una vez un
  parquet canónico en el disco externo (no en el repo) con
  `keklab ingest expand/canonicalize`.
- Los scores de Perspective y las entidades NER son auxiliares automáticos, no
  etiquetas oro.
- La búsqueda dirigida solo cubre los términos sembrados para `rusophobia`,
  `sinophobia` y `accelerationism`; no es un clasificador.
- La ventana de 24 meses depende del último timestamp del dump, no de la fecha
  actual. Si se reemplaza el archivo, la ventana cambia.
- La muestra aleatoria sigue siendo pequeña (20 posts); estima prevalencia con
  mucha incertidumbre.

## Pendientes

- Anotar el piloto con la CLI interactiva.
- Self test-retest del ~20% tras al menos una semana.
- Revisar el codebook y congelar `v1` si el acuerdo es aceptable.
- E0/E2 siguen bloqueados hasta que existan anotaciones humanas.
