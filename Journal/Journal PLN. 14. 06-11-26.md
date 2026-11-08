# Journal PLN — Entrada 14 (06-11-2026)

## Contexto

El usuario detectó una fuga grave en la pre-anotación con IA: las propuestas se
estaban generando con el OP del hilo y los posts citados, pero el clasificador
de producción solo recibirá el texto del post objetivo. Una etiqueta que
dependa del contexto no es aprendible en producción y contamina el oro.

Esta entrada documenta la corrección **text-only**, la regeneración de tareas y
propuestas, y la auditoría inicial del oro previo.

## Regla text-only

La anotación y la pre-anotación usan **solo el texto del post objetivo**. No se
usan:

- el OP del hilo;
- los posts citados (`>>id`);
- el asunto del hilo (`subject`);
- el estrato de muestreo (`stratum`) como pista de etiqueta.

Los metadatos se conservan para trazabilidad, pero no se muestran en la
revisión ni se envían al agente. Si el post no se entiende por sí solo, la
etiqueta correcta es `unclear`, no una inferencia desde el contexto.

El cambio se aplicó en tres capas:

| Archivo | Cambio |
|---|---|
| `src/keklab/annotation/proposal.py` | `TaskRecord.from_sample` descarta `subject` y deja `context` vacío. |
| `src/keklab/annotation/prompts.py` | El prompt solo incluye `post_id`, `text_raw` y `text_clean`; las instrucciones prohíben usar contexto. |
| `src/keklab/annotation/review.py` | La UI de revisión ya no muestra OP, quotes, asunto ni estrato. |

`prompt_version` se mantiene en `v1` para no romper los IDs de tareas,
propuestas y revisiones existentes. El contrato cambió, pero el identificador
de versión se conserva por estabilidad; la enmienda queda documentada en
`docs/annotation_guidelines.md` y en `docs/ai_annotation_protocol.md`.

## Regeneración de tareas y propuestas

Se regeneraron las 148 tareas con el código text-only. El archivo conserva las
148 tareas para preservar la procedencia de las 10 ya revisadas; las tareas
pendientes son 138.

Verificación:

```text
tasks 148
proposals 148
reviews 10
pending 138
orphans 0
context non-empty 0
subject non-empty 0
```

Las propuestas se reimportaron con `--replace`. Solo una propuesta ya revisada
cambió respecto de su revisión: `229326221` pasó de `ethnonationalism`/tox 1 a
`unclear`/tox 0. Las otras nueve siguen coincidiendo con la decisión humana.

## Correcciones de propuestas

La auditoría text-only corrigió estos casos:

| Post | Antes | Después | Motivo |
|---|---|---|---|
| `217139506` | `ableism`, `eugenics` | `unclear` | Solo dice “Couldn’t agree more”; el referente estaba en el quote. |
| `211396451` | `racism`, `violence_glorification`, `islamophobia`, `ableism` | `violence_glorification` | La violencia es explícita; el grupo no se identifica en el texto. |
| `227445715` | `antisemitism` | `none` | Reacción breve sin referente ni contenido antisemita. |
| `211870248` | `misogyny` | `none` | “MAN UP!” no identifica a una mujer ni articula hostilidad hacia las mujeres como clase. |
| `205297752` | `none` | `unclear` | “This but unironicaly” no se entiende sin el post citado. |
| `229326221` | `ethnonationalism` | `unclear` | Fragmento sobre nacionalidades sin el post al que responde. |
| `163767815` | `none` | `homophobia` | “leftypol fag” es un slur homofóbico. |
| `184178792` | `none` | `ableism` | “retard” como insulto capacitista. |
| `195351182` | sin `ableism` | con `ableism` | “retard russians” es capacitista además de rusófobo. |
| `207214201` | `violence_glorification` | `racism`, `islamophobia`, `violence_glorification` | “muslims and nonwhites breed / Kill em” identifica los grupos. |
| `173697589` | sin `homophobia` | con `homophobia` | “nigger fagit politician” incluye slur homofóbico. |

## Auditoría del oro previo

Las 52 anotaciones originales se hicieron con la UI que mostraba OP y quotes.
Se revisaron contra el texto objetivo. La auditoría encontró **dos etiquetas
claramente dependientes del contexto**:

| Post | Texto objetivo | Oro actual | Problema |
|---|---|---|---|
| `176409794` | “Is there a Midnight Meat Train or not? INTK” | `misogyny`, tox 1 | El texto no contiene misoginia; la etiqueta vino del contexto. |
| `229326221` | “Except Bongs, Swedes, Germans, French, Portuguese and Swiss.” | `ethnonationalism`, tox 1 | Fragmento ininterpretable sin el post citado; debe ser `unclear`, tox 0. |

No se modificó el oro directamente: ambas quedan como revisitas humanas. Se
generaron tareas y propuestas de revisita en `/tmp/opencode/` para no alterar
los archivos de la corrida principal.

También se marcaron dos posibles problemas de calidad que **no** son fugas de
contexto, para revisión humana posterior:

- `169094966` (“You probably ask retarded questions.”) figura como `none`/tox 1;
  “retarded” como insulto podría justificar `ableism`.
- `195052309` (hilo sobre FISA, Mueller y Dan Bongino) figura como `none`/tox 1;
  el texto podría sostener `conspiracy` o `institutional_distrust`.

Estos dos no se cambiaron porque la decisión requiere juicio humano y no hay
evidencia de que la etiqueta actual dependa del contexto.

## Tests

La suite sigue en **133 pruebas** y pasa con:

```bash
~/PyVenvs/NNnPLN/bin/python -m pytest -q
```

Las pruebas nuevas cubren que la tarea descarta `subject` y `context`, que el
prompt solo contiene el texto objetivo y que la UI de revisión no renderiza
contexto ni asunto.

## Estado de git

- Commit de código y tests: `proposal.py`, `prompts.py`, `review.py`,
  `tests/test_annotation_ai.py`, `tests/test_annotation_proposal.py`.
- Commit de documentación: `README.md`, `docs/annotation_guidelines.md`,
  `docs/ai_annotation_protocol.md` y esta entrada.
- Sin push a `origin`.
- `data/annotations/` y `Journal/Problems.md` siguen untracked.

## Siguiente paso

Reiniciar la sesión de revisión porque las tareas y propuestas cambiaron:

```bash
keklab annotate ai review \
  --tasks data/annotations/tasks/rotlk_pending_148.jsonl \
  --proposals data/annotations/proposals/rotlk_pending_148.big-pickle.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl \
  --reviewer flynnso
```

Revisitar `229326221`:

```bash
keklab annotate ai review \
  --tasks /tmp/opencode/revisit_229326221_tasks.jsonl \
  --proposals /tmp/opencode/revisit_229326221_proposals.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl \
  --reviewer flynnso --revisit
```

Revisitar `176409794`:

```bash
keklab annotate ai review \
  --tasks /tmp/opencode/revisit_176409794_tasks.jsonl \
  --proposals /tmp/opencode/revisit_176409794_proposals.jsonl \
  --gold data/annotations/rotlk_pilot_r1.jsonl \
  --reviews data/annotations/reviews/rotlk_pending_148.big-pickle.jsonl \
  --reviewer flynnso --revisit
```
