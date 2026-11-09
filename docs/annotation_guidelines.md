# Codebook de anotación — v0.2

Este documento fija el contrato de etiquetado humano del proyecto. Se aplica a
la muestra de 4plebs (período reciente) y al dump de ROTLK (período histórico).
La versión se congela como `v1` recién después del piloto y del control de
acuerdo. El piloto de 200 posts se anotó bajo `guideline_version = "v0.1"`.

> **Cambio v0.2 (09-11-2026).** Se retiraron los marcos `eugenics` y `ableism`
> y la cabeza gruesa `eugenics_ableism`. El codebook queda en **16 marcos
> finos** y **7 cabezas gruesas**. Los archivos históricos conservan las
> etiquetas retiradas como evidencia; el cargador las elimina y, si un registro
> queda vacío, lo colapsa a `none`. La decisión y su justificación están en
> `Journal/Journal PLN. 16. 09-11-26.md` y en la enmienda de
> `docs/evaluation_protocol.md`.

## Unidad y contexto

- La unidad de anotación es el **post**, no el hilo.
- La anotación se hace **solo con el texto del post objetivo**. No se usan el
  OP, los posts citados (`>>id`), el asunto del hilo ni los metadatos de
  muestreo para asignar marcos ni toxicidad, porque el clasificador de
  producción no los verá.
- Los datos de muestreo pueden conservarse para auditoría y trazabilidad, pero
  no son una pista de etiqueta.
- Si el post no se entiende por sí solo, se usa `unclear`.

## Marcos (multi-label binario)

Los marcos son categorías nominales. No son una escala Likert: no existe
intensidad ni orden entre ellos. Se activan todos los marcos presentes y
centrales para el post.

| # | Slug | Definición |
|---|---|---|
| 1 | `conspiracy` | Afirmación de un plan o coordinación secreta de élites, agencias o grupos. |
| 2 | `ethnonationalism` | Pureza, superioridad o jerarquía nacional/étnica genérica **no** cubierta por una etiqueta más específica. |
| 3 | `racism` | Prejuicio, slur, segregación o jerarquía racial/étnica **no** cubierta por una etiqueta de grupo específica. |
| 4 | `antisemitism` | Hostilidad, tropos o prejuicio contra judíos. |
| 5 | `islamophobia` | Hostilidad o prejuicio contra musulmanes o el islam. |
| 6 | `rusophobia` | Hostilidad o prejuicio contra rusos o Rusia. |
| 7 | `sinophobia` | Hostilidad o prejuicio contra chinos o China. |
| 8 | `misogyny` | Hostilidad, desprecio u objetificación hacia las mujeres como clase; inferioridad femenina u oposición a los derechos de las mujeres. |
| 9 | `transphobia` | Hostilidad, burla o prejuicio contra personas trans o negación de su identidad. |
| 10 | `homophobia` | Hostilidad, burla o prejuicio contra personas gays o lesbianas. |
| 11 | `institutional_distrust` | Desconfianza generalizada hacia Estado, medios, academia o elecciones, sin afirmación conspirativa explícita. |
| 12 | `violence_glorification` | Elogio, celebración o incitación a la violencia (no mera discusión o noticia). |
| 13 | `accelerationism` | Deseo de acelerar el colapso, el conflicto o la desestabilización. |
| 14 | `meta_topic` | Meta-discusión del tablero, moderación, raids, cultura online. |
| 15 | `none` | Ningún marco reconocible. |
| 16 | `unclear` | Contexto insuficiente, truncamiento o ambigüedad genuina. |

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

#### `racism`

- **Incluye:** superioridad o inferioridad racial, slurs, segregación, jerarquía
  racial, atribución de rasgos o crímenes a una raza, supremacismo blanco.
- **Excluye:** prejuicio contra un grupo cubierto por una etiqueta más específica
  (`antisemitism`, `islamophobia`, `rusophobia`, `sinophobia`); crítica a
  políticas migratorias sin jerarquía racial.
- **Positivo:** “Las razas no deberían mezclarse.”
- **Negativo:** “La ley de inmigración cambió los requisitos.”

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

#### `misogyny`

- **Incluye:** hostilidad, desprecio u objetificación hacia las mujeres como
  clase; afirmaciones de inferioridad femenina; reducción de mujeres a objetos
  sexuales, botín de guerra o función reproductiva; slurs como “femoid”;
  oposición al sufragio, al trabajo, a los derechos o a la igualdad; teorías de
  privilegio femenino o misandria usadas como ataque. No exige mencionar el
  feminismo ni una ideología explícita.
- **Excluye:** discusión neutral sobre roles de género o una política concreta
  sin hostilidad; crítica a una mujer concreta por sus actos sin apuntar a las
  mujeres como clase. `transphobia` y `homophobia` son ejes distintos y pueden
  coexistir si ambos son centrales.
- **Positivo:** “Las mujeres no deberían votar; el feminismo arruinó la
  sociedad.”
- **Positivo (objetificación):** comentarios sexuales degradantes sobre una
  mujer o sobre mujeres de una nacionalidad concreta.
- **Negativo:** “La candidata presentó su programa.”

#### `transphobia`

- **Incluye:** negación de la identidad trans, misgendering hostil, slurs,
  exclusión, deshumanización, “son hombres disfrazados”, oposición a derechos
  trans basada en esa hostilidad.
- **Excluye:** discusión neutral sobre sexo biológico sin dirigirse a personas
  trans; crítica a una política concreta sin negar la identidad.
- **Positivo:** “Los trans no son lo que dicen ser, son hombres disfrazados.”
- **Negativo:** “La ley de deportes discute categorías por sexo.”

#### `homophobia`

- **Incluye:** hostilidad o slurs contra gays y lesbianas, “degeneración”,
  oposición a derechos basada en esa hostilidad, sodomía como crimen o
  enfermedad.
- **Excluye:** debate neutral sobre derechos sin hostilidad; crítica a una
  persona sin apuntar a su orientación.
- **Positivo:** “Los homosexuales son una degeneración y no deberían adoptar.”
- **Negativo:** “El parlamento debatió el matrimonio igualitario.”

#### `institutional_distrust`

- **Incluye:** desconfianza generalizada hacia elecciones, prensa, academia,
  justicia o Estado, sin afirmar una coordinación secreta.
- **Excluye:** crítica puntual con evidencia; conspiración explícita (usar
  `conspiracy`, pueden coexistir si ambos son centrales).
- **Positivo:** “Ninguna elección en este país es legítima.”
- **Negativo:** “Esa elección tuvo irregularidades documentadas.”

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

- **Incluye:** truncamiento, referencias que no se pueden resolver con el
  texto del post, sarcasmo genuinamente ambiguo, texto en otro idioma sin
  traducir.
- **Regla:** exclusivo con todos los demás marcos y con `none`.

### Reglas de solapamiento

1. Las etiquetas de prejuicio con blanco específico (`antisemitism`,
   `islamophobia`, `rusophobia`, `sinophobia`, `transphobia`, `homophobia`)
   **reemplazan** a las genéricas `ethnonationalism` y `racism` cuando la
   etiqueta específica cubre el mismo contenido. Si el post contiene prejuicios
   distintos (por ejemplo, racismo y homofobia), se anotan ambos.
2. `racism` se usa para prejuicio racial/étnico sin una etiqueta más específica;
   reemplaza a `ethnonationalism` cuando el eje es racial.
3. `ethnonationalism` se reserva para encuadres nacionales/étnicos genéricos
   sin grupo nombrado ni eje racial específico.
4. `transphobia` y `homophobia` son ejes independientes de `misogyny`. Un
   post puede ser ambos si ataca a las mujeres y a personas trans o gays; no se
   usa `misogyny` para contenido exclusivamente trans/homofóbico. `misogyny`
   puede coexistir con `racism` o `ethnonationalism` cuando la hostilidad hacia
   las mujeres se articula por su nacionalidad, etnia o raza.
5. `conspiracy` exige un plan explícito. `institutional_distrust` es la
   etiqueta más amplia y no conspirativa. Pueden coexistir solo si ambos son
   centrales.
6. `violence_glorification` describe la postura frente a la violencia;
   `accelerationism` describe el deseo de acelerar el colapso. Pueden coexistir.
7. `none` y `unclear` son excluyentes con cualquier otro marco y entre sí.
8. Si hay duda entre `none` y un marco: si el marco está claramente presente,
   anotarlo; si no, `none`. Si no se puede decidir por falta de información en
   el texto del post, `unclear`.
9. No se anota ideología inferida. Se anota lo que el post dice o implica de
   forma directa.

### Taxonomía de modelado

La anotación usa los 16 marcos finos, pero el modelo agrupa en 7 cabezas. El
mapeo canónico está en `src/keklab/annotation/taxonomy.py`:

| Cabeza | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `misogyny`, `transphobia`, `homophobia` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

Un post puede activar varias cabezas. La exportación CSV agrega
`coarse_labels` y una columna one-hot `coarse_<cabeza>` por cada una. El
protocolo de evaluación está en `docs/evaluation_protocol.md`.

`national_stereotypes` (generalizaciones sobre el carácter o las costumbres de
una nacionalidad) **no** forma parte de esta versión. Se documenta como clase
candidata para el próximo estudio en `docs/evaluation_protocol.md`; en este
piloto esos casos se anotan con `racism`, `ethnonationalism` o la etiqueta
específica que corresponda.

## Toxicidad (ordinal 0–3)

| Nivel | Definición |
|---|---|
| `0` | Neutral, sin toxicidad. |
| `1` | Insulto leve, hostilidad o edgy sin agresión grave. |
| `2` | Deshumanización explícita, slur, acoso u odio dirigido a un grupo. |
| `3` | Amenaza, incitación o celebración de violencia contra personas reales. |

- Es una escala **ordinal**, no de intervalo. Para acuerdo se usa kappa
  cuadrática ponderada.
- Para E0/E2 puede modelarse como 4 clases o colapsarse a binario
  (`0–1` vs `2–3`) como tarea secundaria.
- La toxicidad es independiente de los marcos: un post puede tener un marco
  político y toxicidad `0`, o no tener marco y toxicidad `2`.
- `violence_glorification` y toxicidad `3` pueden coincidir, pero **no son
  sinónimos**. El marco describe la postura del post frente a la violencia; la
  toxicidad mide la severidad del lenguaje. Un post puede ser tox `3` sin el
  marco (por ejemplo, una amenaza directa) y puede llevar el marco con tox `2`
  si celebra violencia sin dirigirla a personas reales.

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
  `accelerationism`, `racism`, `transphobia`, `homophobia`) para
  entrenamiento/calibración. No sirve para prevalencia.
- Se pueden conservar algunos posts vacíos o solo-imagen con
  `--include-empty N` para probar `none`.
- Para ROTLK se lee el dump comprimido en sitio, sin copiarlo ni extraerlo:

  ```bash
  export KEKLAB_ROTLK_DATASET=/run/media/flynnso/Archivos/pol_0616-1119_labeled.tar.zst
  keklab annotate sample --source rotlk --months 24 --random 20 --targeted 10 \
    --seed 13 --out data/samples/rotlk_pilot.jsonl
  ```

  `--dataset <archivo>` sobrescribe la variable de entorno y acepta `.ndjson`,
  `.ndjson.gz`, `.ndjson.zst` o `.tar.zst`. La alternativa
  `--parquet <canonical.parquet>` sigue disponible si ya existe un parquet
  canónico. `--limit-threads N` permite smoke tests sobre el corpus real.

### 2. Anotación

```bash
keklab annotate run \
  --input data/samples/pilot_fourplebs.jsonl \
  --annotator flynnso \
  --guideline v0.1 \
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

- **Greentext y citas:** el texto citado es contexto y no se usa para
  etiquetar; solo se anota el texto propio del post objetivo.
- **Posts vacíos o solo-imagen:** `none`; no se infiere un marco desde el
  contexto.
- **Truncamiento:** si falta el final y cambia el sentido, `unclear`.
- **Idioma:** si no se puede interpretar con seguridad, `unclear`; no traducir
  con herramientas externas durante la anotación.
- **Sarcasmo:** si el marco es recuperable por el texto del post, anotarlo; si
  no, `unclear`.
- **Spam/raid:** `meta_topic` si es cultura del tablero; `none` si es ruido sin
  contenido.
- **Noticias neutras:** `none`, aunque el tema sea político.

## Versionado

- `v0`: documento previo al piloto.
- `v0.1` (06-11-2026): `antifeminism` → `misogyny`, con definición ampliada
  para cubrir objetificación y hostilidad hacia las mujeres como clase. Los 52
  registros existentes se migraron; no hubo rejuicio.
- Enmienda text-only (06-11-2026, sin subir versión): la anotación pasa a usar
  **solo el texto del post objetivo**. Se eliminan el OP, los quotes, el asunto
  del hilo y el estrato de muestreo de las tareas, del prompt y de la UI de
  revisión. El vocabulario y los IDs se mantienen en `v0.1`/`prompt v1` por
  estabilidad, pero las anotaciones previas que dependían del contexto deben
  auditarse y reanotarse antes de usarse como oro de entrenamiento.
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
