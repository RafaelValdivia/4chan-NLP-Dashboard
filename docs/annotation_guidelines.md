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
| 2 | `ethnonationalism` | Pureza, superioridad o jerarquía nacional/étnica genérica **no** cubierta por una etiqueta más específica. |
| 3 | `racism` | Prejuicio, slur, segregación o jerarquía racial/étnica **no** cubierta por una etiqueta de grupo específica. |
| 4 | `antisemitism` | Hostilidad, tropos o prejuicio contra judíos. |
| 5 | `islamophobia` | Hostilidad o prejuicio contra musulmanes o el islam. |
| 6 | `rusophobia` | Hostilidad o prejuicio contra rusos o Rusia. |
| 7 | `sinophobia` | Hostilidad o prejuicio contra chinos o China. |
| 8 | `eugenics` | Defensa o aprobación de cría selectiva, jerarquía genética, esterilización o “mejorar” el acervo genético. |
| 9 | `ableism` | Prejuicio, burla o discriminación contra personas con discapacidad o enfermedad mental. |
| 10 | `antifeminism` | Hostilidad u oposición al feminismo, los derechos de las mujeres o la igualdad de género. |
| 11 | `transphobia` | Hostilidad, burla o prejuicio contra personas trans o negación de su identidad. |
| 12 | `homophobia` | Hostilidad, burla o prejuicio contra personas gays o lesbianas. |
| 13 | `institutional_distrust` | Desconfianza generalizada hacia Estado, medios, academia o elecciones, sin afirmación conspirativa explícita. |
| 14 | `violence_glorification` | Elogio, celebración o incitación a la violencia (no mera discusión o noticia). |
| 15 | `accelerationism` | Deseo de acelerar el colapso, el conflicto o la desestabilización. |
| 16 | `meta_topic` | Meta-discusión del tablero, moderación, raids, cultura online. |
| 17 | `none` | Ningún marco reconocible. |
| 18 | `unclear` | Contexto insuficiente, truncamiento o ambigüedad genuina. |

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

#### `eugenics`

- **Incluye:** defensa o aprobación de cría selectiva, esterilización,
  jerarquía genética, “gene pool”, disgenia, mejorar la “raza” o la población
  mediante selección reproductiva.
- **Excluye:** genética médica o discusión histórica neutral sin aprobación;
  el simple uso de “evolución” sin programa reproductivo.
- **Positivo:** “Hay que esterilizar a los criminales para mejorar el acervo
  genético.”
- **Negativo:** “El documental describe las políticas eugenésicas del siglo XX.”

#### `ableism`

- **Incluye:** insultos o burlas por discapacidad, enfermedad mental o
  neurodivergencia; exclusión, inferioridad o eliminación de personas
  discapacitadas; uso de “retrasado” como insulto.
- **Excluye:** mención neutral de una discapacidad; crítica a una persona sin
  apuntar a su discapacidad.
- **Positivo:** “Los autistas no deberían tener hijos.”
- **Negativo:** “Tiene una discapacidad y necesita apoyo.”

#### `antifeminism`

- **Incluye:** hostilidad u oposición al feminismo o a los derechos de las
  mujeres; afirmaciones de inferioridad femenina, oposición al sufragio, al
  trabajo o a la igualdad; slurs como “femoid”; teorías de privilegio femenino
  o misandria usadas como ataque.
- **Excluye:** discusión neutral sobre roles de género o una política concreta
  sin hostilidad; crítica a una feminista por sus actos sin apuntar al
  feminismo. `transphobia` y `homophobia` son ejes distintos y pueden
  coexistir si ambos son centrales.
- **Positivo:** “Las mujeres no deberían votar; el feminismo arruinó la
  sociedad.”
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

- **Incluye:** truncamiento, referencias que no se pueden resolver ni con el
  contexto, sarcasmo genuinamente ambiguo, texto en otro idioma sin traducir.
- **Regla:** exclusivo con todos los demás marcos y con `none`.

### Reglas de solapamiento

1. Las etiquetas de prejuicio con blanco específico (`antisemitism`,
   `islamophobia`, `rusophobia`, `sinophobia`, `transphobia`, `homophobia`,
   `ableism`) **reemplazan** a las genéricas `ethnonationalism` y `racism`
   cuando la etiqueta específica cubre el mismo contenido. Si el post
   contiene prejuicios distintos (por ejemplo, racismo y ableismo), se anotan
   ambos.
2. `racism` se usa para prejuicio racial/étnico sin una etiqueta más específica;
   reemplaza a `ethnonationalism` cuando el eje es racial.
3. `ethnonationalism` se reserva para encuadres nacionales/étnicos genéricos
   sin grupo nombrado ni eje racial específico.
4. `eugenics` describe una ideología de mejora genética y **puede coexistir**
   con `racism`, `ableism` o `ethnonationalism` si ambos son centrales.
5. `ableism` **puede coexistir** con `eugenics` (por ejemplo, esterilización de
   personas discapacitadas).
6. `transphobia` y `homophobia` son ejes independientes de `antifeminism`. Un
   post puede ser ambos si ataca el feminismo y a personas trans o gays; no se
   usa `antifeminism` para contenido exclusivamente trans/homofóbico.
7. `conspiracy` exige un plan explícito. `institutional_distrust` es la
   etiqueta más amplia y no conspirativa. Pueden coexistir solo si ambos son
   centrales.
8. `violence_glorification` describe la postura frente a la violencia;
   `accelerationism` describe el deseo de acelerar el colapso. Pueden coexistir.
9. `none` y `unclear` son excluyentes con cualquier otro marco y entre sí.
10. Si hay duda entre `none` y un marco: si el marco está claramente presente,
    anotarlo; si no, `none`. Si no se puede decidir por falta de contexto,
    `unclear`.
11. No se anota ideología inferida. Se anota lo que el post dice o implica de
    forma directa.

### Taxonomía de modelado

La anotación usa los 18 marcos finos, pero el modelo agrupa en 8 cabezas. El
mapeo canónico está en `src/keklab/annotation/taxonomy.py`:

| Cabeza | Marcos finos |
|---|---|
| `conspiracy` | `conspiracy` |
| `ethnoracial_prejudice` | `ethnonationalism`, `racism`, `antisemitism`, `islamophobia`, `rusophobia`, `sinophobia` |
| `gender_sexuality_prejudice` | `antifeminism`, `transphobia`, `homophobia` |
| `eugenics_ableism` | `eugenics`, `ableism` |
| `institutional_distrust` | `institutional_distrust` |
| `violence_acceleration` | `violence_glorification`, `accelerationism` |
| `meta_topic` | `meta_topic` |
| `no_frame` | `none`, `unclear` |

Un post puede activar varias cabezas. La exportación CSV agrega
`coarse_labels` y una columna one-hot `coarse_<cabeza>` por cada una. El
protocolo de evaluación está en `docs/evaluation_protocol.md`.

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
  `accelerationism`, `racism`, `eugenics`, `ableism`, `transphobia`,
  `homophobia`) para entrenamiento/calibración. No sirve para prevalencia.
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
