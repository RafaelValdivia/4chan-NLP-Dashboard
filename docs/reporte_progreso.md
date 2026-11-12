---
title: "Reporte de progreso — Proyecto 4chan-NLP-Dashboard"
subtitle: "Avance hacia la analítica de narrativas y el chatbot"
date: "11-11-2026"
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
fase actual es la plataforma sobre la que se construirán esos tres productos:
el plan de etiquetado plata y de comparación de modelos ya está definido.

# Decisiones tomadas

## Datos y comparabilidad

| Decisión | Valor adoptado |
|---|---|
| Fuente histórica | ROTLK `/pol/` 2016–2019; lectura en sitio del `.tar.zst`, sin copiarlo ni extraerlo. |
| Fuente reciente | API de 4plebs, últimos 24 meses, con el mismo esquema y codebook. |
| Períodos | 2016-2019 vs 2020 en adelante, para comparar con los mismos clasificadores. |
| Unidad de análisis | Post; agrupación por hilo. Split por `thread_id` para evitar fuga entre OP y respuestas. |
| Partición | 60/20/20, semilla 13; test congelado y hasheado antes de entrenar. |
| Eventos externos | Pizzagate, QAnon y Christchurch como hitos de comparación, no como etiquetas del modelo. |

## Anotación y etiquetas

| Decisión | Valor adoptado |
|---|---|
| Oro humano | 200 posts: 190 aleatorios + 10 dirigidos; los dirigidos solo entrenan/calibran. |
| Interfaz | CLI de terminal; sin interfaz web ni herramienta externa. |
| Unidad de clasificación | Solo el post objetivo: sin OP, quotes, `subject` ni estrato de muestreo. Si no se entiende, `unclear`. |
| Plata | 5.000 posts aleatorios, semilla 17, etiquetados por `Qwen3-8B-Q4_K_M`; se confía en la plata sin revisión humana. |
| Rol del oro | Diagnóstico externo del maestro; no entrena, corrige ni bloquea la plata. |

## Taxonomía de clasificación

Reglas que gobiernan la taxonomía:

| Regla | Decisión |
|---|---|
| Estructura | 16 marcos finos binarios multi-label; 7 cabezas gruesas derivadas. |
| Toxicidad | Escala ordinal `0–3`, independiente de los marcos. |
| `none` / `unclear` | Exclusivos con cualquier otro marco y entre sí. |
| Prejuicio específico | Se añadió `rusophobia` y `sinophobia` por prevalencia en el corpus |
| Género y sexualidad | Se optó por mantener`transphobia`, `homophobia` y `misogyny` como ejes independientes. |

Cada marco y la toxicidad son ejes separados. Durante la clasificación se
observó correlación alta entre toxicidad 3 y glorificación de la violencia. Se
optó por mantener ambos aunque se superpongan, ya que remiten a categorías
semánticas distintas.

| # | Marco | Definición |
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

### Toxicidad

| Nivel | Definición |
|---|---|
| `0` | Neutral, sin toxicidad. |
| `1` | Insulto leve, hostilidad o edgy sin agresión grave. |
| `2` | Deshumanización explícita, slur, acoso u odio dirigido a un grupo. |
| `3` | Amenaza, incitación o celebración de violencia contra personas reales. |

## Evaluación y modelado

| Decisión | Valor adoptado |
|---|---|
| Expresiones regulares | El uso de regex es necesario para limpiar los posts de código html, citas a otros posts y otros artefactos que obstaculizan el procesamiento de lenguaje |
| Modelos comparados | TF-IDF + LR, BoW + SVM, embeddings + lineal, BERT/RoBERTa, Laya, GLiClass y GLiNER. |
| Métricas | P/R/F1 por clase, macro y micro; bootstrap por hilo. Toxicidad: kappa cuadrática, MAE y matriz de confusión. |
| Límite de la plata | La tabla principal mide imitación del maestro, no verdad; el oro de 200 posts es la referencia externa. |

## Producto y alcance

| Decisión | Valor adoptado |
|---|---|
| Producto | Aplicación de analítica para científicos sociales y analistas políticos. |
| Chatbot | Componente más importante; _tool calling_ sobre el backend analítico (`consultar`, `graficar`, `clasificar`, `resumir`, `extraer_entidades`). |
| Dashboard | Exploración de marcos, toxicidad y series temporales con hitos históricos. |
| Comparación temporal | Histórico vs reciente con los mismos clasificadores y ventanas comparables. |
| Extracción estructurada | Tópicos y entidades con Laya/Gleaner/GLiNER, integrados al dashboard y al chatbot. |
| Orden de construcción | Datos → clasificador → comparación temporal → backend → dashboard → chatbot. |

# Resumen de avance

| Componente | Estado | Foco inmediato |
|---|---|---|
| Corpus histórico ROTLK | Listo | L0 en disco externo: 134,5 M posts en Parquet mensual. |
| Corpus reciente 4plebs | Parcial | Descargar y validar la ventana de 24 meses. |
| Anotación humana | Listo (piloto) | Ampliar si se busca el modelo completo. |
| Clasificadores de marco y toxicidad | Iniciado | Plata de 5.000 posts y evaluación E0/E2. |
| Comparación temporal | No iniciado | Datos recientes + modelo + línea de eventos. |
| Backend analítico | Listo | `keklab.analytics`: filtros, cuotas, series, procedencia. |
| Dashboard | MVP listo | 7 secciones; faltan las cuotas de marcos hasta que haya L1. |
| Chatbot | Iniciado | 5 herramientas sobre el backend; falta el LLM que planifique. |
| Extracción estructurada | No iniciado | Integración de Laya/Gleaner/GLiNER. |
En una frase: **la infraestructura, el corpus, el oro, el backend y el panel
ya existen; falta el modelo aplicado al corpus (L1) y la ventana reciente.**

# Obstáculos

| Obstáculo | Efecto | Cómo se aborda |
|---|---|---|
| Escala y acceso a ROTLK | El dump es demasiado grande para copiarlo. | Lectura en sitio y muestreo por streaming; resuelto. |
| Datos recientes incompletos | Sin 4plebs reciente no hay comparación temporal. | Descargar y validar la ventana de 24 meses. |
| Marcos raros y pocos positivos | Un modelo de 16 marcos no se aprende con 200 posts. | Muestra plata de 5.000, muestreo dirigido y reporte descriptivo. |
| Sesgo del LLM en la plata | La plata hereda errores y sesgos del maestro. | No llamarla oro; diagnóstico externo con el oro de 200. |
| Un solo anotador humano | No hay acuerdo inter-anotador. | Self test-retest pendiente y limitación documentada. |
| Cómputo limitado | GPU de 8 GB y sin API externa para millones de textos. | Modelos clásicos/encoders a escala; LLM local para etiquetado y chatbot. |
| Producto sin backend | Dashboard y chatbot dependen de consultas y series. | Resuelto: `keklab.analytics` es la fuente única. |

# Hoja de ruta

| Fase | Objetivo | Entregable |
|---|---|---|
| 0. Base (hecha) | Infraestructura, corpus histórico y oro. | Pipeline, 200 posts anotados, protocolo y tests. |
| 1. Datos recientes | Completar la ventana de 24 meses de 4plebs. | Corpus reciente auditado y comparable. |
| 2. Plata y primer clasificador | Etiquetar 5.000 posts con el LLM y entrenar el _baseline_. | Plata confiada, E0/E2 y métricas por cabeza. |
| 3. Escalado | Comparar clásicos, BERT, Laya, GLiClass y GLiNER. | Modelo aplicable a volúmenes grandes. |
| 4. Comparación temporal | Aplicar el modelo a histórico y reciente. | E4 con series y eventos. |
| 5. Backend analítico (hecha) | Consultas, agregados y series para la UI. | `keklab.analytics` + CLI. |
| 6. Dashboard (MVP hecha) | Exploración visual para analistas. | 7 secciones con volumen; cuotas cuando haya L1. |
| 7. Chatbot (en curso) | _Tool calling_ sobre el backend. | 5 herramientas; falta el LLM que enrute y la suite E5. |
| 8. Extracción estructurada | Tópicos y entidades por marco/período. | E6 integrado al dashboard/chatbot. |

# Conclusión

La base técnica, el corpus histórico, el esquema de anotación, el backend
analítico y el panel están resueltos. Lo que falta es **conectar el modelo con
el corpus**: hasta que exista L1, las cuotas de marcos y toxicidad del panel
son volumen, no prevalencia. La ruta crítica queda así: datos recientes →
clasificador → L1 → comparación temporal, con el dashboard y el chatbot ya
listos para mostrar lo que se les dé. La única decisión de alcance que sigue
abierta es si la comparación histórica contra reciente entra antes o después
de la extracción estructurada de tópicos y entidades.
