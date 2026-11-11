# Journal PLN — Entrada 18 (11-11-2026)

## Contexto

La entrada 17 dejó pre-registrado el plan de clasificación plata: 5.000 posts
de ROTLK etiquetados por `Qwen3-8B-Q4_K_M`, sin revisión humana, usando el oro
de 200 solo como diagnóstico externo. Esta entrada implementa la infraestructura
necesaria para ejecutar ese plan y deja el repositorio listo para recibir los
GGUF. No se corrió el maestro: los modelos y el dump no están en esta máquina.

También se cerró el reporte de progreso alrededor de los objetivos originales
y de las decisiones que condicionan el producto: datos, anotación, taxonomía,
evaluación y orden de construcción.

## Decisiones de la sesión

- Los GGUF viven en `models/gguf/`, fuera de `data/` porque no son artefactos
  del corpus. La ruta se puede cambiar con `KEKLAB_MODELS_DIR`.
- Los pesos no se versionan; sí se versionan `models/README.md` y
  `models/SHA256SUMS`.
- Se versionan `data/classification/samples/`, `tasks/`, `silver/`, `splits/`,
  `reports/` y `manifests/`. Se ignoran `llm/raw/` y `predictions/`, que se
  regeneran desde tareas y manifiestos.
- Se mantiene el prompt `v2` para la plata, con hash
  `30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769`. Si el
  smoke test exige cambios, se crea `v3` y se repite el pre-registro.
- La plata es confiada: no se revisa humanamente. El oro de 200 no entrena ni
  corrige la plata; solo diagnostica al maestro.

## Qué se implementó

### Carpeta de modelos

```text
models/
├── README.md
├── SHA256SUMS
└── gguf/              # ignorado, salvo futuros archivos de texto
```

`models/SHA256SUMS` incluye los hashes conocidos de Qwen3-8B Q4, Laya y
GLiNER. El hash de `laya-head.safetensors` queda pendiente hasta que el archivo
llegue. `common/paths.py` gana `MODELS_DIR` y `DEFAULT_LLM_MODEL`; el CLI usa
`models/gguf/qwen3-8b-q4_k_m.gguf` por defecto.

### Pre-registro de plata

- `docs/silver_classification_protocol.md`: muestra, ventana, semilla, prompt,
  maestro, smoke test, split, modelos, métricas, artefactos y límites.
- `docs/evaluation_protocol.md`: enmienda explícita que separa plata de oro y
  aclara que la tabla principal mide imitación del maestro, no verdad.

### Muestreo

`sample_rotlk_stream` ahora acepta `window_start`/`window_end` exactos, con
`--start`/`--end` en `keklab annotate sample`. La ventana se aplica antes de
ofrecer candidatos al reservorio, así que no se llenan cupos con posts fuera
del rango.

También se corrigió el tamaño de los reservorios. Antes se reservaban
`random_count` candidatos **por mes**; para 5.000 posts eso hubiera mantenido
5.000 por mes en memoria. Ahora el cupo se deriva de la cantidad esperada de
meses (`~244` por mes para 5.000 posts en 41 meses) y conserva un mínimo de 64
para muestras pequeñas.

### Hash del prompt en las tareas

`TaskRecord` incluye `prompt_sha256` opcional y `build_tasks` lo propaga. Las
tareas nuevas registran el hash del prompt, además de las versiones de guideline
y prompt. Los archivos históricos sin el campo siguen cargando.

### Paquete `classification/`

| Archivo | Función |
|---|---|
| `backends.py` | `LlamaCppBackend` con carga diferida, modo chat, `/no_think` para Qwen3 y `FakeBackend` para tests |
| `grammar.py` | JSON Schema de la salida esperada |
| `batch.py` | Sharding, reanudación, reintentos, salida cruda append-only |
| `silver.py` | Parseo, validación de etiquetas/toxicidad/evidencia y conversión a `Annotation` con `tier="silver"` |
| `dataset.py` | Join con texto, one-hot de 16 marcos y 7 cabezas, toxicidad binaria |
| `manifest.py` | SHA256 de archivos, hash de plantilla de chat, commit y manifiesto atómico |
| `cli.py` | `keklab classify llm/silver/dataset` |

Comandos nuevos:

```bash
keklab classify llm \
  --tasks data/classification/tasks/rotlk_5000.jsonl \
  --model models/gguf/qwen3-8b-q4_k_m.gguf \
  --out data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
  --n-ctx 2048 --n-gpu-layers -1 --shard 1/4 \
  --manifest data/classification/manifests/qwen3-shard-1.json

keklab classify silver \
  --tasks data/classification/tasks/rotlk_5000.jsonl \
  --raw data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
  --out data/classification/silver/rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl

keklab classify dataset \
  --silver data/classification/silver/rotlk_5000.qwen3-8b-q4_k_m.silver.jsonl \
  --samples data/classification/samples/rotlk_5000.jsonl \
  --splits data/classification/splits/rotlk_5000_threads.jsonl \
  --out data/classification/dataset.jsonl
```

### Split estable

`splits.py` gana `assign_thread_splits_stable`: conserva los hilos ya asignados
y coloca los nuevos en el split con mayor déficit. `keklab annotate split`
acepta `--existing`. También se agregó `read_split_manifest`.

## Tests

La suite pasa con **155 pruebas** (antes 136). Se agregaron pruebas para:

- ventana explícita, ventana invertida y ausencia de timestamp máximo;
- split estable, conservación de hilos existentes y lectura del manifiesto;
- parseo de JSON con fences, validación de etiquetas y toxicidad;
- evidencia no verbatim, `post_id` distinto y errores de conversión;
- sharding, reanudación, reintento y fallo del backend;
- export de dataset con one-hot, splits y muestras faltantes;
- esquema de salida.

También se corrió un smoke test de CLI con backend falso: 5 muestras → tareas
con hash `30dc5689…` → batch → plata → dataset. Todo el flujo de plomería
funciona sin modelos reales.

## Lo que no se hizo

- No se descargó ni generó la muestra real de 5.000; requiere el dump ROTLK.
- No se instaló `llama-cpp-python` ni se corrió el maestro; requiere la máquina
  con la GTX 1070 Ti.
- No se ejecutó el smoke test de 50 posts ni el diagnóstico del maestro contra
  los 200 de oro.
- No se implementaron los baselines, BERT/RoBERTa, Laya, GLiClass ni GLiNER.
- No se descargó la ventana reciente de 4plebs.
- Sigue pendiente el self test-retest de 40 posts.

## Siguiente paso

1. Copiar los GGUF a `models/gguf/` y verificar `sha256sum -c models/SHA256SUMS`.
2. Instalar `llama-cpp-python` con CUDA en la máquina objetivo.
3. Generar y auditar la muestra de 5.000 con `--start 2016-06-01 --end
   2019-11-01 --random 5000 --targeted 0 --seed 17`.
4. Construir tareas y verificar el hash del prompt.
5. Correr el smoke test de 50 posts, ajustar `n_ctx`/`n_gpu_layers` si hace
   falta y recién entonces lanzar los 5.000.
6. Convertir a plata, congelar el split y exportar el dataset.
7. Entrenar el primer baseline y comparar contra plata test; reportar el oro
   200 aparte como diagnóstico.

## Estado de git

La implementación quedó en `cd5e4af` (código y tests) y esta entrada junto con
el pre-registro y `models/` en `2ea5fd8`. Ambas se empujaron a `master`; el
remoto coincide con el local. Los artefactos `data/annotations/tasks/`,
`proposals/` y `reviews/` del piloto siguen sin trackear: son intermedios
regenerables y las propuestas de IA no son oro.
