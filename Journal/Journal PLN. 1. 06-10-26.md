## Fuente de datos

- **Histórico:** *Raiders of the Lost Kek* (~3.5 años de /pol/, 2016–2019), disponible en su totalidad. Formato semiestructurado: metadatos (identificadores, hilos, fechas) más texto libre con marcas propias del tablero.
- **Reciente:** API de 4plebs, con horizonte definido en los **últimos 24 meses**.
- Ambos períodos no son i.i.d.: existe deriva de vocabulario, formatos y tópicos. Esta observación condiciona el diseño experimental (véase E4).
- La escala del corpus histórico es del orden de millones de posts; la anotación manual, en el orden de cientos; la anotación asistida por LLMs, en el orden de miles.
## Restricciones del entorno de cómputo

- GPU GTX 1070 Ti (8 GB VRAM), sin acceso a API externa de LLM.
- Los modelos *encoder* (Laya, GLiNER, BERT/RoBERTa) son viables; el fine-tuning de un LLM con LoRA/QLoRA es factible pero costoso; la inferencia de LLM sobre millones de textos es inviable.
## Arquitectura considerada

Se contempla una arquitectura en capas que integra los tres núcleos temáticos de la asignatura:

| Módulo                                                         | Función en el pipeline                                              | Enfoque de decisión               |
| -------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------- |
| Lenguajes formales (regex, GLC)                                | saneamiento de marcas rígidas del tablero y validación de metadatos | teórico (lenguaje determinista)   |
| PLN clásico (TF-IDF/BoW, embeddings, LR/SVM)                   | clasificación de alto volumen a bajo costo                          | empírico (comparación controlada) |
| PLN con IA generativa (LLM local, fine-tuning, *tool calling*) | etiquetado asistido, modelos de referencia, chatbot, resúmenes      | empírico y de diseño              |

La coexistencia de modelos clásicos y generativos se justifica por el volumen: el LLM etiqueta y explica; los modelos de bajo costo procesan el corpus completo.

## Estrategia de etiquetado

Se adopta un esquema de referencia humana ("oro") y etiquetado asistido ("plata"):

1. Anotación humana de una muestra estratificada en el orden de cientos de posts (oro).
2. Competencia entre modelos candidatos a "maestro" clasificando el oro; se reportan métricas completas y se selecciona el mejor.
3. El maestro seleccionado etiqueta miles de posts (plata).
4. Los modelos tradicionales se validan sobre esa base.

## Competencia de maestros

- Laya (clasificación *zero-shot* tipada, ModernBERT)
- LLM local (~7B, prompting tipado)
- GLiClass

## Experimentos propuestos

| ID  | Pregunta                                                                        | Módulo               | Tipo de criterio |
| --- | ------------------------------------------------------------------------------- | -------------------- | ---------------- |
| E0  | ¿La limpieza con regex mejora la clasificación? (crudo vs saneado)              | formal               | empírico         |
| E1  | Selección de maestro: Laya vs LLM (vs GLiClass) contra oro; F1, kappa, latencia | generativo           | empírico         |
| E2  | Representación + clásico: TF-IDF+LR vs BoW+SVM vs embeddings, en plata→oro      | clásico              | empírico         |
| E3  | Clásicos vs Laya vs RoBERTa fine-tuneado vs LLM: F1 y costo por 10k posts       | clásico + generativo | empírico         |
| E4  | Deriva temporal: modelo histórico sobre muestra reciente anotada                | transversal          | empírico         |
| E5  | Evaluación del chatbot: suite de ~25 preguntas (tool calling y gráficos)        | generativo           | empírico         |
| E6  | Extracción de entidades con GLiNER por marco y período                          | generativo           | teórico/empírico |

## Producto analítico

- **Dashboard** con vistas comparativas entre períodos (distribución de marcos, niveles de toxicidad, series temporales con hitos externos). La tecnología de UI está **pendiente**.
- **Chatbot con *tool calling*** sobre LLM local. Herramientas consideradas: `consultar`, `graficar`, `clasificar`, `resumir`, `extraer_entidades`.

