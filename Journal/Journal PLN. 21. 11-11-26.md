# Journal PLN — Entrada 21 (11-11-2026)

## Contexto

Continuación de la entrada 20. Al ejecutar el plan de recuperación, la guardia
de contexto se negó a arrancar: el prompt más largo necesitaba 10.773 tokens y
cada slot tenía 8.192. Esta entrada documenta la investigación, las decisiones
y la corrección adoptada.

## Hallazgo principal: el prompt duplicaba el post

El prompt v2 enviaba `text_raw` **y** `text_clean`. Para el post problemático
(`157832878`, arte Unicode/Braille) la atribución exacta de tokens es:

| Componente | Tokens |
|---|---:|
| Plantilla fija (menú de marcos + reglas) | 825 |
| `task_json` con raw + clean | 9.054 |
| `task_json` solo clean | 4.327 |
| `task_json` solo raw | 4.745 |
| **Prompt completo, ambos campos** | **9.861** |
| **Prompt completo, solo clean** | **5.134** |

Quitar `text_raw` basta para que el prompt quepa en 8.192. El mecanismo no es
que el raw sea caro en tokens (en este post es más barato por carácter), sino
que el post se enviaba **dos veces**.

## Otros factores identificados

1. **Post degenerado.** Es arte Unicode/Braille: 2,11 tokens/carácter en clean
   (1,47 en raw), frente a ~0,25 del inglés. Incluso sin raw cuesta 5.134
   tokens, 4× el siguiente más pesado (1.287).
2. **El cleaner deja `<wbr>`.** 63 ocurrencias en 16 de 5.000 posts
   (`EXTRA_TAGS_RE` no incluye `<wbr>` y `strip_markup_plain` solo desescapa
   entidades). También queda un `</kanye>`, que es contenido/juego y se
   conserva a propósito. Ver `URGENT.md`.
3. **Sobrecosto constante.** La plantilla fija son 825 tokens por petición.
4. **Duplicación media.** Quitar raw ahorra 166 tokens/prompt de media (15,1 %)
   y elimina ruido HTML (`<span>`, `&gt;`, `<br>`) para los 4.158 posts donde
   raw ≠ clean.
5. **Selección de muestra.** Admite posts de arte degenerado; es una decisión
   de muestreo, no de limpieza.
6. **Hueco de procedencia.** `prompt_sha256()` hasheaba solo
   `PROMPT_TEMPLATE` + menús: no cubría `PROMPT_VERSION` (la plantilla conserva
   el placeholder) ni la forma de `task_json`. Cambiar `render_prompt` sin
   corregir esto habría dejado el hash igual y el manifiesto mentiría.

## Verificación de corpus

Muestra de 500 prompts (top 100 por longitud + 400 aleatorios):

- Con ambos campos: 1/500 supera 8.192; máximo 9.861.
- Solo clean: 0/500 supera 8.192; máximo 5.134.

## Decisiones

| Decisión | Valor | Motivo |
|---|---|---|
| Prompt | **v3, solo `text_clean`** | Elimina la duplicación y el ruido HTML; cabe en 8.192. |
| Hash del prompt | Cubrir `PROMPT_VERSION` + campos de `task_json` | Cierra el hueco de procedencia. |
| Etiquetas v2 | **No se reutilizan** | `task_id` incluye `prompt_version`; v3 cambia todos los ids. Se reetiquetan los 5.000 (~6,8 h). |
| Contexto | Mantener `-c 8192 --parallel 1` | El peor caso v3 necesita ~6.046 tokens; sobran ~2.100. |
| `<wbr>` | Se elimina en el cleaner y se re-deriva `text_clean` en 16 posts | Es ruido HTML y en v3 es el único texto que ve el modelo. |
| `</kanye>` | Se conserva | Es contenido/juego del post, no markup del archivo. |
| `content_hash` | Se recalcula solo en los 16 posts afectados | `content_hash = sha256(text_clean)`; cambia al cambiar el texto. |
| Salida cruda | Archivo nuevo `rotlk_5000.v3.qwen3-8b-q4_k_m.raw.jsonl` | Evita mezclar filas v2 y v3; los shards v2 quedan como registro. |
| Oro de 200 | Se diagnosticará con v3 | Debe usar el mismo prompt que la plata. |

## Enmiendas al pre-registro

1. `docs/silver_classification_protocol.md`: el prompt usa solo `text_clean`
   (antes decía `text_raw` y `text_clean`); `prompt_version = v3`;
   `n_ctx = 8192`.
2. `docs/evaluation_protocol.md`: el experimento E0 (crudo vs saneado) sigue
   igual, porque el dataset exporta ambas representaciones; solo cambia el
   prompt del maestro.
3. `docs/handoff_llm_annotation.md`: actualizar versión y hash del prompt.

## Ejecución

1. `URGENT.md` con el problema del regex.
2. Código: prompt v3, hash corregido, `<wbr>` fuera del cleaner.
3. Re-derivar `text_clean`/`content_hash` en 16 posts y reconstruir tareas.
4. Verificar hash y guardia de contexto con `doctor`.
5. Reetiquetar los 5.000 con un solo cliente y supervisor de salud.
6. Plata → split → dataset → diagnóstico de oro, en pasos posteriores.

## Estado de git

Pendiente de commit. Cambios nuevos de esta entrada: `URGENT.md`, esta entrada,
`src/keklab/annotation/prompts.py`, `src/keklab/formal/markup_regex.py`,
`tests/test_annotation_proposal.py`, docs de protocolo, muestra y tareas
reconstruidas.
