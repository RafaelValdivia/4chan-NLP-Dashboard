# URGENT — markup cleaner leaves `<wbr>` in `text_clean`

> **Estado: resuelto** en la entrada 22 del journal (`Journal/Journal PLN. 22.
> 11-11-26.md`). `<wbr>` se quita en `strip_markup` y `strip_markup_plain`, el
> alcance se amplió a los tags HTML reales (lista blanca, `</kanye>` se
> conserva) y las tareas se reconstruyeron con el prompt v3. Se conserva el
> documento como registro del problema.

## What happened

The markup regex cleaner (`src/keklab/formal/markup_regex.py`) does not strip
`<wbr>` (the HTML word-break hint). As a result, 63 `<wbr>` occurrences survive
in `text_clean` across 16 of the 5,000 sampled posts.

Root cause:

- `EXTRA_TAGS_RE` only lists `span|div|b|i|strong|em|s|u`, so `<wbr>` is never
  matched by `strip_markup`.
- `strip_markup_plain` (used when `has_html` is false) only calls
  `html.unescape`, so it cannot remove tags either.

Reproduction:

```python
from keklab.annotation.store import load_tasks
tasks = load_tasks("data/classification/tasks/rotlk_5000.jsonl")
print(sum("<wbr" in t.text_clean.lower() for t in tasks))  # 16
```

## Why it matters now

The silver prompt moves to **v3**, which sends **only `text_clean`** to the
model. Any leftover markup in `text_clean` is therefore the only text the model
sees for those posts.

## Scope of the fix

- Strip `<wbr>` and `<wbr/>` (case-insensitive) in both `strip_markup` and
  `strip_markup_plain`.
- Re-derive `text_clean` for the 16 affected sample rows and recompute their
  `content_hash` (`sha256(text_clean)`), then rebuild tasks.
- **Do not** strip `</kanye>`. It is a single tongue-in-cheek tag that is part
  of the post's content; removing it would destroy text.

## What this is not

- It is not the cause of the oversized prompt. The one prompt that exceeded
  8,192 tokens was a Braille/Unicode art post, and the main cause was the prompt
  sending `text_raw` and `text_clean` (duplicating the post). That is fixed
  separately by prompt v3.
