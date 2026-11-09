# Journal PLN — Entrada 15 (09-11-2026)

## Contexto

Esta entrada cierra la revisión humana del corpus de 200 posts y registra la
auditoría de **reproducibilidad y trazabilidad** del flujo de pre-anotación con
IA. No se reabre el codebook, no se cambia el esquema de etiquetas y no se
modifica el oro en esta entrada.

## Corpus de 200 posts

El corpus de 200 posts ya fue revisado por una persona. La composición es:

- 52 anotaciones originales;
- 148 tareas de pre-anotación con IA;
- 200 posts con decisión humana registrada.

Estado de las 148 revisiones:

| Decisión | Cantidad |
|---|---:|
| `accept` | 124 |
| `edit` | 23 |
| `skip` | 1 |
| `reject` | 0 |

Las decisiones `accept` y `edit` escribieron oro: 147 registros nuevos. Sumados
a los 52 originales, el archivo de oro tiene **199 registros**.

El post `166273462` quedó con `skip` y **no tiene oro**. Su propuesta era
`none`/toxicidad 0, pero la revisión humana decidió no cerrarla. No quedan
propuestas pendientes de revisión: el `skip` es una decisión registrada, no una
tarea abierta.

## Estadísticas de la revisión

Salida de `keklab annotate ai stats`:

```text
tasks: 148
proposals: 148
coverage: 1.000 (148/148 tasks)
unresolved: 1
decisions: {"accept": 124, "edit": 23, "reject": 0, "skip": 1}
accept/edit/reject: 0.844 / 0.156 / 0.000
mean Jaccard proposal-final: 0.905
toxicity exact/MAE: 0.952 / 0.048
mean confidence: 0.767
mean confidence by decision: {"accept": 0.780, "edit": 0.689}
by model: {"big-pickle": 148}
calibration:
  0.00-0.50: proposals=0 resolved=0 accepted=0 rate=0.000
  0.50-0.70: proposals=27 resolved=27 accepted=19 rate=0.704
  0.70-0.85: proposals=82 resolved=82 accepted=68 rate=0.829
  0.85-1.00: proposals=39 resolved=38 accepted=37 rate=0.974
```

La confianza estuvo mejor calibrada en el tramo alto: las propuestas con
confianza `0.85–1.00` se aceptaron sin edición el 97.4 % de las veces. Las del
tramo `0.50–0.70` se aceptaron el 70.4 %, consistente con que la edición humana
se concentrara ahí.

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
- 199 registros de oro;
- 1 `skip` sin oro (`166273462`);
- 0 propuestas pendientes de revisión.

También era incorrecta la frase de que el `prompt_sha256` queda en el
manifiesto de la tarea: hoy solo se imprime en el reporte de la corrida. La
documentación se corrigió en esta entrada.

## Pendientes de anotación

Tres casos siguen abiertos y no se tocaron en esta entrada:

| Post | Estado | Problema |
|---|---|---|
| `229326221` | Oro y review: `ethnonationalism`/tox 1 | La propuesta text-only actual es `unclear`/tox 0. El review se hizo antes de la corrección. |
| `176409794` | Oro: `misogyny`/tox 1 | El texto objetivo (“Is there a Midnight Meat Train or not? INTK”) no contiene misoginia; la etiqueta vino del contexto. |
| `166273462` | `skip`, sin oro | La propuesta era `none`/tox 0; falta decidir si se deja como exclusión documentada o se anota. |

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
- 0 tareas con `subject` o `context`.

## Estado de git

- Sin cambios de código en esta entrada.
- Esta entrada y la corrección de estado de
  `docs/ai_annotation_protocol.md` van en un commit de documentación.
- Sin push a `origin`.
- `data/annotations/` y `Journal/Problems.md` siguen untracked.

## Siguiente paso

1. Revisitar `229326221` y `176409794` con el flujo `--revisit`.
2. Decidir si `166273462` queda como exclusión documentada o recibe oro.
3. Opcional, para una próxima iteración: persistir un manifiesto con
   `prompt_sha256`, agregar un hash de contenido de la propuesta al review y
   hashear el prompt renderizado completo.
4. Mantener el oro actual sin cambios hasta que exista una decisión humana
   registrada para los tres casos abiertos.
