# Journal PLN — Entrada 20 (11-11-2026)

## Contexto

Continuación de la entrada 19. En esa entrada solo se auditó el entorno y se
planificó la corrida. En esta sesión se ejecutó el plan: se instalaron las
dependencias, se implementó el backend HTTP de `llama-server`, se añadió
validación semántica y el comando `doctor`, se corrieron dos smoke tests y se
lanzó la corrida de 5.000 posts.

La corrida de 5.000 **falló**: solo 385 filas (7,7 %) quedaron válidas. Esta
entrada documenta la implementación, las verificaciones, el incidente con su
atribución exacta, el error de diseño que lo causó y las correcciones
implementadas al final de la sesión.

## Implementación realizada

### Dependencias

Se instalaron las dependencias del proyecto en `~/PyVenvs/NetworkAnalysis`:

```bash
~/PyVenvs/NetworkAnalysis/bin/python -m pip install -e ".[dev,ingest,formal]"
```

Esto añade `keklab` editable, `duckdb`, `tenacity` y `zstandard`. No se
instalaron `gliner`, `datasets`, `peft` ni `gguf` porque siguen sin existir los
checkpoints locales correspondientes.

### Backend HTTP (`classification/backends.py`)

`LlamaServerBackend` habla con `/v1/chat/completions` de `llama-server`:

- `chat_template_kwargs={"enable_thinking": False}` para apagar el razonamiento
  de Qwen3.
- `response_format` con `json_object` y fallback a `json_schema` de OpenAI.
- `health()`, `props()`, `preflight()` y `metadata()`; el manifiesto registra
  modelo, build, plantilla, contexto y configuración del servidor.
- Sin dependencia de `llama-cpp-python`.

### CLI (`classification/cli.py`)

- `--backend llama_server` pasa a ser el backend por defecto.
- Nuevos flags: `--base-url`, `--server-timeout`, `--no-validate`.
- Nuevo subcomando `keklab classify doctor`: verifica servidor, modelo cargado,
  nombre del modelo, contexto, soporte de `enable_thinking`, hash del prompt y
  hash de las tareas.

### Validación semántica (`classification/validate.py`, nuevo)

- `validate_payload`: slugs conocidos, exclusividad de `none`/`unclear`,
  toxicidad 0-3, confianza en [0,1], `post_id` correcto y evidencia verbatim.
- `rule_violations`: reglas del codebook para el informe de plata (prejuicio
  específico no debe convivir con genérico).
- `repair_prompt`: reintento de reparación para payloads inválidos.

`batch.py` valida cada payload y hace **un** reintento de reparación; el
informe cuenta `repaired`. `silver.py` añade contadores de `rule_violations`.

### Corrección de entorno (`common/io.py`)

`zstandard` 0.25 devuelve un objeto que no acepta `.readline()`; se envuelve en
`io.BufferedReader(reader)`. Sin esto la ingesta fallaba.

### Pruebas

Suite completa: **174 pruebas en verde** al final de la implementación (155
previas + 19 nuevas: 6 del backend HTTP y 13 de validación).

## Verificaciones realizadas

### Auditoría de la muestra de 5.000

- 5.000 posts únicos y 5.000 hilos únicos; 0 posts duplicados, 0 hilos
  duplicados, 0 textos vacíos.
- 64 filas comparten 27 valores de `content_hash`; son textos idénticos cortos
  legítimos (`bump`, `kek`, etc.) en hilos distintos, no registros duplicados.
- 42 meses distintos (2016-06 a 2019-11), 119-120 posts por mes, 0 fuera de la
  ventana temporal, 1.480 posts son OP.

### Tareas ciegas

- `data/classification/tasks/rotlk_5000.jsonl`: 5.000 tareas.
- Hash del prompt:
  `30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769`.
- `PROMPT_VERSION=v2`, `GUIDELINE_VERSION=v0.2`; 16 marcos finos, 7 cabezas
  gruesas.
- Las tareas son ciegas: `subject=None`, contexto vacío, sin etiquetas.

### Tamaño de los prompts

- 3.584 caracteres mínimo, 3.790 mediana, 4.834 p95, **8.877 máximo**
  (≈ 2.536 tokens estimados).
- El pre-registro fijaba `n_ctx=2048`; el prompt más largo ya no cabe. Debe
  subirse a ≥4.096 tokens por slot.

### Smoke tests

- Smoke v1 (sin validación): 50/50 válidas, 0 fallos, 245 s, 4,9 s/post.
- Smoke v2 (con validación y reparación): 50/50 válidas, 2 reparadas, 258 s.
- Calidad observada: confianza 0,95 en 45/50 (no hay señal de calibración);
  5/50 combinan prejuicio específico con genérico; 0 usos de `unclear`;
  2 fragmentos de evidencia no verbatim.

### Preflight

- Servidor alcanzable, modelo cargado, nombre de modelo correcto, contexto
  reportado, `enable_thinking` soportado, hash del prompt coincidente.

## La corrida de 5.000 y su fallo

Se lanzaron **4 shards** contra un servidor arrancado con `-c 4096`. El
servidor reparte el contexto total entre sus slots paralelos, así que cada
petición disponía de ~1.024 tokens, muy por debajo de los 950-2.536 tokens de
los prompts. Además, el usuario detuvo el servidor al final de la corrida.

### Atribución exacta

| Resultado | Filas | Causa |
|---|---:|---|
| Válidas | 385 (7,7 %) | — |
| `HTTP 500 Context size has been exceeded` | 664 | **Error de configuración propio** (4 slots × 1.024 tokens) |
| `llama-server unreachable` | 3.947 | **El usuario detuvo el servidor** |
| `RemoteDisconnected` | 4 | El usuario detuvo el servidor |
| **Total** | **5.000** | 5.000 `task_id` únicos, 0 duplicados |

Con el servidor arriba se intentaron 1.053 filas y solo 385 fueron válidas
(36,6 %). La latencia de las filas válidas fue de 16,6 s de media frente a
4,9 s/post del smoke con un solo cliente: la concurrencia multiplicó por ~3,4
la latencia por petición y no mejoró el rendimiento agregado, porque la
generación está limitada por ancho de banda en la GTX 1070 Ti.

### Cronología

- `00:38:03` — arranca la corrida de 4 shards.
- `00:38`-`02:27` — servidor arriba; 1.053 intentos, 385 válidos, 664 errores
  de contexto.
- `02:27:41` — el usuario detiene el servidor; en ese minuto los shards
  escriben 3.956 filas de fallo de conexión y terminan sus colas.

## Diagnóstico y responsabilidad

1. **Error propio:** propuse y lancé 4 shards sin comprobar cómo `-c` se
   reparte entre slots ni el tamaño real de los prompts. La configuración
   estaba condenada a fallar y quemó 664 peticiones.
2. **Error propio de razonamiento:** asumí que más concurrencia sería más
   rápido sin medir el límite de ancho de banda del GPU. La evidencia dice lo
   contrario: un solo cliente es igual o más rápido y no falla.
3. **Decisión deliberada, correcta:** cada fila se escribe y se hace `flush`
   inmediatamente después de clasificarse, y el archivo es append-only. Por eso
   se conservaron las 385 filas válidas y los 5.000 `task_id`.
4. **Fallo de diseño (no deliberado):** no existía taxonomía de errores. El
   bucle trataba igual "servidor caído", "contexto agotado" y "JSON inválido".
   Consecuencias: siguió escribiendo fallos tras la caída del servidor y
   reintentó errores de contexto con un prompt de reparación **más largo**, que
   garantizaba otro fallo.
5. **Fallo de diseño (no deliberado):** no había guardia previa que comparara
   el prompt más largo con el contexto por slot del servidor.

## Correcciones implementadas en esta sesión

### Taxonomía de errores (`classification/errors.py`, nuevo)

- `TransportError`: servidor inalcanzable, timeout, conexión cerrada, HTTP 5xx.
- `SystemicError`: contexto agotado, KV cache llena, OOM, modelo no cargado.
- `classify_exception` / `classify_message`: clasifican también excepciones no
  tipadas por su mensaje.

### Cortacircuitos en `batch.py`

- `transport`: se reintenta con el **prompt original** (nunca con reparación) y
  el shard aborta tras `--max-consecutive-transport-errors` fallos seguidos
  (por defecto 3).
- `systemic`: no se reintenta y el shard aborta de inmediato
  (`--allow-systemic-continue` lo desactiva).
- `contract`: JSON inválido o payload fuera de contrato; se repara una vez y se
  registra como fallo normal.
- Cada fila cruda lleva ahora `error_kind` (`transport`/`systemic`/`contract`/
  `other`) y el informe lleva `aborted`, `abort_reason` y `error_kinds`.
- Al abortar se escribe la fila culpable y se detiene el bucle; el resto queda
  pendiente para la reanudación. Nada se pierde.
- `repaired` ahora solo cuenta reparaciones reales de contrato, no reintentos
  de transporte.

### Guardia de contexto (`backends.py` + `cli.py`)

- `LlamaServerBackend.context_report()`: obtiene `n_ctx` y `total_slots` de
  `/props`, calcula el contexto por slot, tokeniza el prompt más largo con
  `/tokenize` (o estima si el servidor no responde) y exige espacio para
  prompt + plantilla + reparación + salida.
- `classify llm` ejecuta la guardia antes de la corrida y se niega a arrancar si
  no cabe (`--skip-context-guard` la desactiva).
- `classify doctor --tasks ...` incluye la guardia y devuelve error si el
  prompt más largo no cabe en un slot.
- El manifiesto registra `context_guard` y usa el `n_ctx` real del servidor.

### Pruebas nuevas

- `tests/test_classification_resilience.py`: 6 pruebas del cortacircuitos, la
  taxonomía, el reintento de transporte y la desactivación del cortacircuitos.
- `tests/test_classification_backend_server.py`: 4 pruebas nuevas (error
  sistémico, `context_report` que cabe, que no cabe, y slots en preflight).
- Suite completa: **184 pruebas en verde**.

## Estado de los datos y del servidor

- `data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.shard{1..4}.raw.jsonl`:
  1.250 filas cada uno, 5.000 en total.
- 385 filas válidas reutilizables; 4.615 filas fallidas reanudables.
- Manifiestos: `data/classification/manifests/qwen3-shard-{1..4}.json`.
- No se ha hecho merge, ni plata, ni split, ni dataset para los 5.000.
- El servidor `llama-server` está detenido.
- El código nuevo **no** se ha ejecutado contra el modelo todavía.

## Enmiendas al pre-registro

1. **Meses:** la muestra cubre 42 meses (2016-06 a 2019-11), no 41.
2. **Duplicados de `content_hash`:** 64 filas comparten 27 hashes por textos
   idénticos cortos legítimos; no son registros duplicados. Se documenta para
   que la auditoría no los cuente como error.
3. **Contexto:** `n_ctx` por slot debe ser ≥4.096; el valor 2.048 del
   pre-registro es insuficiente para el prompt más largo.
4. **Confianza del maestro:** es ~0,95 casi constante, así que no sirve como
   señal de calibración. Se reportará como tal; no invalida las etiquetas.

## Lecciones operativas

1. No paralelizar sin calcular antes el contexto por slot y sin medir si la
   concurrencia aporta. En esta GPU la generación es limitada por ancho de
   banda: un cliente es igual de rápido y mucho más seguro.
2. Correr siempre la guardia del prompt más largo antes de una corrida larga.
3. Un backend caído debe detener la corrida, no rellenar el archivo de fallos.
4. Un error sistémico no se "repara" con un prompt más largo.
5. El servidor debe sobrevivir a la sesión de terminal (`setsid`) y, para
   corridas largas, tener un supervisor de salud que lo reinicie.

## Siguiente paso (pendiente de autorización)

1. Reiniciar el servidor con un solo slot y contexto completo:

   ```bash
   setsid llama-server \
     -m models/gguf/Qwen3-8B-Q4_K_M.gguf \
     --host 127.0.0.1 --port 8080 \
     -c 8192 -ngl 99 --parallel 1 \
     --jinja --reasoning off --no-webui --no-warmup \
     > /tmp/llama-server.log 2>&1 &
   ```

2. Verificar con la guardia incluida:

   ```bash
   keklab classify doctor \
     --tasks data/classification/tasks/rotlk_5000.jsonl \
     --model models/gguf/Qwen3-8B-Q4_K_M.gguf \
     --n-ctx 8192 --n-gpu-layers -1
   ```

3. Fusionar los 4 shards en un único archivo crudo (5.000 `task_id` únicos) y
   reanudar con un solo cliente:

   ```bash
   cat data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.shard{1..4}.raw.jsonl \
     > data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl

   keklab classify llm \
     --tasks data/classification/tasks/rotlk_5000.jsonl \
     --out data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
     --backend llama_server --shard 1/1 \
     --n-ctx 8192 --n-gpu-layers -1 \
     --manifest data/classification/manifests/qwen3-resume.json
   ```

   Se saltan las 385 filas válidas y se reintentan las 4.615 fallidas.
   ETA ≈ 6,3 h a 4,9 s/post, con supervisor de salud del servidor.

4. Después: `classify silver` → congelar split por hilo → `classify dataset` →
   diagnóstico contra los 200 de oro, reportado por separado.

## Estado de git

Modificados en esta sesión:

- `src/keklab/classification/backends.py`
- `src/keklab/classification/batch.py`
- `src/keklab/classification/cli.py`
- `tests/test_classification_backend_server.py`

Nuevos en esta sesión:

- `src/keklab/classification/errors.py`
- `tests/test_classification_resilience.py`
- esta entrada de journal

Pendientes de la sesión anterior (sin commit):

- `src/keklab/classification/silver.py`, `src/keklab/common/io.py`,
  `src/keklab/classification/validate.py`
- `tests/test_classification_validate.py`
- `data/classification/tasks/`, `data/classification/manifests/`
- `models/SHA256SUMS` (modificación preexistente del usuario)

No se ha hecho commit. No se ha tocado ningún artefacto de datos en esta
sesión.
