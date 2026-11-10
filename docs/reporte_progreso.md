---
title: "Reporte de progreso — Proyecto 4chan-NLP-Dashboard"
subtitle: "Avance hacia la analítica de narrativas y el chatbot"
date: "10-11-2026"
---

# Reporte de progreso

**Objetivo original.** Entrenar clasificadores de marco narrativo y toxicidad
sobre _Raiders of the Lost Kek_ (4chan `/pol/`, 2016–2019), aplicarlos a datos
recientes obtenidos vía 4plebs y comparar la evolución del tablero en relación
con eventos externos como Pizzagate, la emergencia de QAnon y Christchurch. El
producto es una aplicación de analítica para científicos sociales y analistas
políticos, con un **chatbot inteligente** como componente más importante.

**Estado general.** El proyecto completó la base de datos, limpieza y anotación
humana. Todavía **no hay clasificadores entrenados, dashboard ni chatbot**. La
fase actual es la plataforma sobre la que se construirán esos tres productos.

## 1. Qué debe entregar el proyecto

| Componente | Papel en el objetivo |
|---|---|
| Corpus histórico y reciente | Base comparable para medir evolución. |
| Clasificadores de marco y toxicidad | Convierten texto en narrativas y niveles de toxicidad. |
| Comparación temporal | Responde cómo cambió `/pol/` entre 2016–2019 y el presente. |
| Dashboard analítico | Permite explorar distribuciones, series y eventos. |
| Chatbot con _tool calling_ | Interfaz principal para analistas; debe consultar, graficar y explicar. |
| Extracción estructurada | Tópicos y entidades por marco/período; apoya dashboard y chatbot. |

```{=latex}
\newpage
```

## 2. Resumen de avance

| Componente | Estado | Foco inmediato |
|---|---|---|
| Corpus histórico ROTLK | Listo | — |
| Corpus reciente 4plebs | Parcial | Descargar y validar la ventana de 24 meses. |
| Anotación humana | Listo (piloto) | Ampliar si se busca el modelo completo. |
| Clasificadores de marco y toxicidad | No iniciado | Baseline y evaluación E0/E2. |
| Comparación temporal | No iniciado | Datos recientes + modelo + línea de eventos. |
| Dashboard | No iniciado | Backend analítico y UI. |
| Chatbot | No iniciado | Tool calling y suite E5. |
| Extracción estructurada | No iniciado | Integración de Laya/Gleaner/GLiNER. |

En una frase: **la infraestructura y el oro están listos; el producto analítico
y el chatbot todavía no.**

## 3. Progreso por componente

### 3.1 Datos históricos y recientes

El corpus histórico se lee directamente del dump de ROTLK, sin copiarlo ni
extraerlo: **3,397,911 hilos y 134,529,233 posts**. Sobre ese corpus se construyó
una muestra de **200 posts y 200 hilos** de `/pol/`, ventana
`2017-11-11T10:15:36Z` → `2019-11-01T10:15:36Z`, con **190 aleatorios + 10
dirigidos** para enriquecer marcos poco frecuentes.

La capa de ingesta incluye limpieza de marcas de 4chan, normalización Unicode,
extracción de citas, deduplicación y features de hilo. El cliente de 4plebs ya
pagina, cachea, reintenta y resuelve el bloqueo TLS con `curl`; el _smoke test_
de índice, hilo y búsqueda funcionó. Sin embargo, **la tanda reciente de 24
meses todavía no se descargó ni se validó a escala**.

### 3.2 Anotación humana

El piloto tiene **200 registros de oro**. La composición es 52 anotaciones
originales más 148 propuestas de un agente de lenguaje revisadas por una
persona: **124 aceptadas, 24 editadas, 0 rechazadas y 0 saltadas**. El acuerdo
propuesta-final fue Jaccard 0.898; la toxicidad coincidió exactamente en 94.6 %
de los casos (MAE 0.054).

La taxonomía quedó en **16 marcos finos y 7 cabezas gruesas**, con toxicidad
ordinal `0–3`, reglas de exclusividad para `none`/`unclear` y definiciones para
prejuicios específicos. El codebook, el protocolo de evaluación y la partición
120/40/40 por hilo están documentados y la suite pasa con **136 pruebas**.

Este es el activo más maduro del proyecto, pero también el cuello de botella:
200 posts alcanzan para empezar, no para cubrir todos los marcos raros.

### 3.3 Clasificadores de marco y toxicidad

**No se entrenó ningún modelo todavía.** Tampoco se ejecutaron E0 (crudo vs
saneado) ni E2 (TF-IDF + regresión logística, BoW + SVM, embeddings). El piloto
muestra que el tamaño actual permite un primer _baseline_ en las cabezas con más
soporte, pero no el modelo completo de 16 marcos. La ruta prevista es:

1. entrenar un _baseline_ sobre las etiquetas con soporte suficiente;
2. usar el LLM como pre-anotador para generar etiquetas “plata” a escala;
3. validar los modelos clásicos contra el oro.

El flujo de pre-anotación con IA ya está listo y tiene un handoff para un agente
relevo, incluido el prompt versionado. Eso permite escalar el etiquetado sin
llamar a una API desde `keklab`.

### 3.4 Comparación temporal

**No iniciada.** Para responder a Pizzagate, QAnon y Christchurch hacen falta
tres piezas que todavía no están juntas:

- la tanda reciente de 4plebs, con el mismo esquema y la misma limpieza;
- un clasificador estable aplicado a ambos períodos;
- una línea de tiempo de eventos externos y ventanas comparables.

La infraestructura de `period` (`hist_2016_2019` vs `recent_2020_plus`) ya
existe; falta producir los datos y el modelo.

### 3.5 Dashboard analítico

**No iniciado.** Solo están definidos los servicios compartidos que deberían
alimentar la UI. El dashboard debe mostrar distribución de marcos, niveles de
toxicidad, series temporales con hitos y comparación histórica vs reciente.
La tecnología de UI sigue pendiente de decisión.

### 3.6 Chatbot

**No iniciado, y es la parte más importante del proyecto.** Las herramientas
objetivo están definidas: `consultar`, `graficar`, `clasificar`, `resumir` y
`extraer_entidades`. El chatbot depende de que existan:

1. corpus reciente;
2. clasificadores aplicables;
3. backend analítico con consultas y series;
4. suite de evaluación E5 (~25 preguntas con _tool calling_ y gráficos).

Sin esas piezas, un chatbot sería una interfaz sin datos confiables detrás.

### 3.7 Extracción estructurada

**No iniciada.** El plan original incluye tópicos y entidades por marco y
período, con Laya y Gleaner/GLiNER como modelos candidatos. Esto alimenta tanto
el dashboard como el chatbot (por ejemplo, “mostrame entidades y narrativas
alrededor de Christchurch”). Todavía no hay integración ni evaluación.

## 4. Obstáculos

| Obstáculo | Efecto | Cómo se aborda |
|---|---|---|
| Escala y acceso a ROTLK | El dump es demasiado grande para copiarlo. | Lectura en sitio y muestreo por streaming; ya resuelto. |
| Datos recientes incompletos | Sin 4plebs reciente no hay comparación temporal. | Ejecutar y validar la ventana de 24 meses. |
| Marcos raros y pocos positivos | Un modelo de 16 marcos no se aprende con 200 posts. | Ampliar oro, muestreo dirigido y etiquetas plata. |
| Cómputo limitado | GPU de 8 GB y sin API externa de LLM para millones de textos. | Encoders y modelos clásicos para volumen; LLM solo para etiquetado y chatbot. |
| Un solo anotador | No hay acuerdo inter-anotador. | Self test-retest pendiente y limitación documentada. |
| Producto aún sin backend | Dashboard y chatbot no pueden construirse antes de las consultas. | Priorizar corpus → clasificador → backend analítico. |
| Alineación de eventos | Pizzagate, QAnon y Christchurch no coinciden con ventanas triviales. | Definir línea de tiempo y ventanas antes de comparar. |

## 5. Hoja de ruta

| Fase | Objetivo | Entregable |
|---|---|---|
| 0. Base (hecha) | Infraestructura, corpus histórico y oro. | Pipeline, 200 posts anotados, protocolo y tests. |
| 1. Datos recientes | Completar la ventana de 24 meses de 4plebs. | Corpus reciente auditado y comparable. |
| 2. Primer clasificador | Entrenar y evaluar un _baseline_ de marcos y toxicidad. | E0/E2 con métricas por cabeza. |
| 3. Escalado | Generar etiquetas plata con LLM y ampliar el entrenamiento. | Modelo aplicable a volúmenes grandes. |
| 4. Comparación temporal | Aplicar el modelo a histórico y reciente. | E4 con series y eventos. |
| 5. Backend analítico | Consultas, agregados y series para la UI. | API/servicios compartidos. |
| 6. Dashboard | Exploración visual para analistas. | MVP con distribución, toxicidad y tiempo. |
| 7. Chatbot | _Tool calling_ sobre el backend. | Chatbot + suite E5. |
| 8. Extracción estructurada | Tópicos y entidades por marco/período. | E6 integrado al dashboard/chatbot. |

**Prioridad inmediata:** cerrar la tanda reciente de 4plebs, entrenar el primer
_baseline_ y ejecutar el self test-retest. Sin esas tres piezas no se puede
empezar la comparación temporal ni darle datos confiables al chatbot.

## 6. Conclusión

El proyecto tiene una base sólida: corpus histórico, limpieza, anotación humana,
protocolo y flujo de pre-anotación. Pero el avance debe medirse contra el
producto original, y ese producto todavía no existe: faltan los clasificadores,
la comparación temporal, el dashboard y el chatbot.

El riesgo principal ya no es de infraestructura sino de **alcance y secuencia**.
La ruta crítica es: datos recientes → primer clasificador → comparación
temporal → backend analítico → dashboard → chatbot. El chatbot es la meta
principal y debe orientar las prioridades; por eso conviene no seguir invirtiendo
en detalles internos del codebook antes de tener un modelo que produzca las
series que el chatbot necesita explicar.
