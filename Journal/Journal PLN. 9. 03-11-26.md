# Journal PLN — Entrada 9 (03-11-2026)

## Contexto

La entrada 8 agregó cinco marcos de prejuicio, pero dejó `gender` como etiqueta
genérica para roles de género, masculinidad, antifeminismo y temas LGBTQ+. Al
revisar el codebook quedó claro que ese cajón era demasiado amplio: mezclaba
antifeminismo con homosexualidad y transfobia, y hacía que las reglas de
precedencia dependieran de una etiqueta paraguas. En esta entrada se reemplaza
`gender` por `antifeminism` y se revisa si el vocabulario resultante es
demasiado grande para el tamaño de muestra disponible. No repite la expansión
de la entrada 8; solo registra el cambio y el chequeo de presupuesto de
etiquetas.

## Reemplazo de `gender` por `antifeminism`

El índice 10 pasa de `gender` a `antifeminism`. La definición nueva es:

> Hostilidad u oposición al feminismo, los derechos de las mujeres o la
> igualdad de género.

Incluye inferioridad femenina, oposición al sufragio o al trabajo, slurs como
“femoid”, y privilegio femenino o misandria usados como ataque. Excluye
discusión neutral de roles de género y crítica a una feminista por sus actos
sin atacar al feminismo.

El cambio también corrige la precedencia:

- `transphobia` y `homophobia` dejan de reemplazar a `gender`; ahora son ejes
  independientes de `antifeminism` y pueden coexistir si el post ataca ambos
  frentes.
- `antifeminism` no reemplaza a `racism` ni a `ethnonationalism`; el
  antifeminismo no es un eje racial.
- La lista de etiquetas específicas que reemplazan a las genéricas queda en
  `ethnonationalism` y `racism`, sin `gender`.

Se agregaron términos dirigidos para el marco nuevo: `feminism`, `feminist`,
`femoid`, `femoids`, `suffragette`, `misandry`, `women's rights` y
`female privilege`. Con esto el muestreo dirigido cubre 9 marcos.

El cambio de código quedó en:

```
5d1b819 refactor: replace the gender frame with antifeminism
```

La suite siguió en **87 pruebas**: el reemplazo renombró casos existentes en
lugar de agregar pruebas nuevas.

## Chequeo de infradeterminación

La pregunta era si 18 marcos no dejan al modelo sin suficientes restricciones.
El chequeo da una respuesta matizada: el codebook fino es defendible para
anotar, pero no para entrenar 18 cabezas con el piloto actual.

- Con 16 marcos no exclusivos más `none` y `unclear`, el espacio posible es
  `2^16 + 2 = 65,538` conjuntos de etiquetas. El piloto de 30 posts observa
  como máximo 30 de ellos.
- Para un marco con prevalencia del 5%, se esperan 1.5 positivos en 30 posts y
  la probabilidad de ver al menos 5 es de solo 1.6%. Para esperar 10 positivos
  harían falta ~200 posts.
- El self test-retest del 20% son 6 posts. Un kappa por marco sobre 6
  decisiones no es estimable para marcos raros.
- 18 cabezas binarias sobre un encoder de 768 dimensiones implican ~13,800
  parámetros de salida, entrenados con 30 ejemplos.
- En el piloto, los términos semilla aparecen 2 veces para `racism`, 1 para
  `ableism` y 0 para `eugenics`, `transphobia`, `homophobia` y `antifeminism`.
  Es un proxy de candidatos, no prevalencia anotada, pero confirma que los
  marcos nuevos tendrán muy poco soporte.

Conclusión: 30 posts no infradeterminan la **anotación**, porque el codebook es
una decisión humana y no un modelo; sí infradeterminan el **aprendizaje
supervisado** de 18 etiquetas.

## Recomendación

Separar la taxonomía de anotación de la de modelado. La anotación conserva los
18 marcos; el modelo usa 8 cabezas agrupadas:

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

Reglas propuestas:

1. Un marco fino solo entra a E0/E2 con **≥30 positivos en train** y **≥5 en
   test**; si no, se reporta solo descriptivamente.
2. La muestra aleatoria estima prevalencia; la dirigida solo entrena/calibra.
3. Para conservar marcos finos, el piloto debe crecer a 100–150 posts
   aleatorios y la muestra dirigida a 200–300 candidatos por marco raro.
4. La alternativa jerárquica es una cabeza gruesa más una cabeza hija solo para
   los marcos que superen el umbral.

Esta recomendación queda documentada en `docs/pipeline_draft.md`, pero **no se
implementó** todavía: no hay módulo de modelado y la decisión de taxonomía
gruesa corresponde al siguiente paso.

## Estado de git

- `5d1b819`: código y tests del reemplazo `gender` → `antifeminism`.
- Este commit: `docs/annotation_guidelines.md`, `docs/pipeline_draft.md` y esta
  entrada.
- Nada se empujó a `origin`.

## Siguiente paso

Anotar el piloto con `antifeminism` en lugar de `gender`. Antes de E0/E2, elegir
si se adopta el mapeo grueso de 8 cabezas o una variante jerárquica.
