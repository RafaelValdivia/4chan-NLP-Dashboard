# Journal PLN — Entrada 16 (09-11-2026)

## Contexto

Esta entrada registra una decisión de taxonomía tomada después de cerrar el
piloto de 200 posts y de revisar la infradeterminación del modelo (entrada 15):
**retirar los marcos `eugenics` y `ableism` y la cabeza gruesa
`eugenics_ableism`**. No se reabre la anotación humana ni se cambia ninguna
etiqueta sustantiva: los tres registros afectados se migran de forma explícita.

La decisión no cambia el veredicto de infradeterminación. El piloto sigue
alcanzando solo para un proof-of-concept binario de `ethnoracial_prejudice`;
lo que cambia es el tamaño y la forma del espacio de etiquetas.

## Decisión

- Se retiran de `FRAME_LABELS` los marcos finos `eugenics` (índice 8) y
  `ableism` (índice 9).
- Se retira `eugenics_ableism` de `COARSE_HEADS`.
- La taxonomía vigente queda en **16 marcos finos** y **7 cabezas gruesas**.
- `guideline_version` sube a **`v0.2`** y `prompt_version` a **`v2`**.

Los nombres retirados se conservan en `RETIRED_FRAME_LABELS` como vocabulario
histórico. No son etiquetas válidas para anotar, pero el cargador las reconoce
para poder leer archivos viejos.

## Justificación

La decisión se apoya en tres hechos observados en el piloto:

1. **`eugenics` tuvo 0 positivos en 200 posts.** No es estimable, no tiene
   varianza y no se puede proyectar con la muestra actual.
2. **`ableism` tuvo 3 positivos**, todos concentrados en el uso de “retard”
   como insulto genérico. La etiqueta no separaba un encuadre ideológico
   distinto de otros marcos y añadía una decisión de anotación poco confiable.
3. **La cabeza `eugenics_ableism` quedaba con 1 positivo en train y 0 en
   test**, muy por debajo de cualquier umbral razonable.

Mantener dos marcos y una cabeza sin soporte aumentaba el espacio de hipótesis
sin aportar señal. Retirarlos simplifica el codebook y hace que el resto del
análisis de soporte sea más honesto: no hay una cabeza “fantasma” que parezca
modelable solo por existir en el esquema.

## Nueva taxonomía

16 marcos finos:

```text
conspiracy
ethnonationalism
racism
antisemitism
islamophobia
rusophobia
sinophobia
misogyny
transphobia
homophobia
institutional_distrust
violence_glorification
accelerationism
meta_topic
none
unclear
```

7 cabezas gruesas:

| Cabeza | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `misogyny`, `transphobia`, `homophobia` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

`none` y `unclear` siguen siendo exclusivos con todos los demás marcos y entre
sí. `transphobia` y `homophobia` siguen siendo ejes independientes de
`misogyny`. Las etiquetas específicas de prejuicio siguen reemplazando a
`ethnonationalism`/`racism` cuando cubren el mismo contenido.

## Migración de los tres registros afectados

| Post | Split | Antes | Después |
|---|---|---|---|
| `184178792` | dev | `ableism` | `none` |
| `201863027` | dev | `ableism` | `none` |
| `195351182` | train | `rusophobia`, `homophobia`, `islamophobia`, `ableism`, `violence_glorification` | `rusophobia`, `homophobia`, `islamophobia`, `violence_glorification` |

Los dos posts que solo tenían `ableism` quedan como `none` porque, al quitar la
etiqueta retirada, no queda ningún marco válido. El tercero conserva sus otros
cuatro marcos. La toxicidad no cambia en ningún caso.

Los archivos crudos (`rotlk_pilot_r1.jsonl`, propuestas y reviews) **no se
reescriben**: conservan `ableism` como procedencia histórica. La normalización
ocurre al cargar. Esto mantiene la trazabilidad y evita una reescritura masiva
de artefactos ya auditados.

## Compatibilidad y contrato de código

- `normalize_frame_labels()` acepta etiquetas retiradas, las descarta y
  devuelve el resto en orden. Si el resultado queda vacío, devuelve `["none"]`.
- `apply_frame_toggle()` y el menú interactivo solo aceptan `FRAME_LABELS`; por
  lo tanto, `eugenics` y `ableism` **no se pueden seleccionar** en la CLI.
- El cargador de anotaciones aplica la misma normalización, así que ningún
  registro cargado contiene etiquetas retiradas.
- Los IDs deterministas no cambian para los registros existentes: la migración
  es de etiquetas, no de `post_id`, `task_id` ni `proposal_id`.
- El conteo de positivos cambia solo en los tres posts migrados.

## Versiones y hash del prompt

- `GUIDELINE_VERSION = "v0.2"`.
- `PROMPT_VERSION = "v2"`.
- `prompt_sha256()` ahora hashea `PROMPT_TEMPLATE` **más** el menú generado de
  marcos (`format_frame_menu()`) y el menú de toxicidad (`_toxicity_menu()`).

El hash vigente es:

```text
30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769
```

El cambio corrige un hueco de la entrada 15: en `v1` el hash solo cubría el
template y no detectaba cambios en los menús. El hash sigue sin persistirse en
el JSONL de tareas; esa limitación no se resuelve en esta entrada.

## Soporte observado tras el retiro

La partición no cambia: 120 train / 40 dev / 40 test por hilo, semilla 13. `p`
se estima solo con los 190 posts aleatorios; `train+` y `test+` incluyen los 10
dirigidos, porque el protocolo los permite en entrenamiento/calibración.

### Cabezas gruesas

| Cabeza | `p` random | train+ | test+ | ≥30 train y ≥5 test |
|---|---:|---:|---:|---|
| `no_frame` | 59.5 % | 70 | 22 | ✅ |
| `ethnoracial_prejudice` | 25.8 % | 30 | 12 | ✅ borderline |
| `gender_sexuality_prejudice` | 10.5 % | 13 | 5 | ❌ |
| `violence_acceleration` | 7.9 % | 10 | 5 | ❌ |
| `meta_topic` | 4.7 % | 6 | 2 | ❌ |
| `institutional_distrust` | 3.2 % | 5 | 0 | ❌ |
| `conspiracy` | 2.6 % | 4 | 2 | ❌ |

Solo **2 de 7** cabezas cumplen el umbral, y una es la clase mayoritaria. El
retiro no cambia el veredicto: `eugenics_ableism` tampoco lo cumplía.

`ethnoracial_prejudice` sigue en 30 positivos de train solo porque uno es
dirigido; con aleatorios puros tendría 29.

### Marcos finos

| Marco | `p` random | train+ | test+ | ≥30 train y ≥5 test |
|---|---:|---:|---:|---|
| `none` | 53.2 % | 61 | 22 | ✅ |
| `racism` | 11.1 % | 14 | 5 | ❌ |
| `ethnonationalism` | 7.9 % | 10 | 4 | ❌ |
| `antisemitism` | 10.0 % | 9 | 8 | ❌ |
| `violence_glorification` | 7.4 % | 9 | 4 | ❌ |
| `unclear` | 6.3 % | 9 | 0 | ❌ |
| `homophobia` | 4.7 % | 6 | 3 | ❌ |
| `meta_topic` | 4.7 % | 6 | 2 | ❌ |
| `misogyny` | 5.3 % | 5 | 2 | ❌ |
| `institutional_distrust` | 3.2 % | 5 | 0 | ❌ |
| `conspiracy` | 2.6 % | 4 | 2 | ❌ |
| `islamophobia` | 3.2 % | 3 | 3 | ❌ |
| `transphobia` | 1.1 % | 2 | 0 | ❌ |
| `rusophobia` | 1.1 % | 1 | 0 | ❌ |
| `accelerationism` | 0.5 % | 1 | 1 | ❌ |
| `sinophobia` | 0.0 % | 0 | 0 | ❌ no estimable |

**15 de 16 marcos finos fallan.** El único que pasa es `none`, que no es un
marco sustantivo. `sinophobia` no tiene positivos; `rusophobia`, `transphobia`
y `accelerationism` tienen 1–2.

## Espacio de etiquetas

- 16 marcos finos: 14 no exclusivos más `none` y `unclear`; el espacio es
  `2^14 + 2 = 16,386` conjuntos.
- 7 cabezas gruesas binarias: `2^7 = 128` conjuntos.
- El corpus observa **38** conjuntos finos únicos y **17** conjuntos gruesos
  únicos.
- 106 posts son `none`; 12 son `unclear`. 29 posts tienen más de un marco fino;
  el promedio es 1.23 marcos por post.
- Toxicidad: 98 en `0`, 49 en `1`, 41 en `2`, 12 en `3`.

El espacio sigue siendo grande para 200 posts, pero ya no incluye dos marcos
sin señal. La conclusión de la entrada 15 se mantiene: el modelo fino está
infradeterminado y el grueso solo permite un proof-of-concept binario.

## Verificación

- Suite completa: **136 passed** (`~/PyVenvs/NNnPLN/bin/python -m pytest -q`).
- Carga de los 200 registros de oro: 200 posts, 106 `none`, 12 `unclear`,
  38 conjuntos finos únicos, 17 conjuntos gruesos únicos.
- Tras la carga, **0 etiquetas retiradas** en el oro; los archivos crudos sí las
  conservan y el cargador las elimina.
- Los tres posts migrados cargan con las etiquetas de la tabla anterior.
- `keklab annotate stats` y `keklab annotate ai stats` siguen funcionando con
  los archivos existentes.
- Los IDs deterministas de tareas, propuestas y reviews no cambian.
- El menú interactivo muestra `16. unclear`; `eugenics` y `ableism` ya no
  aparecen.
- La validación de revisiones sigue aceptando los archivos históricos: las
  propuestas con `ableism` se normalizan a las etiquetas finales ya migradas.

## Pendientes que no cambia esta entrada

- La partición de los 10 dirigidos sigue violando el “solo
  entrenamiento/calibración”: 5 en train, 4 en dev y 1 en test. Hay que
  excluirlos de `dev`/`test` o registrar una enmienda explícita antes de E0/E2.
- Siguen abiertos los dos casos de posible fuga de contexto: `229326221`
  (`ethnonationalism`/1 en oro vs. propuesta text-only `unclear`/0) y
  `176409794` (`misogyny`/1 aunque el texto objetivo no contiene misoginia).
- El hash del prompt sigue sin persistirse en el JSONL de tareas.
- El modelo y el proveedor siguen siendo autodeclarados por el archivo.

## Cierre

El codebook queda en `v0.2`: 16 marcos finos, 7 cabezas gruesas y ninguna
etiqueta sin señal. La migración es explícita, el cargador es compatible hacia
atrás y la suite completa pasa. El siguiente paso sigue siendo ampliar la
muestra o quedarse con el proof-of-concept binario de
`ethnoracial_prejudice`; retirar `eugenics`/`ableism` no habilita ninguna cabeza
nueva.
