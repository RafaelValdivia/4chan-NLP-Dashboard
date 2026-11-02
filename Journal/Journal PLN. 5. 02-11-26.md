# Journal PLN — Entrada 5 (02-11-2026)

## Contexto

Las entradas anteriores dejaron E0/E2 como próximo paso, pero ambos experimentos
requieren etiquetas y todavía no existe un conjunto oro ni plata. La anotación
humana de la muestra estratificada nunca se inició. Sin etiquetas, construir el
harness de E0/E2 solo validaría plomería: no produciría resultados.

Esta entrada documenta la propuesta de arranque de anotación **antes** de
implementar código. La implementación queda para la siguiente iteración.

## Decisiones

- **Anotación por CLI**, sin interfaz web ni herramienta externa.
- **Fuente del piloto:** API de archivo de 4plebs ahora; ROTLK cuando el dump
  esté disponible. Mismo formato y mismo codebook para ambos períodos.
- **Marcos:** etiquetas binarias multi-label. No se usa escala Likert: los
  marcos son categorías nominales, no intensidades ordenadas.
- **Toxicidad:** escala ordinal de cuatro niveles (`0–3`).
- **Threat:** se elimina del esquema de anotación. No aporta al objetivo y
  agrega carga al anotador.
- **Acuerdo:** self test-retest sobre ~20% de la muestra. No hay segundo
  anotador. Se documenta como limitación: mide consistencia intra-anotador, no
  acuerdo inter-anotador.

## Vocabulario de marcos

| Slug | Definición |
|---|---|
| `conspiracy` | Afirmación de un plan o coordinación secreta de élites o grupos. |
| `ethnonationalism` | Pureza, superioridad o jerarquía étnica/nacional genérica **no** cubierta por una etiqueta de grupo específico. |
| `antisemitism` | Hostilidad, tropos o prejuicio contra judíos. |
| `islamophobia` | Hostilidad o prejuicio contra musulmanes o el islam. |
| `rusophobia` | Hostilidad o prejuicio contra rusos o Rusia. |
| `sinophobia` | Hostilidad o prejuicio contra chinos o China. |
| `institutional_distrust` | Desconfianza generalizada hacia Estado, medios, academia o elecciones, sin afirmación conspirativa explícita. |
| `gender` | Política de género y sexualidad: antifeminismo, roles de género, masculinidad, temas LGBTQ+. |
| `violence_glorification` | Elogio, celebración o incitación a la violencia (no mera discusión). |
| `accelerationism` | Deseo de acelerar el colapso, el conflicto o la desestabilización. |
| `meta_topic` | Meta-discusión del tablero, moderación, raids, cultura online. |
| `none` | Ningún marco reconocible. |
| `unclear` | Contexto insuficiente, truncamiento o ambigüedad genuina. |

### Reglas de solapamiento

- Las etiquetas de prejuicio específicas (`antisemitism`, `islamophobia`,
  `rusophobia`, `sinophobia`) **reemplazan** a `ethnonationalism`. Esta última
  se reserva para encuadres étnicos/nacionales genéricos sin grupo nombrado.
- `conspiracy` exige un plan explícito; `institutional_distrust` es la etiqueta
  más amplia y no conspirativa. Pueden coexistir solo si ambos son centrales.
- `violence_glorification` describe la postura frente a la violencia;
  `accelerationism` describe el deseo de acelerar el colapso. Pueden coexistir.
- `none` y `unclear` son excluyentes con cualquier otro marco y entre sí.
  `none` = no hay marco; `unclear` = no se puede decidir por falta de contexto
  o ambigüedad.

## Toxicidad

| Nivel | Definición |
|---|---|
| `0` | Neutral, sin toxicidad. |
| `1` | Insulto leve, hostilidad o edgy sin agresión grave. |
| `2` | Deshumanización explícita, slur, acoso o odio dirigido a un grupo. |
| `3` | Amenaza, incitación o elogio de violencia contra personas. |

Se trata como escala **ordinal**, no de intervalo: para acuerdo se usa kappa
cuadrática ponderada. Para E0/E2 se puede modelar como 4 clases o colapsar a
binario (`0–1` vs `2–3`) como tarea secundaria.

## Registros

### Candidato a anotación

```json
{
  "post_id": "...",
  "thread_id": "...",
  "source": "fourplebs",
  "period": "recent_2020_plus",
  "timestamp_utc": "...",
  "subject": "...",
  "text_raw": "...",
  "text_clean": "...",
  "quotes": ["..."],
  "content_hash": "...",
  "stratum": {"month": "2026-10", "reason": "random"},
  "context": {
    "op": {"post_id": "...", "text_raw": "..."},
    "parents": []
  }
}
```

### Anotación

```json
{
  "post_id": "...",
  "thread_id": "...",
  "source": "fourplebs",
  "period": "recent_2020_plus",
  "content_hash": "...",
  "frame_labels": ["conspiracy"],
  "toxicity": 2,
  "annotator": "...",
  "round": 1,
  "tier": "gold",
  "guideline_version": "v1",
  "annotated_utc": "...",
  "notes": "..."
}
```

El registro de anotación se une al candidato por `post_id`, `thread_id`,
`source` y `content_hash`. El hash detecta cambios de texto entre muestreo y
anotación.

## Muestreo

### 4plebs (piloto actual)

- Ventana de 24 meses, estratificada por mes.
- **20 posts aleatorios** para estimar prevalencia y calibrar el codebook.
- **10 posts dirigidos** a marcos raros (`rusophobia`, `sinophobia`,
  `accelerationism`) mediante búsqueda del archivo.
- Se guarda el OP y los posts citados como contexto.
- Se excluyen posts solo-imagen, salvo un par deliberado para probar `none`.
- Se conservan `text_raw` y `text_clean` para reutilizar la muestra en E0.

### ROTLK (cuando esté disponible)

- Misma interfaz de muestreo, leyendo el parquet canónico.
- Estratificación por mes.
- Contexto de hilo por `thread_id`.
- Mismo formato de salida JSONL.

### Prevalencia vs entrenamiento

La muestra aleatoria sirve para estimar prevalencia. La muestra dirigida a
marcos raros sirve para entrenamiento/evaluación, no para prevalencia. El campo
`stratum.reason` registra el origen de cada post.

## Hallazgos de la API de 4plebs

- `/_/api/chan/index/?board=pol&page=1` devuelve hilos indexados por número, con
  `op` únicamente.
- `/_/api/chan/thread/?board=pol&num=...` devuelve `op` y `posts` como **dict**
  indexado por número de post.
- `/_/api/chan/search/?boards=pol&text=...&page=1` devuelve `posts` como
  **list**; útil para muestreo dirigido.
- La API exige `User-Agent`; sin él responde con error de política.
- Conviene limitar la tasa de consultas y cachear en disco.

El `FourplebsClient` actual apunta a `a.4cdn.org` y espera la forma de la API de
4chan (`catalog.json`, `thread/{id}.json`, `posts` como lista). Para el archivo
de 4plebs hace falta un adaptador o un cliente específico.

## CLI de anotación

```bash
keklab annotate sample --source fourplebs --months 24 --random 20 --targeted 10 \
  --out data/samples/pilot_fourplebs.jsonl

keklab annotate run --input data/samples/pilot_fourplebs.jsonl \
  --annotator flynnso --guideline v1 \
  --out data/annotations/pilot_fourplebs.jsonl

keklab annotate export --input data/annotations/pilot_fourplebs.jsonl --format csv
keklab annotate stats --input data/annotations/pilot_fourplebs.jsonl
keklab annotate agreement --a data/annotations/round1.jsonl \
  --b data/annotations/round2.jsonl
```

### Interacción

- Metadatos: fuente, fecha, hilo, asunto.
- Contexto: OP y posts citados.
- Texto crudo del post a anotar.
- Marcos numerados que se activan/desactivan.
- `t` cicla toxicidad `0–3`.
- `n` = `none`, `u` = `unclear` (limpian los demás marcos).
- `s` guarda, `b` vuelve, `q` guarda y sale.
- Auto-guardado tras cada post y reanudación por `post_id`.
- Progreso y tiempo transcurrido visibles.

## Acuerdo y calibración

1. Anotar 30 posts de piloto.
2. Repetir ~20% (6 posts) en una segunda ronda, tras un lapso de al menos una
   semana, con el mismo anotador (`round=2`).
3. Calcular kappa de Cohen por marco, kappa cuadrática ponderada para toxicidad
   y F1 macro/micro para el conjunto multi-label.
4. Si algún marco queda por debajo de `kappa ≈ 0.6`, revisar la definición y
   repetir la calibración.
5. Congelar el codebook como `v1` recién después de la calibración.

Limitación registrada: el self test-retest mide estabilidad del anotador, no
reliability inter-anotador. Si más adelante se suma un segundo anotador, se
repetirá el cálculo sobre una submuestra.

## Artefactos

```
docs/annotation_guidelines.md
src/keklab/annotation/
  __init__.py
  labels.py        # vocabulario y validación
  schema.py        # AnnotationRecord
  store.py         # JSONL, reanudación, dedupe
  sampler.py       # 4plebs + ROTLK
  agreement.py     # kappa / F1
  cli.py           # interfaz interactiva
tests/test_annotation_*.py
data/samples/       # candidatos
data/annotations/   # oro
```

Se versionan los JSONL pequeños de piloto/oro. Las cachés crudas de la API
quedan fuera de git. `Annotation.threat` se elimina del esquema; no hay
anotaciones previas que migrar.

## Hitos

1. Codebook `v1` borrador con definiciones y ejemplos.
2. Adaptador de la API de archivo de 4plebs y sampler.
3. CLI de anotación con validación, reanudación y auto-guardado.
4. Tests del vocabulario, la exclusividad, la reanudación y el sampler.
5. Piloto de 30 posts.
6. Self test-retest del 20% y cálculo de acuerdo.
7. Congelar codebook `v1`.
8. Conjunto oro de 200–300 posts (aleatorio + enriquecido).
9. E1: competencia de maestros sobre oro y generación de plata.
10. E0/E2 sobre oro/plata.

## Pendientes

- ROTLK sigue sin estar disponible; el sampler queda preparado pero sin correr.
- No hay segundo anotador; se acepta la limitación del self test-retest.
- La API de 4plebs impone límites y requiere cortesía; falta medir latencia y
  cuotas reales.
- La taxonomía es preliminar y puede cambiar tras el piloto.
- La prevalencia de marcos raros es desconocida; el muestreo dirigido la
  mitigará para entrenamiento, no para estimación poblacional.
