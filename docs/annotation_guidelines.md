# Codebook de anotación — v0

Este documento fija el contrato de etiquetado humano del proyecto. Se aplica a
la muestra de 4plebs (período reciente) y al dump de ROTLK (período histórico).
La versión se congela como `v1` recién después del piloto y del control de
acuerdo. Mientras tanto, todo lo anotado queda bajo `guideline_version = "v0"`.

## Unidad y contexto

- La unidad de anotación es el **post**, no el hilo.
- Cada candidato conserva el OP del hilo y los posts citados (`>>id`) como
  contexto.
- Se anota el post objetivo, no el contexto. El contexto solo sirve para
  desambiguar.
- Si el post no se entiende ni con el contexto, se usa `unclear`.

## Marcos (multi-label binario)

Los marcos son categorías nominales. No son una escala Likert: no existe
intensidad ni orden entre ellos. Se activan todos los marcos presentes y
centrales para el post.

| # | Slug | Definición |
|---|---|---|
| 1 | `conspiracy` | Afirmación de un plan o coordinación secreta de élites, agencias o grupos. |
| 2 | `ethnonationalism` | Pureza, superioridad o jerarquía étnica/nacional genérica **no** cubierta por una etiqueta de grupo específico. |
| 3 | `antisemitism` | Hostilidad, tropos o prejuicio contra judíos. |
| 4 | `islamophobia` | Hostilidad o prejuicio contra musulmanes o el islam. |
| 5 | `rusophobia` | Hostilidad o prejuicio contra rusos o Rusia. |
| 6 | `sinophobia` | Hostilidad o prejuicio contra chinos o China. |
| 7 | `institutional_distrust` | Desconfianza generalizada hacia Estado, medios, academia o elecciones, sin afirmación conspirativa explícita. |
| 8 | `gender` | Política de género y sexualidad: antifeminismo, roles de género, masculinidad, temas LGBTQ+. |
| 9 | `violence_glorification` | Elogio, celebración o incitación a la violencia (no mera discusión o noticia). |
| 10 | `accelerationism` | Deseo de acelerar el colapso, el conflicto o la desestabilización. |
| 11 | `meta_topic` | Meta-discusión del tablero, moderación, raids, cultura online. |
| 12 | `none` | Ningún marco reconocible. |
| 13 | `unclear` | Contexto insuficiente, truncamiento o ambigüedad genuina. |

### Criterios por marco

Los ejemplos son paráfrasis ilustrativas, no posts del corpus, y sirven solo
para fijar el criterio.

#### `conspiracy`

- **Incluye:** atribuir un hecho a coordinación secreta (“lo hicieron a
  propósito”, “están coordinados”, “es un plan de X”).
- **Excluye:** desconfianza genérica sin plan (“los medios mienten”); crítica
  política sin coordinación oculta.
- **Positivo:** “Las farmacéuticas y los gobiernos acordaron ocultar el
  estudio.”
- **Negativo:** “No confío en las farmacéuticas.”

#### `ethnonationalism`

- **Incluye:** superioridad, pureza o jerarquía étnica/nacional genérica, sin
  nombrar un grupo específico cubierto por otra etiqueta.
- **Excluye:** prejuicio contra un grupo nombrado (usar la etiqueta específica);
  patriotismo sin jerarquía étnica.
- **Positivo:** “Las naciones solo funcionan si mantienen su composición
  étnica.”
- **Negativo:** “Prefiero vivir en mi país.”

#### `antisemitism`

- **Incluye:** tropos clásicos (control financiero o mediático, conspiración
  judía), hostilidad explícita, negación burlona del Holocausto.
- **Excluye:** crítica a Israel o a políticas israelíes sin tropos antisemitas.
- **Positivo:** “Los bancos y los medios están todos controlados por ellos.”
- **Negativo:** “El gobierno israelí respondió con fuerza al ataque.”

#### `islamophobia`

- **Incluye:** hostilidad contra musulmanes, generalizaciones sobre violencia o
  inferioridad, tropos de invasión.
- **Excluye:** crítica a una doctrina o a un Estado sin dirigirse a las
  personas musulmanas.
- **Positivo:** “Esa gente no puede convivir en una sociedad civilizada.”
- **Negativo:** “Ese país aplica una interpretación estricta de la ley.”

#### `rusophobia`

- **Incluye:** hostilidad contra rusos como grupo, generalizaciones de
  barbarie/autoritarismo inherente, deshumanización.
- **Excluye:** crítica a Putin, al ejército o al Estado ruso sin generalizar a
  las personas.
- **Positivo:** “Los rusos son genéticamente incapaces de democracia.”
- **Negativo:** “Rusia invadió el país y la OTAN respondió.”

#### `sinophobia`

- **Incluye:** hostilidad contra chinos como grupo, tropos de contagio/suciedad,
  generalizaciones de deslealtad o control.
- **Excluye:** crítica al Partido Comunista o al gobierno chino sin dirigirse a
  las personas chinas.
- **Positivo:** “Los chinos están por todos lados comprando todo, nos invaden.”
- **Negativo:** “China anunció nuevas tarifas.”

#### `institutional_distrust`

- **Incluye:** desconfianza generalizada hacia elecciones, prensa, academia,
  justicia o Estado, sin afirmar una coordinación secreta.
- **Excluye:** crítica puntual con evidencia; conspiración explícita (usar
  `conspiracy`, pueden coexistir si ambos son centrales).
- **Positivo:** “Ninguna elección en este país es legítima.”
- **Negativo:** “Esa elección tuvo irregularidades documentadas.”

#### `gender`

- **Incluye:** antifeminismo, roles de género, masculinidad, hostilidad contra
  personas LGBTQ+, debates sobre sexualidad.
- **Excluye:** menciones incidentales de género sin postura política.
- **Positivo:** “Las mujeres no deberían votar.”
- **Negativo:** “La candidata presentó su programa.”

#### `violence_glorification`

- **Incluye:** elogio, celebración o incitación a la violencia contra personas
  o grupos.
- **Excluye:** noticia, condena o discusión analítica de violencia.
- **Positivo:** “Que se maten entre ellos, es un espectáculo.”
- **Negativo:** “Hubo un tiroteo y varias personas murieron.”

#### `accelerationism`

- **Incluye:** deseo de acelerar el colapso, la guerra civil, la crisis o la
  desestabilización.
- **Excluye:** predicción pasiva de colapso sin desearlo; crítica al sistema sin
  aceleracionismo.
- **Positivo:** “Cuanto antes colapse todo, mejor.”
- **Negativo:** “La situación económica va a empeorar.”

#### `meta_topic`

- **Incluye:** moderación, bans, raids, calidad del tablero, cultura online,
  discusión sobre el propio foro.
- **Excluye:** política del mundo real sin referencia al tablero.
- **Positivo:** “Los mods borran todo lo que no les gusta.”
- **Negativo:** “El Senado aprobó la ley.”

#### `none`

- **Incluye:** posts sin marco reconocible: imágenes, spam, preguntas
  logísticas, texto trivial, off-topic no político.
- **Regla:** exclusivo con todos los demás marcos y con `unclear`.

#### `unclear`

- **Incluye:** truncamiento, referencias que no se pueden resolver ni con el
  contexto, sarcasmo genuinamente ambiguo, texto en otro idioma sin traducir.
- **Regla:** exclusivo con todos los demás marcos y con `none`.

### Reglas de solapamiento

1. Las etiquetas específicas (`antisemitism`, `islamophobia`, `rusophobia`,
   `sinophobia`) **reemplazan** a `ethnonationalism`. No se anotan las dos por
   el mismo contenido.
2. `ethnonationalism` se reserva para encuadres étnicos/nacionales genéricos
   sin grupo nombrado.
3. `conspiracy` exige un plan explícito. `institutional_distrust` es la
   etiqueta más amplia y no conspirativa. Pueden coexistir solo si ambos son
   centrales.
4. `violence_glorification` describe la postura frente a la violencia;
   `accelerationism` describe el deseo de acelerar el colapso. Pueden coexistir.
5. `none` y `unclear` son excluyentes con cualquier otro marco y entre sí.
6. Si hay duda entre `none` y un marco: si el marco está claramente presente,
   anotarlo; si no, `none`. Si no se puede decidir por falta de contexto,
   `unclear`.
7. No se anota ideología inferida. Se anota lo que el post dice o implica de
   forma directa.

## Toxicidad (ordinal 0–3)

| Nivel | Definición |
|---|---|
| `0` | Neutral, sin toxicidad. |
| `1` | Insulto leve, hostilidad o edgy sin agresión grave. |
| `2` | Deshumanización explícita, slur, acoso u odio dirigido a un grupo. |
| `3` | Amenaza, incitación o elogio de violencia contra personas. |

- Es una escala **ordinal**, no de intervalo. Para acuerdo se usa kappa
  cuadrática ponderada.
- Para E0/E2 puede modelarse como 4 clases o colapsarse a binario
  (`0–1` vs `2–3`) como tarea secundaria.
- La toxicidad es independiente de los marcos: un post puede tener un marco
  político y toxicidad `0`, o no tener marco y toxicidad `2`.

## Flujo de trabajo

### 1. Muestreo

```bash
keklab annotate sample \
  --source fourplebs \
  --months 24 \
  --random 20 \
  --targeted 10 \
  --seed 13 \
  --out data/samples/pilot_fourplebs.jsonl
```

- **Aleatorio:** estima prevalencia. Estratificado por mes.
- **Dirigido:** enriquece marcos raros (`rusophobia`, `sinophobia`,
  `accelerationism`) para entrenamiento/calibración. No sirve para prevalencia.
- Se pueden conservar algunos posts vacíos o solo-imagen con
  `--include-empty N` para probar `none`.
- `--source rotlk --parquet <canonical.parquet>` usa el mismo formato de salida
  cuando el dump esté disponible.

### 2. Anotación

```bash
keklab annotate run \
  --input data/samples/pilot_fourplebs.jsonl \
  --annotator flynnso \
  --guideline v0 \
  --round 1 \
  --out data/annotations/pilot_fourplebs_r1.jsonl
```

Teclas:

| Entrada | Acción |
|---|---|
| `1 3 7` | Activa/desactiva esos marcos. |
| `n` | Marco `none` (limpia los demás). |
| `u` | Marco `unclear` (limpia los demás). |
| `c` | Limpia la selección. |
| `t` | Cicla toxicidad `0 → 1 → 2 → 3 → 0`. |
| `s` | Guarda y avanza. |
| `b` | Vuelve al post anterior. |
| `q` | Sale sin guardar el post actual. |
| `?` | Ayuda. |

El guardado es automático tras cada `s`, con escritura atómica y actualización
por clave `(post_id, thread_id, source, round, annotator)`. Al reanudar se
omiten los posts ya anotados en esa ronda.

### 3. Exportación y estadísticas

```bash
keklab annotate export --input data/annotations/pilot_fourplebs_r1.jsonl --format csv
keklab annotate stats --input data/annotations/pilot_fourplebs_r1.jsonl
```

El CSV incluye `frame_labels` como lista separada por `|` y una columna binaria
por marco.

## Piloto y control de acuerdo

1. Anotar **30 posts**: 20 aleatorios + 10 dirigidos.
2. Esperar al menos **una semana**.
3. Reanotar ~20% (6 posts) con `--round 2` en un archivo separado.
4. Calcular acuerdo:

```bash
keklab annotate agreement \
  --a data/annotations/pilot_fourplebs_r1.jsonl \
  --b data/annotations/pilot_fourplebs_r2.jsonl
```

Se reporta:

- kappa de Cohen por marco (binario);
- kappa cuadrática ponderada para toxicidad;
- F1 macro/micro multi-label;
- coincidencia exacta del conjunto de marcos y Jaccard medio.

### Limitación del self test-retest

No hay segundo anotador. La comparación entre `round=1` y `round=2` mide
**consistencia intra-anotador**, no acuerdo inter-anotador. Un kappa alto indica
estabilidad del criterio y del codebook, pero no elimina sesgo individual. Si
más adelante se suma un segundo anotador, se repetirá el cálculo sobre una
submuestra y se reportarán ambos resultados por separado.

### Umbral de calidad

- Si algún marco con soporte suficiente queda con `kappa < 0.6`, revisar la
  definición, agregar ejemplos y repetir la calibración.
- La toxicidad se evalúa con kappa cuadrática; un valor bajo obliga a revisar
  los límites entre niveles.
- No se congela `v1` ni se escala el conjunto oro hasta superar el control.

## Casos límite

- **Greentext y citas:** el texto citado es contexto; no se anota como si
  fuera del post objetivo.
- **Posts vacíos o solo-imagen:** `none`, salvo que el contexto inmediato
  aporte un marco claro.
- **Truncamiento:** si falta el final y cambia el sentido, `unclear`.
- **Idioma:** si no se puede interpretar con seguridad, `unclear`; no traducir
  con herramientas externas durante la anotación.
- **Sarcasmo:** si el marco es recuperable por el contexto, anotarlo; si no,
  `unclear`.
- **Spam/raid:** `meta_topic` si es cultura del tablero; `none` si es ruido sin
  contenido.
- **Noticias neutras:** `none`, aunque el tema sea político.

## Versionado

- `v0`: este documento, previo al piloto.
- `v1`: se congela después de la calibración y antes del conjunto oro.
- Cualquier cambio posterior a `v1` sube la versión y obliga a reanotar la
  submuestra de control.

## Archivos

```
docs/annotation_guidelines.md          # este codebook
src/keklab/annotation/labels.py        # vocabulario y validación
src/keklab/annotation/schema.py        # SamplePost / AnnotationRecord
src/keklab/annotation/store.py         # JSONL, reanudación, exportación
src/keklab/annotation/sampler.py       # 4plebs y ROTLK
src/keklab/annotation/agreement.py     # kappa y F1
src/keklab/annotation/cli.py           # interfaz de terminal
data/samples/                          # candidatos (versionados si son pequeños)
data/annotations/                      # anotaciones oro
```

Las cachés crudas de la API de 4plebs no se versionan.
