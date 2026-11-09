# Journal PLN — Entrada 15 (09-11-2026)

> **Nota posterior (09-11-2026).** El análisis de esta entrada se hizo con la
> taxonomía de 18 marcos / 8 cabezas. La entrada
> `Journal/Journal PLN. 16. 09-11-26.md` retira `eugenics` y `ableism`, deja el
> esquema en 16 marcos / 7 cabezas y actualiza el soporte. Las cifras de esta
> entrada se conservan como registro histórico; el veredicto de
> infradeterminación no cambia.

## Contexto

Esta entrada cierra la revisión humana del corpus de 200 posts, registra la
auditoría de **reproducibilidad y trazabilidad** del flujo de pre-anotación con
IA y revisa la **infradeterminación del modelo de clasificación**. No se reabre
el codebook, no se cambia el esquema de etiquetas y no se modifica el oro en
esta entrada.

## Corpus de 200 posts

El corpus de 200 posts está anotado por una persona. La composición es:

- 52 anotaciones originales;
- 148 tareas de pre-anotación con IA;
- 200 posts con decisión humana registrada.

Estado de las 148 revisiones:

| Decisión | Cantidad |
|---|---:|
| `accept` | 124 |
| `edit` | 24 |
| `skip` | 0 |
| `reject` | 0 |

Las decisiones `accept` y `edit` escribieron oro: 148 registros nuevos. Sumados
a los 52 originales, el archivo de oro tiene **200 registros**.

El último post pendiente, `166273462`, se revisó y quedó como `racism`/toxicidad
1 con decisión `edit`. La propuesta era `none`/toxicidad 0; la persona corrigió
la etiqueta. No quedan propuestas pendientes ni posts sin oro.

## Estadísticas de la revisión

Salida de `keklab annotate ai stats`:

```text
tasks: 148
proposals: 148
coverage: 1.000 (148/148 tasks)
unresolved: 0
decisions: {"accept": 124, "edit": 24, "reject": 0, "skip": 0}
accept/edit/reject: 0.838 / 0.162 / 0.000
mean Jaccard proposal-final: 0.898
toxicity exact/MAE: 0.946 / 0.054
mean confidence: 0.767
mean confidence by decision: {"accept": 0.780, "edit": 0.698}
by model: {"big-pickle": 148}
calibration:
  0.00-0.50: proposals=0 resolved=0 accepted=0 rate=0.000
  0.50-0.70: proposals=27 resolved=27 accepted=19 rate=0.704
  0.70-0.85: proposals=82 resolved=82 accepted=68 rate=0.829
  0.85-1.00: proposals=39 resolved=39 accepted=37 rate=0.949
```

La confianza estuvo mejor calibrada en el tramo alto: las propuestas con
confianza `0.85–1.00` se aceptaron sin edición el 94.9 % de las veces. Las del
tramo `0.50–0.70` se aceptaron el 70.4 %, consistente con que la edición humana
se concentrara ahí.

## Infradeterminación del modelo de clasificación

La anotación es una decisión humana y no está infradeterminada por el tamaño
muestral; lo que puede quedar infradeterminado es el **modelo supervisado** que
se entrene sobre esas etiquetas. El chequeo usa las reglas de soporte
pre-registradas en `docs/evaluation_protocol.md`: una cabeza gruesa o un marco
fino entra al modelo con **≥30 positivos en train** y **≥5 en test**. La
partición es 120 train / 40 dev / 40 test por hilo.

### Espacio de etiquetas

- 18 marcos finos, 16 no exclusivos más `none` y `unclear`: `2^16 + 2 =
  65,538` conjuntos posibles. El corpus observa **39** (0.06 %).
- 8 cabezas gruesas binarias: `2^8 = 256` conjuntos posibles. El corpus observa
  **19** (7.4 %).
- 104 posts son `none`; 12 son `unclear`. Solo 29 posts tienen más de un marco
  fino; el promedio es 1.235 marcos por post.
- Toxicidad: 98 en `0`, 49 en `1`, 41 en `2`, 12 en `3`.

La combinación de un espacio de etiquetas enorme y un corpus pequeño es la
definición práctica de un problema infradeterminado: muchas hipótesis predicen
igual de bien los 200 posts observados, pero difieren fuera de la muestra.

### Soporte por cabeza gruesa

`p` se estima solo con los 190 posts aleatorios; `train+` y `test+` incluyen los
10 dirigidos, porque el protocolo permite usarlos en entrenamiento/calibración.
El intervalo es Wilson 95 %.

| Cabeza | `p` random (IC 95 %) | train+ | test+ | ≥30 train y ≥5 test |
|---|---:|---:|---:|---|
| `no_frame` | 58.4 % [51.3, 65.2] | 70 | 22 | ✅ |
| `ethnoracial_prejudice` | 25.8 % [20.1, 32.4] | 30 | 12 | ✅ borderline |
| `gender_sexuality_prejudice` | 10.5 % [6.9, 15.7] | 13 | 5 | ❌ |
| `violence_acceleration` | 7.9 % [4.8, 12.6] | 10 | 5 | ❌ |
| `meta_topic` | 4.7 % [2.5, 8.8] | 6 | 2 | ❌ |
| `institutional_distrust` | 3.2 % [1.5, 6.7] | 5 | 0 | ❌ |
| `conspiracy` | 2.6 % [1.1, 6.0] | 4 | 2 | ❌ |
| `eugenics_ableism` | 1.6 % [0.5, 4.5] | 1 | 0 | ❌ |

Solo **2 de 8** cabezas cumplen el umbral. `ethnoracial_prejudice` llega a 30
positivos en train, pero uno de ellos es dirigido: con solo aleatorios tendría
29. Es la única cabeza sustantiva con soporte suficiente, y aun así es
borderline. `no_frame` es la clase mayoritaria, no una cabeza difícil de
aprender.

### Soporte por marco fino

| Marco | train+ | test+ | ≥30 train y ≥5 test |
|---|---:|---:|---|
| `none` | 61 | 22 | ✅ |
| `racism` | 14 | 5 | ❌ |
| `ethnonationalism` | 10 | 4 | ❌ |
| `antisemitism` | 9 | 8 | ❌ |
| `violence_glorification` | 9 | 4 | ❌ |
| `unclear` | 9 | 0 | ❌ |
| `homophobia` | 6 | 3 | ❌ |
| `meta_topic` | 6 | 2 | ❌ |
| `misogyny` | 5 | 2 | ❌ |
| `institutional_distrust` | 5 | 0 | ❌ |
| `conspiracy` | 4 | 2 | ❌ |
| `islamophobia` | 3 | 3 | ❌ |
| `transphobia` | 2 | 0 | ❌ |
| `rusophobia` | 1 | 0 | ❌ |
| `ableism` | 1 | 0 | ❌ |
| `accelerationism` | 1 | 1 | ❌ |
| `sinophobia` | 0 | 0 | ❌ no estimable |
| `eugenics` | 0 | 0 | ❌ no estimable |

**17 de 18 marcos finos fallan.** El único que pasa es `none`, que no es un
marco sustantivo. `sinophobia` y `eugenics` no tienen ningún positivo;
`rusophobia`, `transphobia`, `ableism` y `accelerationism` tienen 1–2. Un
modelo de 18 cabezas finas sobre 120 ejemplos de train es claramente
infradeterminado.

### Cuántos posts harían falta

Proyección aproximada para llegar a 30 positivos en train, usando la prevalencia
aleatoria observada y la proporción 60/20/20. Es `ceil(30 / (0.6 * p))`; no es
un tamaño garantizado porque los intervalos de `p` son amplios.

| Cabeza | `p` | n total necesario | posts adicionales sobre 200 |
|---|---:|---:|---:|
| `no_frame` | 58.4 % | 86 | 0 |
| `ethnoracial_prejudice` | 25.8 % | 194 | 0 |
| `gender_sexuality_prejudice` | 10.5 % | 476 | +276 |
| `violence_acceleration` | 7.9 % | 634 | +434 |
| `meta_topic` | 4.7 % | 1,056 | +856 |
| `institutional_distrust` | 3.2 % | 1,584 | +1,384 |
| `conspiracy` | 2.6 % | 1,901 | +1,701 |
| `eugenics_ableism` | 1.6 % | 3,167 | +2,967 |

Para el esquema fino, los requerimientos son mayores: `racism` necesitaría
~453 posts, `antisemitism` ~500, `ethnonationalism` ~634,
`violence_glorification` ~679, `misogyny` ~951, `homophobia` ~1,056,
`islamophobia` e `institutional_distrust` ~1,584, `ableism` ~3,167,
`rusophobia` y `transphobia` ~4,750, y `accelerationism` ~9,500. `sinophobia` y
`eugenics` no se pueden proyectar con cero positivos.

### Veredicto

- **Modelo fino de 18 marcos: infradeterminado.** No debe entrenarse con este
  piloto. Los marcos finos se reportan de forma descriptiva.
- **Modelo grueso de 8 cabezas: parcialmente infradeterminado.** Solo 2 de 8
  cabezas cumplen el soporte; una es la clase mayoritaria y la otra es
  borderline. Un modelo de 8 cabezas completo no está identificado con 200
  posts.
- **Lo que sí permite el piloto:** estimar prevalencia descriptiva de las
  cabezas gruesas, entrenar un proof-of-concept binario de
  `ethnoracial_prejudice` contra el resto y comparar representaciones
  (`text_raw` vs `text_clean`) sin extrapolar a las demás cabezas.
- **Lo que no permite:** afirmar que se aprendieron las 8 cabezas, reportar F1
  por cabeza como si todas tuvieran evaluación válida, o entrenar los 18 marcos
  finos.

### Problema de partición con los dirigidos

El protocolo dice que los 10 posts dirigidos son solo para
entrenamiento/calibración. La partición pre-registrada los distribuyó así:

- 5 en `train`;
- 4 en `dev`;
- 1 en `test` (`226274308`, con `conspiracy`, `ethnonationalism`, `racism` y
  `antisemitism`).

Eso viola el “solo entrenamiento/calibración” y contamina `dev`/`test` con
positivos enriquecidos. En particular, el test de `ethnoracial_prejudice` pasa
de 12 a 11 positivos si se excluye el dirigido. Antes de E0/E2 hay que decidir
si se excluyen los dirigidos de `dev`/`test` o si se documenta una enmienda al
pre-registro; no se debe cambiar la partición en silencio.

## Supuestos que sí se cumplieron

La verificación estructural sobre los archivos actuales dio:

| Supuesto | Resultado |
|---|---|
| IDs deterministas | 148/148 `task_id`, 148/148 `proposal_id` y 148/148 `review_id` recalculan exactamente |
| Sin duplicados ni huérfanos | 148 tareas, 148 propuestas y 148 reviews; 0 duplicados, 0 propuestas sin tarea |
| Modelo y proveedor uniformes | 148/148 propuestas con `provider=opencode`, `model=big-pickle` |
| Versiones coherentes | 148/148 en `guideline_version=v0.1`, `prompt_version=v1` |
| Evidencia verbatim | 148/148 propuestas tienen evidencia localizada en el texto del post |
| Propuesta ↔ tarea | 0 mismatches en `post_id`, `thread_id`, `source`, `content_hash`, versión de codebook y versión de prompt |
| Text-only | 0 tareas con `subject` o `context`; el prompt solo renderiza `post_id`, `text_raw` y `text_clean` |

El hash del template actual es:

```text
c9b72fc4d4339047d1953841818ae04726a19cf7505f324cc88e6440a0792d7d
```

Coincide con el que se imprimió al regenerar las tareas text-only. El problema
es que ese valor no quedó guardado en los archivos de tareas.

## Huecos de reproducibilidad y trazabilidad

### 1. `prompt_sha256` no se persiste

`docs/ai_annotation_protocol.md` decía que el hash quedaba “registrado en el
manifiesto de la tarea”, pero el JSONL de tareas no tiene ese campo. El hash
solo se imprime en el reporte de `keklab annotate ai task`.

Consecuencia: la correspondencia entre un archivo de tareas y el template que
lo generó solo se puede reconstruir desde el log de la corrida, no desde el
artefacto.

### 2. El hash no cubre el prompt completo

`prompt_sha256()` hashea solo `PROMPT_TEMPLATE`. No incluye:

- el menú de marcos (`format_frame_menu()`);
- el menú de toxicidad (`_toxicity_menu()`);
- el JSON de la tarea;
- la lógica de `render_prompt()`.

Si cambia una descripción de marco o la forma de renderizar, el hash no cambia.

### 3. `prompt_version` no distingue el cambio text-only

Se mantuvo `prompt_version=v1` a propósito para no romper los IDs. Eso significa
que dos prompts semánticamente distintos comparten versión. Si no se regeneran
las tareas, una propuesta vieja sigue validando como si fuera del prompt nuevo.
El hash era la única defensa, y no quedó persistido.

### 4. `proposal_id` no identifica el contenido

`proposal_id` se calcula solo con `task_id + model + prompt_version`. No incluye
etiquetas, toxicidad, confianza, rationale ni evidencia. El caso concreto:

```text
229326221
proposal_id: prop_091b22b5e8f9d8c1
review propuesta: ethnonationalism / tox 1
propuesta actual: unclear / tox 0
mismo proposal_id: sí
```

Una regeneración con el mismo modelo y el mismo prompt puede cambiar por
completo la propuesta y conservar el mismo ID. `--replace` la sobrescribe sin
que el identificador lo delate.

### 5. El modelo y el proveedor son autodeclarados

El flujo es file-based: el archivo dice `provider=opencode`, `model=big-pickle`,
pero nada verifica criptográficamente qué modelo escribió esas líneas. Tampoco
se guardan `temperature`, `seed`, configuración de muestreo ni un hash del
output. Los archivos actuales no permiten demostrar que dos corridas del mismo
modelo produzcan la misma propuesta.

### 6. La revisión no congela toda la propuesta

`ReviewRecord` guarda `proposed_frame_labels` y `proposed_toxicity`, pero no
`confidence`, `rationale`, `evidence` ni un hash de la propuesta. Si alguien
edita el archivo de propuestas después de la revisión, se detecta un cambio de
etiquetas, pero no un cambio de rationale o confianza.

### 7. Residuo text-only en las tareas

95 tareas todavía guardan `quotes` (IDs de posts citados) y las 148 guardan
`stratum` con `reason`/`month`. No son texto de contexto y ni el prompt ni la
UI de revisión los usan, pero si “text-only” se interpreta de forma estricta
habría que quitarlos también de las tareas.

## Documentación desactualizada

`docs/ai_annotation_protocol.md` decía que había 62 registros de oro y 138
propuestas pendientes. El estado real es:

- 200 posts con decisión humana;
- 200 registros de oro;
- 0 `skip` sin oro;
- 0 propuestas pendientes de revisión.

También era incorrecta la frase de que el `prompt_sha256` queda en el
manifiesto de la tarea: hoy solo se imprime en el reporte de la corrida. La
documentación se corrigió en esta entrada.

## Pendientes de anotación

Dos casos siguen abiertos:

| Post | Estado | Problema |
|---|---|---|
| `229326221` | Oro y review: `ethnonationalism`/tox 1 | La propuesta text-only actual es `unclear`/tox 0. El review se hizo antes de la corrección. |
| `176409794` | Oro: `misogyny`/tox 1 | El texto objetivo (“Is there a Midnight Meat Train or not? INTK”) no contiene misoginia; la etiqueta vino del contexto. |

La auditoría del oro original encontró **dos fugas de contexto claras**:
`176409794` y `229326221`. No se modificaron directamente porque requieren una
decisión humana y una revisión registrada.

También quedaron marcados dos posibles problemas de calidad que **no** son
fugas de contexto:

- `169094966` (“You probably ask retarded questions.”) figura como `none`/tox 1;
  “retarded” como insulto podría justificar `ableism`.
- `195052309` (FISA, Mueller y Dan Bongino) figura como `none`/tox 1; el texto
  podría sostener `conspiracy` o `institutional_distrust`.

## Verificación ejecutada

No hubo cambios de código en esta entrada. La verificación fue de solo lectura
sobre los archivos de tareas, propuestas, reviews y oro:

- 148/148 IDs recalculados sin diferencias;
- 0 duplicados, 0 huérfanos, 0 propuestas sin tarea;
- 148/148 propuestas con evidencia verbatim;
- 148/148 propuestas con el mismo `model`/`provider`;
- 0 tareas con `subject` o `context`;
- 200/200 posts con oro, 190 aleatorios + 10 dirigidos, split 120/40/40;
- 39 conjuntos de etiquetas finas observados de 65,538 posibles;
- 19 conjuntos de cabezas gruesas observados de 256 posibles;
- solo 2/8 cabezas gruesas y 1/18 marcos finos cumplen el soporte;
- los 10 dirigidos quedaron 5 en train, 4 en dev y 1 en test.

## Estado de git

- Sin cambios de código en esta entrada.
- Esta entrada y las correcciones de estado de
  `docs/ai_annotation_protocol.md`, `docs/evaluation_protocol.md` y
  `docs/pipeline_draft.md` van en un commit de documentación.
- Sin push a `origin`.
- `data/annotations/` y `Journal/Problems.md` siguen untracked.

## Siguiente paso

1. Revisitar `229326221` y `176409794` con el flujo `--revisit`.
2. No entrenar el modelo fino de 18 marcos con este piloto; reportarlo de forma
   descriptiva.
3. Para el esquema grueso, decidir entre:
   - un proof-of-concept binario de `ethnoracial_prejudice` contra el resto;
   - reportar las 8 cabezas solo como descriptivas hasta ampliar la muestra;
   - ampliar el corpus según la tabla de soporte (empezando por ~500 posts para
     `gender_sexuality_prejudice` y `violence_acceleration`).
4. Resolver la partición de los 10 dirigidos: excluirlos de `dev`/`test` o
   documentar una enmienda al pre-registro antes de E0/E2.
5. Opcional, para una próxima iteración: persistir un manifiesto con
   `prompt_sha256`, agregar un hash de contenido de la propuesta al review y
   hashear el prompt renderizado completo.
6. Mantener el oro actual sin cambios hasta que exista una decisión humana
   registrada para los dos casos abiertos.
