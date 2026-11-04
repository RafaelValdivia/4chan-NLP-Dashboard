# Journal PLN — Entrada 10 (03-11-2026)

## Contexto

La entrada 9 concluyó que 30 posts no alcanzan para entrenar 18 marcos y dejó
una recomendación tentativa de crecer a 100–150 posts. Esa cifra era demasiado
optimista: no salía de un cálculo de soporte por etiqueta. Esta entrada
determina el tamaño muestral con una fórmula explícita y corrige la
recomendación anterior. No repite el cambio `gender` → `antifeminism` ni el
diagnóstico de infradeterminación, que ya están en la entrada 9.

## Criterio

Para modelar un marco con `K` positivos y prevalencia `p`, el número de posts
aleatorios necesarios es:

```
n = K / p
```

Los posts adicionales sobre los 30 actuales son `n - 30`. Se usan dos umbrales:

- `K=10`: mínimo para evaluar un marco con cierta estabilidad.
- `K=50`: mínimo razonable para entrenar una cabeza binaria.
- `K=30` y `K=100` quedan como escenarios intermedios y conservadores.

La prevalencia `p` es la del marco más raro que se quiera modelar. Como
todavía no hay anotaciones, `p` es un supuesto; después de la primera tanda se
reemplaza por la prevalencia observada.

## Resultado

Cada celda es `n total (posts adicionales sobre 30)`:

| `p` del marco más raro | K=10 | K=30 | K=50 | K=100 |
|---:|---:|---:|---:|---:|
| 1% | 1,000 (970) | 3,000 (2,970) | 5,000 (4,970) | 10,000 (9,970) |
| 2% | 500 (470) | 1,500 (1,470) | 2,500 (2,470) | 5,000 (4,970) |
| 5% | 200 (170) | 600 (570) | 1,000 (970) | 2,000 (1,970) |
| 10% | 100 (70) | 300 (270) | 500 (470) | 1,000 (970) |
| 20% | 50 (20) | 150 (120) | 250 (220) | 500 (470) |

### Esquema grueso de 8 cabezas

Si la cabeza más rara tiene ~5–10% de prevalencia:

- **1,000 posts aleatorios** (970 más) dan ~50 positivos a 5% y ~100 a 10%.
- 200 posts (170 más) solo alcanzan para estimar prevalencia de forma
  descriptiva, no para entrenar.

### Esquema fino de 18 marcos

Si el marco más raro tiene ~1–2%:

- **2,500–5,000 posts aleatorios** (2,470–4,970 más) para 50 positivos.
- Con 10 positivos, el mínimo de evaluación, siguen haciendo falta 470–970
  posts.

Ese volumen no es viable con anotación humana únicamente. Las alternativas son
muestreo dirigido por marco raro o quedarse con el esquema grueso para el
modelo y usar los marcos finos solo de forma descriptiva.

## Procedimiento recomendado

1. Anotar 200 posts aleatorios (170 más).
2. Calcular `p_hat` por marco o cabeza.
3. Recalcular `n = K / p_hat`.
4. Seguir en tandas de 100–200 hasta que cada marco modelado llegue a `K`.
5. Si un marco no llega a 5 positivos tras 1,000 posts, sacarlo del modelo y
   reportarlo solo descriptivamente.

Para el acuerdo, el test-retest plano del 20% no alcanza: con 1,000 posts son
200 pares y una cabeza del 5% tendría ~10 positivos. Conviene un **retest
estratificado**: todos los positivos de marcos raros más una muestra aleatoria
de negativos, hasta ≥20 pares por marco modelado. Eso desacopla el tamaño de la
muestra de prevalencia del tamaño de la muestra de acuerdo.

## Corrección de la entrada 9

La entrada 9 recomendaba crecer a 100–150 posts aleatorios para conservar
marcos finos. El cálculo de esta entrada muestra que esa cifra solo sirve para
una estimación descriptiva gruesa; para 50 positivos de un marco al 1–2% hacen
falta 2,500–5,000 posts. La recomendación operativa queda:

- **Modelo de 8 cabezas:** 1,000 posts aleatorios (970 más).
- **Modelo fino de 18 marcos:** 2,500–5,000 posts aleatorios, o muestreo
  dirigido por marco raro.

## Estado de git

- Esta entrada solo modifica `docs/pipeline_draft.md` y el journal; no hay
  cambios de código.
- La suite sigue en **87 pruebas**.
- Nada se empujó a `origin`.

## Siguiente paso

Anotar la primera tanda de 200 posts aleatorios para reemplazar los supuestos
de prevalencia por datos observados y decidir si el modelo queda en 8 cabezas o
si se intenta el esquema fino con muestreo dirigido.
