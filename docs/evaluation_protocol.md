# Protocolo de evaluación (pre-registro)

Fecha: 04-11-2026. Estado: pre-registrado antes de la primera anotación del
piloto de 200. Este documento fija las decisiones que no deben cambiarse
después de ver las etiquetas: unidad de análisis, taxonomía de modelado,
partición train/dev/test, métricas y reglas para marcos con poco soporte.

## Unidad y muestra

- Unidad de análisis: **post**.
- Fuente: ROTLK `/pol/`, ventana `2017-11-11T10:15:36Z → 2019-11-01T10:15:36Z`.
- Muestra: `data/samples/rotlk_pilot_200.jsonl`, **200 posts / 200 hilos**.
  - 190 aleatorios: estiman prevalencia y alimentan el modelo.
  - 10 dirigidos: solo entrenamiento/calibración; **nunca** entran en
    estimaciones de prevalencia.
- La muestra aleatoria no se reemplaza después de ver resultados. Si se
  necesitan más positivos, se agregan tandas nuevas y se documenta el cambio.

## Taxonomía

La anotación conserva **16 marcos finos**. El modelado usa **7 cabezas
gruesas**; la correspondencia está en `src/keklab/annotation/taxonomy.py`.

| Cabeza gruesa | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `misogyny`, `transphobia`, `homophobia` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

Reglas:

- Cada marco fino mapea a exactamente una cabeza; un post puede activar varias
  cabezas.
- `none` y `unclear` se colapsan a `no_frame` y siguen siendo excluyentes en la
  anotación fina.
- La evaluación principal es por cabeza gruesa. Los marcos finos se reportan
  de forma descriptiva salvo que superen el umbral de soporte.

## Partición train/dev/test

- Partición **por `thread_id`**, nunca por post, para evitar fuga entre OP y
  respuestas del mismo hilo.
- Proporciones: **60% train / 20% dev / 20% test**.
- Semilla: **13**. Manifiesto pre-registrado:
  `data/splits/rotlk_pilot_200_threads.jsonl` (120/40/40 hilos).
- `dev` se usa para selección de modelo e hiperparámetros. `test` se evalúa una
  sola vez al final; no se usa para elegir nada.
- Las tandas futuras se asignan con la misma regla y semilla documentada, pero
  un hilo ya asignado **no se mueve** de split. Si una cabeza no alcanza el
  mínimo de positivos en `test`, se amplía `test` con hilos nuevos; no se
  transfieren hilos desde `train`.

## Métricas

Por cabeza gruesa (binaria, multi-label):

- Precisión, recall y F1 por cabeza.
- F1 macro y F1 micro.
- Número de positivos reales y predichos en train/dev/test.
- Intervalos de confianza por bootstrap (1,000 remuestreos, semilla 13).

Toxicidad (`0–3`, ordinal):

- Kappa cuadrática ponderada.
- Error absoluto medio.
- Matriz de confusión.
- Como tarea secundaria, versión binaria `0–1` vs `2–3`.

Acuerdo:

- Self test-retest sobre 40 posts (20%), seleccionados con
  `keklab annotate retest --fraction 0.2 --seed 13`.
- La ronda 2 se anota con al menos una semana de separación.
- Se reporta kappa por cabeza gruesa y kappa cuadrática de toxicidad. Para
  marcos finos con <10 positivos, el kappa se reporta como no estimable.
- Limitación explícita: mide consistencia intra-anotador, no acuerdo
  inter-anotador.

## Experimentos

### E0: crudo vs saneado

- Mismo modelo, mismo split, dos representaciones: `text_raw` y `text_clean`.
- Métrica primaria: diferencia de F1 macro por cabeza en `dev`, con bootstrap
  pareado.
- `text_clean` solo se usa si la diferencia es positiva y el intervalo no
  cruza cero en la mayoría de las cabezas; si no, se conserva `text_raw`.

### E2: representación + clásico

- TF-IDF + regresión logística.
- BoW + SVM lineal.
- Embeddings con un clasificador lineal (si el entorno lo permite).
- El vectorizador se ajusta **solo con train**.
- Selección por F1 macro en `dev`; una sola evaluación final en `test`.

### E1/E3

No se ejecutan hasta tener oro. La comparación con Laya/LLM queda fuera de este
pre-registro y se documentará por separado.

## Reglas de soporte

- Un marco fino entra a E0/E2 solo con **≥30 positivos en train** y **≥5 en
  test**. Si no, se reporta solo de forma descriptiva.
- Una cabeza gruesa entra al modelo con **≥30 positivos en train** y **≥5 en
  test**. Si no llega, se agrupa o se reporta descriptivamente.
- Si después de 1,000 posts aleatorios una cabeza sigue con <5 positivos, se
  saca del modelo supervisado y se documenta su prevalencia observada.
- Los 10 posts dirigidos se excluyen de prevalencia y no se usan para estimar
  el rendimiento poblacional.

## Reproducibilidad

- Semillas: muestreo ROTLK `17` (tanda adicional) y `13` (piloto original,
  split y retest). Cada comando debe registrar su semilla.
- Los comandos nuevos de la CLI son:

```bash
keklab annotate merge --input a.jsonl b.jsonl --out merged.jsonl \
  --expect-total 200 --expect-random 190 --expect-targeted 10
keklab annotate audit --input merged.jsonl \
  --start 2017-11-11T10:15:36Z --end 2019-11-01T10:15:36Z
keklab annotate retest --input merged.jsonl --out retest.jsonl \
  --fraction 0.2 --seed 13
keklab annotate split --input merged.jsonl --out splits.jsonl --seed 13
```

- `annotate export` agrega `coarse_labels` y columnas one-hot `coarse_*`
  además de los 16 marcos finos.

## Enmiendas posteriores al pre-registro

### 06-11-2026: `antifeminism` → `misogyny`

Se renombra el marco fino 10 de `antifeminism` a `misogyny` y se amplía su
definición para cubrir hostilidad, desprecio u objetificación hacia las mujeres
como clase, no solo oposición al feminismo. Es una aclaración terminológica y
conceptual: los tres positivos existentes (`176409794`, `226180859`,
`151478852`) fueron revisados y confirmados como misoginia. El alias
`antifeminism → misogyny` se mantiene en el código para leer archivos viejos.
La taxonomía gruesa no cambia: `misogyny` sigue mapeando a
`gender_sexuality_prejudice`. El codebook pasa a `v0.1`.

### 09-11-2026: soporte observado con el piloto completo

Con 200 posts anotados (190 aleatorios + 10 dirigidos), la partición
pre-registrada 120/40/40 y la taxonomía vigente de 16 marcos / 7 cabezas, solo
**2 de 7** cabezas gruesas cumplen el umbral de ≥30 positivos en train y ≥5 en
test:

| Cabeza | `p` random | train+ | test+ | Umbral |
|---|---:|---:|---:|---|
| `no_frame` | 59.5 % | 70 | 22 | ✅ |
| `ethnoracial_prejudice` | 25.8 % | 30 | 12 | ✅ borderline |
| `gender_sexuality_prejudice` | 10.5 % | 13 | 5 | ❌ |
| `violence_acceleration` | 7.9 % | 10 | 5 | ❌ |
| `meta_topic` | 4.7 % | 6 | 2 | ❌ |
| `institutional_distrust` | 3.2 % | 5 | 0 | ❌ |
| `conspiracy` | 2.6 % | 4 | 2 | ❌ |

`ethnoracial_prejudice` llega a 30 positivos en train, pero uno es dirigido; con
solo aleatorios tendría 29. Es la única cabeza sustantiva con soporte y aun así
es borderline.

En el esquema fino, **15 de 16** marcos fallan el umbral. El único que pasa es
`none` (61 train / 22 test), que no es un marco sustantivo. `sinophobia` tiene
0 positivos; `rusophobia`, `transphobia` y `accelerationism` tienen 1–2.

Consecuencia: el piloto no permite entrenar el modelo fino de 16 marcos. Para el
modelo grueso, solo hay soporte para un proof-of-concept binario de
`ethnoracial_prejudice` contra el resto; las otras cabezas se reportan de forma
descriptiva hasta ampliar la muestra. La entrada
`Journal/Journal PLN. 15. 09-11-26.md` incluye la proyección de posts necesarios
por cabeza.

El retiro de `eugenics` y `ableism` no cambia el veredicto: `eugenics_ableism`
tenía 1 positivo en train y 0 en test, así que su cabeza tampoco era modelable.
Los detalles están en la enmienda siguiente.

También se documenta una inconsistencia de la partición: 5 dirigidos quedaron
en `train`, 4 en `dev` y 1 en `test`, aunque el protocolo dice que los dirigidos
son solo para entrenamiento/calibración. Antes de E0/E2 hay que excluirlos de
`dev`/`test` o registrar una enmienda explícita; no se cambia la partición en
silencio.

### 09-11-2026: retiro de `eugenics` y `ableism`

Se retiran los marcos finos `eugenics` (índice 8) y `ableism` (índice 9) y la
cabeza gruesa `eugenics_ableism`. La taxonomía pasa de 18 marcos / 8 cabezas a
**16 marcos / 7 cabezas**. La decisión se toma tras el piloto de 200 y se
registra en `Journal/Journal PLN. 16. 09-11-26.md`.

Motivos:

- `eugenics` tuvo **0 positivos** en los 200 posts; no es estimable ni
  modelable con esta muestra.
- `ableism` tuvo **3 positivos**, todos concentrados en el uso de “retard” como
  insulto genérico. La etiqueta no separaba un encuadre ideológico distinto y
  añadía una decisión de anotación poco confiable.
- La cabeza `eugenics_ableism` quedaba con 1 positivo en train y 0 en test, por
  debajo de cualquier umbral razonable.

Migración de los tres registros afectados:

| Post | Split | Antes | Después |
|---|---|---|---|
| `184178792` | dev | `ableism` | `none` |
| `201863027` | dev | `ableism` | `none` |
| `195351182` | train | `rusophobia`, `homophobia`, `islamophobia`, `ableism`, `violence_glorification` | `rusophobia`, `homophobia`, `islamophobia`, `violence_glorification` |

Los archivos históricos conservan las etiquetas retiradas como procedencia. El
cargador (`normalize_frame_labels`) las elimina y, si un registro queda vacío,
lo colapsa a `none`. La edición interactiva las rechaza. Las versiones suben a
`guideline_version = "v0.2"` y `prompt_version = "v2"`; el hash del prompt ahora
cubre también los menús generados de marcos y toxicidad.

### Trabajo futuro: `national_stereotypes`

Se registra como clase candidata para el próximo estudio, no para este piloto.
Definición propuesta: generalizaciones sobre rasgos, costumbres o carácter de
una nacionalidad (por ejemplo, “las alemanas son…”, “los europeos del este
son…”). Mapeo futuro a `ethnoracial_prejudice`. Agregarla a este piloto
obligaría a re-anotar los posts previos para la clase y rompería la taxonomía
pre-registrada.

## Limitaciones

- 200 posts es un piloto: alcanza para prevalencia descriptiva y, con el
  soporte observado, solo para un proof-of-concept binario de
  `ethnoracial_prejudice`; no para las 7 cabezas gruesas ni para los 16 marcos
  finos.
- Un solo anotador y self test-retest: no hay acuerdo inter-anotador.
- La muestra es histórica (2016–2019); no garantiza generalización a `/pol/`
  reciente.
- Los marcos finos raros no serán modelables con este tamaño; quedan para
  análisis descriptivo o para muestreo dirigido posterior.

### 11-11-2026: enmienda de clasificación plata

Se agrega un segundo régimen de etiquetas para entrenar modelos a escala. La
decisión está pre-registrada en `docs/silver_classification_protocol.md` y
modifica el alcance del protocolo original, no sus métricas.

- Se etiquetan **5.000 posts aleatorios** de ROTLK (semilla 17, ventana
  `2016-06-01 → 2019-11-01`) con `Qwen3-8B-Q4_K_M` como maestro.
- Esas etiquetas son **plata confiada**: no se revisan ni se corrigen
  humanamente.
- El oro de 200 posts deja de ser el conjunto de entrenamiento principal. Se
  conserva solo como **diagnóstico externo** del maestro.
- La tabla principal de resultados mide imitación del maestro, no verdad. La
  comparación contra el oro se reporta en una tabla secundaria y no se usa para
  seleccionar modelos ni hiperparámetros.
- El split 60/20/20 por `thread_id` y la semilla 13 se mantienen. El test se
  congela y se hashea antes de entrenar; los hilos ya asignados no se mueven.
- Los umbrales de soporte y las métricas del protocolo original siguen
  vigentes para la plata. Los marcos con pocos positivos se reportan como
  descriptivos.

Esta enmienda no borra ni reinterpreta el pre-registro del piloto: el piloto de
200 sigue siendo el único conjunto con validación humana y su análisis de
soporte sigue documentado arriba.
