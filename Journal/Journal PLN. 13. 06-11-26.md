# Journal PLN — Entrada 13 (06-11-2026)

## Contexto

Esta entrada responde a los problemas anotados en `Journal/Problems.md`
mientras el piloto está en 52/200 posts. No cambia el tamaño muestral ni el
split pre-registrado; corrige vocabulario, aclara reglas y deja registrado qué
no se toca.

## El `>` del post 9

El post 9 (`190197729`) empieza con `>yfw...` porque el HTML de ROTLK trae
`<span class="quote">&gt;yfw...</span>`. Es **greentext**, no un carácter
espurio ni un error de regex. En la muestra hay 41/200 posts con `>` en
`text_clean`: 31 con `>` al inicio y 10 inline.

No se modifica nada. `render_sample` muestra `text_raw` primero por
trazabilidad, y con esta aclaración el comportamiento es correcto. Tocar
`text_clean` o los `>` habría cambiado el contenido y el `content_hash` sin
necesidad.

## `antifeminism` → `misogyny`

Se renombra el marco fino 10. `antifeminism` funcionaba como proxy de
misoginia; `misogyny` nombra el fenómeno directamente y evita el eufemismo.
La definición se amplía: hostilidad, desprecio u objetificación hacia las
mujeres como clase; inferioridad femenina; reducción a objeto sexual, botín de
guerra o función reproductiva; slurs; oposición a los derechos de las mujeres.
No exige mencionar el feminismo.

Los tres positivos existentes **no eran falsos positivos**: son verdaderos
positivos de misoginia anotados con el nombre viejo. Por eso no se rejuzgaron;
solo se migró el nombre:

| Post | Antes | Después |
|---|---|---|
| `151478852` | `ethnonationalism`, `racism`, `antifeminism`, `violence_glorification` | `ethnonationalism`, `racism`, `misogyny`, `violence_glorification` |
| `176409794` | `antifeminism` | `misogyny` |
| `226180859` | `racism`, `antifeminism` | `racism`, `misogyny` |

Se migraron los 52 registros a `guideline_version = "v0.1"` y se agregó un
alias `antifeminism → misogyny` en `normalize_frame_labels`, de modo que
cualquier archivo viejo siga cargando aunque no se reescriba. La migración se
hizo en sitio, preservando el orden, con backup en
`/tmp/opencode/rotlk_pilot_r1_pre_misogyny.jsonl`. El archivo de anotaciones
sigue untracked.

El codebook pasa a v0.1. La taxonomía gruesa no cambia: `misogyny` sigue
mapeando a `gender_sexuality_prejudice`.

## Post de Christchurch

El post `206907369` (sample #26) estaba como `meta_topic` +
`institutional_distrust`. El texto comenta el manifiesto, los “traps” para
periodistas y la credulidad de los medios; no es meta del tablero. Se quitó
`meta_topic` y quedó solo `institutional_distrust`, con toxicidad 1. Tampoco
corresponde `violence_glorification`: comenta el manifiesto, no lo elogia.

## Violencia y toxicidad

`violence_glorification` y toxicidad 3 pueden coincidir, pero no son
sinónimos. El marco describe la postura del post frente a la violencia; la
toxicidad mide la severidad del lenguaje. Se agregó esta regla al codebook,
con ejemplos:

- toxicidad 3 sin el marco: amenaza directa;
- el marco con toxicidad 2: celebración de violencia no dirigida a personas
  reales;
- ambos: celebración de muertes o incitación a la violencia contra personas.

El post `155513535` (“Dead Americans is never pointless”) se mantiene con
`violence_glorification` y toxicidad 3: justifica/celebra muertes. La
coincidencia es esperada, no un conflicto de etiquetas.

## Estereotipos nacionales

`national_stereotypes` no se agrega a este piloto. Se documenta como clase
candidata para el próximo estudio en `docs/evaluation_protocol.md`, con
definición y mapeo futuro a `ethnoracial_prejudice`. Agregarla ahora obligaría
a re-anotar los 52 posts previos y rompería la taxonomía pre-registrada. En
este piloto esos casos se siguen cubriendo con `racism`, `ethnonationalism` o
la etiqueta específica que corresponda.

## Tests

La suite pasó de 109 a **111 pruebas**. Las nuevas cubren:

- el alias `antifeminism → misogyny` al normalizar y al togglear;
- la carga de un JSONL viejo con `antifeminism`, que se lee como `misogyny`;
- que `antifeminism` ya no está en `FRAME_LABELS` ni en los términos dirigidos.

Todos pasan con `~/PyVenvs/NNnPLN/bin/python -m pytest -q`.

## Estado de git

- `0234ffb`: código y tests del renombre, con alias de compatibilidad.
- Este commit: documentación (`README.md`, `docs/annotation_guidelines.md`,
  `docs/evaluation_protocol.md`, `docs/pipeline_draft.md`) y esta entrada.
- Sin push a `origin`.
- `data/annotations/rotlk_pilot_r1.jsonl` se migró en sitio pero sigue
  untracked, igual que `Journal/Problems.md`.

## Lo que no se hizo

- No se cambió la visualización del greentext: no hay bug.
- No se agregó `national_stereotypes` al piloto.
- No se reanotaron los 52 posts: los tres positivos de misoginia se
  confirmaron y solo se renombraron.
- No se tocó el split ni el protocolo de evaluación más allá de la enmienda
  documentada.

## Siguiente paso

Continuar la anotación desde el post 53 con el codebook v0.1:

```bash
keklab annotate run \
  --input data/samples/rotlk_pilot_200.jsonl \
  --annotator flynnso \
  --guideline v0.1 \
  --round 1 \
  --out data/annotations/rotlk_pilot_r1.jsonl
```
