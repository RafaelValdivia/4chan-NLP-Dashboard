# Journal PLN — Entrada 8 (03-11-2026)

## Contexto

La entrada 7 cerró con el piloto de ROTLK auditado y commiteado, pero el
vocabulario seguía teniendo 13 marcos. Al revisar el codebook aparecieron cinco
ejes de prejuicio que el esquema no podía representar sin forzarlos dentro de
`ethnonationalism` o `gender`: racismo, eugenesia, ableismo, transfobia y
homofobia. Esta entrada documenta esa expansión. No repite el muestreo, la
ventana ni la auditoría del piloto, que ya están en las entradas 6 y 7.

## Vocabulario nuevo

El vocabulario canónico pasa de 13 a **18 marcos**. El orden también es el
número que muestra la CLI interactiva:

| # | Slug | Definición breve |
|---|---|---|
| 1 | `conspiracy` | Plan o coordinación secreta. |
| 2 | `ethnonationalism` | Pureza o jerarquía nacional/étnica genérica. |
| 3 | `racism` | Prejuicio, slur, segregación o jerarquía racial/étnica. |
| 4 | `antisemitism` | Prejuicio contra judíos. |
| 5 | `islamophobia` | Prejuicio contra musulmanes o el islam. |
| 6 | `rusophobia` | Prejuicio contra rusos o Rusia. |
| 7 | `sinophobia` | Prejuicio contra chinos o China. |
| 8 | `eugenics` | Cría selectiva, jerarquía genética o esterilización. |
| 9 | `ableism` | Prejuicio o burla por discapacidad o enfermedad mental. |
| 10 | `gender` | Antifeminismo, roles de género, masculinidad, LGBTQ+ general. |
| 11 | `transphobia` | Prejuicio contra personas trans o negación de su identidad. |
| 12 | `homophobia` | Prejuicio contra personas gays o lesbianas. |
| 13 | `institutional_distrust` | Desconfianza no conspirativa hacia instituciones. |
| 14 | `violence_glorification` | Elogio o incitación a la violencia. |
| 15 | `accelerationism` | Deseo de acelerar el colapso o el conflicto. |
| 16 | `meta_topic` | Meta-discusión del tablero. |
| 17 | `none` | Ningún marco reconocible. |
| 18 | `unclear` | Contexto insuficiente o ambigüedad genuina. |

## Reglas de precedencia

La expansión obligó a explicitar qué etiqueta gana cuando varias podrían
aplicar:

- Las etiquetas con blanco específico (`antisemitism`, `islamophobia`,
  `rusophobia`, `sinophobia`, `transphobia`, `homophobia`, `ableism`)
  reemplazan a las genéricas `ethnonationalism`, `racism` y `gender` cuando
  cubren el mismo contenido.
- `racism` reemplaza a `ethnonationalism` cuando el eje es racial; queda
  reservada para prejuicio racial/étnico sin una etiqueta de grupo más
  específica.
- `transphobia` y `homophobia` reemplazan a `gender` cuando el post se dirige a
  personas trans o gays/lesbianas. `gender` queda para antifeminismo, roles de
  género, masculinidad y temas LGBTQ+ generales.
- `eugenics` y `ableism` **pueden coexistir** con `racism`,
  `ethnonationalism` o entre sí, porque describen un programa reproductivo o
  una jerarquía de capacidad que no se agota en el prejuicio racial.
- `none` y `unclear` siguen siendo exclusivos con todo y entre sí.
- Si un post contiene prejuicios distintos, se anotan ambos; la precedencia
  solo elimina la etiqueta genérica que la específica ya cubre.

## Búsqueda dirigida

Se agregaron términos semilla para los cinco marcos nuevos:

- `racism`: racism, racist, racial, segregation, white supremacy, white
  nationalist, white nationalism, miscegenation.
- `eugenics`: eugenics, eugenic, gene pool, dysgenic, selective breeding,
  sterilization/sterilisation, sterilize/sterilise.
- `ableism`: ableism, ableist, retarded, retard, disabled, disability,
  autistic, mongoloid.
- `transphobia`: transphobia, transphobic, tranny, transgender, transsexual,
  trans woman, trans women, troon.
- `homophobia`: homophobia, homophobic, faggot, fag, homosexual, gay, lesbian,
  sodomy, dyke.

Los términos se suman a los tres grupos existentes (`rusophobia`,
`sinophobia`, `accelerationism`), así que el muestreo dirigido ahora reparte su
cupo entre **8 marcos**. Un smoke test de 5,000 hilos pasó de ~3.6 s a ~5.8 s
por el costo de escanear más términos; sigue siendo despreciable frente a la
pasada completa.

## Cambios de código y pruebas

- `src/keklab/annotation/labels.py`: vocabulario, descripciones, términos
  dirigidos e índices actualizados.
- `tests/test_annotation_labels.py`: conteo 18, cobertura de descripciones,
  aceptación de los cinco slugs nuevos y validación de que los términos
  dirigidos usan marcos conocidos.
- `src/keklab/annotation/cli.py`: la sesión ahora imprime el menú de marcos al
  inicio. Con 13 marcos el menú se podía inferir; con 18 y números reasignados,
  no. Sin esto la CLI solo permitía usar `n`/`u`.
- `tests/test_annotation_cli.py`: verifica que el menú se emita y que incluya
  los marcos nuevos y el índice 18.

Los commits de código quedaron como:

```
c7db1cd feat: add racism, eugenics, ableism, transphobia and homophobia frames
9efaf2b fix: show the frame menu when an annotation session starts
```

La suite pasa de **86 a 87 pruebas** (la expansión por sí sola sumó 3; el menú
sumó 1).

## Documentación y estado del piloto

- `docs/annotation_guidelines.md`: tabla de 18 marcos, criterios por marco para
  los cinco nuevos y reglas de solapamiento reescritas.
- `docs/pipeline_draft.md`: conteo de marcos, lista de marcos dirigidos y
  conteo de pruebas actualizados.

El piloto de 30 posts (`data/samples/rotlk_pilot.jsonl`) **no se regeneró**:
fue muestreado antes de esta expansión. Sigue siendo válido para anotar los
marcos que aparezcan de forma natural, pero no sobre-muestrea los cinco marcos
nuevos. La prevalencia de esos marcos en la muestra aleatoria de 20 posts es,
por ahora, solo la que el azar haya producido. Si se necesita calibración
específica para ellos, habrá que generar una muestra dirigida nueva.

## Siguiente paso

Anotar el piloto con el vocabulario de 18 marcos. El menú se imprime al inicio
de la sesión y `?` sigue mostrando la ayuda de comandos. Después: self
test-retest del ~20% y revisión del codebook antes de congelar `v1`.
