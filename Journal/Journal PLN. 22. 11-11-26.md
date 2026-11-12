# Journal PLN — Entrada 22 (11-11-2026)

## Contexto

Continuación de la entrada 21. Esta sesión cierra `URGENT.md`: el cleaner de
markup dejaba `<wbr>` en `text_clean`, que en el prompt v3 es el único texto que
ve el modelo. Además se amplió el alcance del cleaner a **todos los tags HTML
reales** (no solo `<wbr>`) y se reconstruyeron las 5.000 tareas con el prompt v3.

Estado heredado de la entrada 21 (ya aplicado, sin commit): prompt v3 en
`prompts.py` (solo `text_clean`, hash corregido), muestra con las 16 filas de
`<wbr>` parcheadas y tareas reconstruidas en v3.

## El fix del cleaner

### Lista blanca de tags reales

`EXTRA_TAGS_RE` era una lista corta (`span|div|b|i|strong|em|s|u`) con efectos
colaterales: `b` también capturaba `br`/`blockquote`, `i` capturaba `img`/
`iframe`, `s` capturaba `span`/`strong`/`small` y `u` capturaba `ul`. El patrón
no cubría HTML real que sí aparece en los posts (`<a>`, `<li>`, `<p>`, `<h1>`,
`<td>`, …).

Se sustituyó por `HTML_TAGS_RE`: una **lista blanca explícita** de tags HTML
reales, con el patrón `</?nombre\b[^>]*>` sustituido por `" "`.

La lista blanca es deliberada: en `/pol/` hay tags inventados que son parte
del chiste (`</kanye>`). Una regla genérica `<[^>]+>` borraría texto junto con
el markup. Con lista blanca:

| Entrada | ¿Se quita? | Motivo |
|---|---|---|
| `<wbr>` / `<wbr/>` | Sí, **sin espacio** | Es un hint de corte de palabra, no un separador: `students-a<wbr>t` → `students-at`. |
| `<a href=" target="_blank">` | Sí | HTML real; quedaba residual en `text_clean`. |
| `<iframe …>` | Sí | HTML real. |
| `</kanye>` | **No** | Chiste de `/pol/`, es contenido del post. |
| `< The` / `<ck` | No | No son tags (contenido). |

`WBR_RE` se aplica en `strip_markup` y en `strip_markup_plain` (antes solo se
desescapaba en la ruta plain).

## Datos

### Muestra (`data/classification/samples/rotlk_5000.jsonl`)

18 filas re-derivadas y con `content_hash` recalculado (`sha256(text_clean)`):

- 16 filas con `<wbr>` en `text_clean`.
- 2 filas con `<a href=" target="_blank">` residual (`115110323`, `207330062`).

El parche es mínimo y auditable: solo se re-deriva el `text_clean` cuando la
diferencia con el cleaner del repo es **exactamente** la eliminación de tags
HTML reales.

### Dos filas que NO se tocaron (documentadas)

`123255091` y `133796076` guardan un `text_clean` que **no es reproducible** con
el cleaner del repo: el `text_clean` del dump ROTLK externo dejó fragmentos de
los atributos del `<iframe>` (`s8SwlaqDrdM" frameborder="0" allowfullscreen>`),
mientras que el cleaner del repo borra el tag completo. Se conservan tal cual:
el dump externo no está montado y el `text_clean` del dump es la procedencia de
la muestra. Queda registrado como límite conocido, no como error.

### Tareas

`data/classification/tasks/rotlk_5000.jsonl` reconstruida con `keklab annotate
ai task`:

| Campo | Valor |
|---|---|
| Tareas | 5.000 (`task_id` únicos) |
| `prompt_version` | `v3` |
| `prompt_sha256` | `ef251abee5137ab35ff1882817c97aee5bdcdac9c0ee52900afbbe60d68c995e` |
| `guideline_version` | `v0.2` |
| Cegas | `subject=None`, contexto vacío |

Los `task_id` cambian en las 5.000 (el identificador incluye
`prompt_version`), así que las 385 filas válidas de la corrida v2 **no** son
reutilizables tal cual.

## Verificaciones

| Comprobación | Resultado |
|---|---|
| Suite de pruebas | **193 en verde** (185 previas + 8 nuevas de `tests/test_formal_markup.py`) |
| Muestra | 5.000 posts, 5.000 hilos, 0 duplicados, 0 textos vacíos, 42 meses (2016-06 a 2019-11) |
| `content_hash` | 0 discrepancias frente a `sha256(text_clean)` |
| Residuo de markup | 0 filas con `<wbr>`; 0 con tags HTML reales; `</kanye>` conservado |
| Tareas | 5.000, ids únicos, ciegas, `prompt_sha256` único y coincidente |
| Longitud de prompt v3 | 3.565 / 3.637 / 4.132 / **5.570** caracteres (mín / mediana / p95 / máx) |
| `classify doctor` | `prompt_match: True`, `context_fits: True` (`per_slot_ctx=8192`, prompt más largo 4.998 tokens, requerido 5.910) |

Nota: los hashes duplicados suben de 64 a 65 filas (28 valores compartidos por
93 filas). Son textos cortos legítimos e idénticos (`bump`, `kek`, `?`,
`/thread`); el salto viene de que 16 posts que antes eran distintos por el
`<wbr>` ahora coinciden al quitarlo. Los `task_id` siguen siendo únicos porque
incluyen `post_id`.

## Decisiones

| Decisión | Valor | Motivo |
|---|---|---|
| Sustitución de `<wbr>` | Sin espacio | Es un hint de corte de palabra; con espacio partiría la palabra. |
| Regla de tags | Lista blanca de HTML real | Una regla genérica borraría `</kanye>`, que es contenido. |
| Filas de `<iframe>` (2) | Se conservan y se documentan | El `text_clean` del dump es la procedencia; el dump no está montado. |
| Re-derivación de `text_clean` | Solo 18 filas, y solo si la diferencia es exactamente la eliminación de tags | Cambio mínimo y auditable sobre la muestra. |
| Tareas | Reconstruidas en v3 | El `task_id` incluye `prompt_version`; no hay reaprovechamiento de la corrida v2. |
| Oro de 200 | No se toca | El piloto está cerrado; su `text_clean` no tiene residuos de markup. |
| Reetiquetación | Fuera de esta sesión | Queda para la corrida de 5.000 con el prompt v3. |

## Enmiendas al pre-registro

1. `docs/silver_classification_protocol.md`: prompt v3 (solo `text_clean`),
   hash `ef251abe…`, `n_ctx = 8192`.
2. `docs/evaluation_protocol.md`: el experimento E0 (crudo vs saneado) se
   mantiene; el maestro ya no se anota en crudo.
3. `docs/handoff_llm_annotation.md`: versión, hash y prompt de referencia
   (`docs/prompts/annotation_prompt_v3.txt`).
4. `docs/ai_annotation_protocol.md`: `prompt_version = v3` y hash persistido en
   las tareas.

## Siguiente paso

1. Reetiquetar los 5.000 con el prompt v3, un solo cliente, con supervisor de
   salud del servidor:

   ```bash
   setsid llama-server \
     -m models/gguf/Qwen3-8B-Q4_K_M.gguf \
     --host 127.0.0.1 --port 8080 \
     -c 8192 -ngl 99 --parallel 1 \
     --jinja --reasoning off --no-webui --no-warmup \
     > /tmp/llama-server.log 2>&1 &

   keklab classify llm \
     --tasks data/classification/tasks/rotlk_5000.jsonl \
     --out data/classification/llm/raw/rotlk_5000.v3.qwen3-8b-q4_k_m.raw.jsonl \
     --backend llama_server --shard 1/1 \
     --n-ctx 8192 --n-gpu-layers -1 \
     --manifest data/classification/manifests/qwen3-v3.json
   ```

   ETA ≈ 6,8 h a 4,9 s/post. Archivo nuevo: los shards v2 quedan como registro
   y no se mezclan con v3.

2. Después: `classify silver` → split congelado por hilo → `classify dataset` →
   diagnóstico contra los 200 de oro, reportado por separado.

## Estado de git

Pendiente de commit en dos commits (código + datos). `models/SHA256SUMS` es una
modificación del usuario y no se toca.
