# Protocolo de pre-anotación asistida por IA

Este documento fija el contrato del flujo `keklab annotate ai`. La IA propone
etiquetas; **solo una persona puede convertirlas en oro**. Ninguna propuesta se
acepta automáticamente.

## Principio: solo el texto del post

El clasificador de producción recibe únicamente el texto del post objetivo. Por
eso, las tareas de pre-anotación y la revisión humana tampoco usan:

- el OP del hilo;
- los posts citados (`>>id`);
- el asunto del hilo (`subject`);
- el estrato de muestreo (`stratum`) como pista de etiqueta.

Los metadatos pueden conservarse en los archivos para trazabilidad, pero no se
muestran en la revisión ni se incluyen en el prompt. Si un post no se entiende
por sí solo, la etiqueta correcta es `unclear`, no una inferencia desde el
contexto.

## Flujo de archivos

La generación es *file-based*: no hay llamada a una API de LLM desde `keklab`.
El agente lee las tareas, escribe las propuestas y las importa.

```
data/samples/rotlk_pilot_200.jsonl
        │
        ▼
keklab annotate ai task
        │
        ▼
data/annotations/tasks/rotlk_pending_148.jsonl
        │
        ▼  (el agente lee las tareas y escribe propuestas)
data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl
        │
        ▼
keklab annotate ai import
        │
        ▼
keklab annotate ai review   ──►  data/annotations/rotlk_pilot_r1.jsonl (oro)
        │
        ▼
data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl
```

### 1. Construir tareas

```bash
keklab annotate ai task \
  --input data/samples/rotlk_pilot_200.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --out data/annotations/tasks/rotlk_pending_148.jsonl
```

- Excluye los posts que ya tienen oro (`--gold`).
- `--start` es 1-based; `--limit` corta la cola.
- `--include-annotated` no excluye el oro (solo para auditorías).
- Cada tarea tiene un `task_id` determinista.

### 2. Escribir propuestas

El agente debe devolver un JSON por tarea con:

```json
{
  "post_id": "217139506",
  "frame_labels": ["unclear"],
  "toxicity": 0,
  "confidence": 0.9,
  "rationale": "El post es solo una expresión de acuerdo; sin el comentario citado no se puede determinar a qué se refiere.",
  "evidence": ["Couldn’t agree more"]
}
```

Reglas de la propuesta:

- `frame_labels` es multi-label binario; `none` y `unclear` son exclusivos.
- La evidencia debe ser un fragmento **verbatim** del texto del post objetivo.
- `confidence` es una estimación global en `[0, 1]`.
- El `proposal_id` se deriva de `task_id + model + prompt_version`; no se
  inventa a mano.

### 3. Importar y validar

```bash
keklab annotate ai import \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --input data/annotations/proposals/big-pickle.jsonl \
  --out data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl
```

La importación falla si:

- el `task_id` no existe;
- el `proposal_id` no coincide con sus campos;
- cambia `post_id`, `thread_id`, `source`, `content_hash`, `guideline_version`
  o `prompt_version` respecto de la tarea;
- la evidencia no aparece en el texto del post;
- hay propuestas duplicadas en el lote.

Para reemplazar una propuesta existente se usa `--replace`.

### 4. Revisión humana

```bash
keklab annotate ai review \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --proposals data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl \
  --reviewer flynnso
```

La UI muestra el texto del post, la propuesta, la confianza, la racionalidad y
la evidencia. `--blind` oculta racionalidad, evidencia y confianza.

Decisiones:

| Tecla | Decisión | Efecto |
|---|---|---|
| `a` | `accept` | Escribe oro con las etiquetas propuestas. |
| `e` | `edit` | Abre edición; `s` guarda el oro corregido. |
| `r` | `reject` | No escribe oro; la propuesta queda rechazada. |
| `s` | `skip` | Se registra, pero sigue pendiente en la próxima sesión. |
| `b` | `back` | Vuelve a la propuesta anterior. |
| `q` | `quit` | Sale sin decidir la propuesta actual. |

`accept` y `edit` son las únicas decisiones que escriben en el archivo de oro.
`reject` y `skip` no escriben oro. La procedencia de la IA vive **solo** en el
log de revisión; `AnnotationRecord` no cambia de esquema.

### 5. Estadísticas

```bash
keklab annotate ai stats \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --proposals data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl
```

Reporta cobertura, decisiones, Jaccard propuesta-final, acuerdo exacto y MAE de
toxicidad, confianza media y calibración por bucket.

`keklab annotate ai agreement` compara propuestas con oro en los posts que
comparten. En una corrida limpia está vacío porque las tareas excluyen el oro;
sirve para comparaciones diseñadas de IA vs. humano.

## Versiones y reproducibilidad

- `guideline_version`: versión del codebook (`v0.1` en este piloto).
- `prompt_version`: versión del contrato de prompt (`v1`).
- `prompt_sha256`: hash del template. Se imprime en el reporte de
  `keklab annotate ai task`, pero **no se persiste** en el JSONL de tareas ni
  en las propuestas. Hashea solo `PROMPT_TEMPLATE`, no el menú de marcos, el
  menú de toxicidad ni el prompt renderizado.
- `model` y `provider`: se guardan en cada propuesta, pero son autodeclarados
  por el archivo; el flujo file-based no verifica qué modelo generó el texto.
- Los IDs son prefijos SHA-256 deterministas:
  - `task_id = sha256(source, post_id, content_hash, guideline_version, prompt_version)`
  - `proposal_id = sha256(task_id, model, prompt_version)`
  - `review_id = sha256(proposal_id, reviewer)`
- `proposal_id` identifica la tarea, el modelo y la versión de prompt, no el
  contenido de la propuesta. Regenerar con el mismo modelo puede cambiar
  etiquetas, toxicidad, confianza o rationale sin cambiar el ID.
- `ReviewRecord` guarda las etiquetas y la toxicidad propuestas, pero no
  `confidence`, `rationale`, `evidence` ni un hash del contenido propuesto.

## Limitaciones

- **Sin segundo anotador.** El acuerdo es self test-retest (~20 % de la
  muestra), no acuerdo inter-anotador. Esto mide estabilidad, no validez.
- **Oro previo con contexto.** Las 52 anotaciones originales se hicieron con la
  UI humana que mostraba OP y quotes. Bajo el contrato text-only, deben
  auditarse; cualquier etiqueta que dependa del contexto es una fuga y no debe
  usarse para entrenar.
- **Propuestas no son oro.** La calidad de la IA se mide después de la revisión
  humana; no se usa el acuerdo IA-humano como sustituto del juicio humano.
- **Trazabilidad incompleta del prompt.** El hash del template no se guarda en
  las tareas y solo cubre el texto del template. La versión `v1` se mantuvo
  tras el cambio text-only, así que por sí sola no distingue ambos prompts.
- **Trazabilidad incompleta de la propuesta.** El ID no incluye el contenido y
  el review no conserva confianza, rationale ni evidencia. Para auditorías
  estrictas hay que conservar los archivos de propuestas y comparar sus campos.
- **Prevalencia.** Las muestras dirigidas enriquecen marcos raros; no estiman
  prevalencia. Solo la parte aleatoria sirve para eso.

## Estado del piloto

- 200 posts en la muestra, los 200 con decisión humana registrada: 52
  anotaciones originales + 148 revisiones del flujo AI.
- 148 revisiones: 124 `accept`, 24 `edit`, 0 `skip`, 0 `reject`.
- 200 registros de oro.
- 0 propuestas pendientes de revisión.
- Las propuestas se generaron con `provider=opencode`, `model=big-pickle`.
- `229326221` fue aceptado con `ethnonationalism` antes de la corrección
  text-only; su propuesta actual es `unclear`/tox 0 y requiere revisión.
- `176409794` sigue en oro como `misogyny`/tox 1, pero su texto objetivo no
  contiene misoginia; requiere revisión.
- La auditoría de reproducibilidad y trazabilidad está documentada en
  `Journal/Journal PLN. 15. 09-11-26.md`.
- El corpus completo deja al modelo fino de 18 marcos infradeterminado; solo
  `ethnoracial_prejudice` y `no_frame` cumplen el soporte grueso. Ver la misma
  entrada para el chequeo y la tabla de posts necesarios.
