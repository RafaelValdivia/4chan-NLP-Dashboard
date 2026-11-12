# Journal PLN — Entrada 19 (11-11-2026)

## Contexto

Continuación de la entrada 18. El objetivo de la sesión fue dejar listo el
maestro Qwen para etiquetar la muestra plata de 5.000 posts y verificar si el
entorno local permite además entrenar GLiNER y Laya. No se modificó código en
esta sesión: se auditó el entorno, los modelos y los artefactos existentes, y se
tomaron las decisiones operativas para la corrida.

La muestra `data/classification/samples/rotlk_5000.jsonl` ya existe con 5.000
posts. Todavía no hay tareas, etiquetas plata ni split para esa muestra.

## Decisiones tomadas

| Decisión | Valor | Motivo |
|---|---|---|
| Entorno Python | `~/PyVenvs/NetworkAnalysis` | Ya tiene torch 2.12.1+cu130 con CUDA, transformers, sklearn, sentence-transformers, accelerate, safetensors y pytest. Evita reinstalar la pila ML y ahorra disco. |
| Backend del maestro | `llama-server` por HTTP (API compatible con OpenAI) | El binario Vulkan ya funciona y soporta JSON schema, plantilla jinja y reasoning off. No requiere compilar `llama-cpp-python`. |
| Thinking de Qwen | Desactivado explícitamente con `enable_thinking=false` | El sufijo `/no_think` no es fiable con esta plantilla; en la prueba el modelo entró en modo thinking. |
| Hash de Qwen | Postergado | El usuario verificó el shasum y pidió no bloquear la corrida por la discrepancia. No se redescarga el modelo. |
| Fine-tuning de Qwen | No se hace ahora | Qwen es el maestro; 200 posts de oro son insuficientes para ajustarlo y la plata es su propia salida. La corrida usa prompting y gramática JSON. |
| GLiNER y Laya | Fine-tuning diferido | No hay checkpoints PyTorch completos locales ni runtime suficiente. No se descargan modelos. |
| Entrega de fine-tuning | Exportar datasets ahora; entrenadores cuando existan los pesos locales | Permite avanzar con la clasificación sin depender de descargas. |
| Smoke test | 50 posts antes de los 5.000 | Exigido por el pre-registro de plata. |
| Oro de 200 | Solo diagnóstico externo | No entrena, no corrige y no bloquea la plata. |
| Muestra plata | Usar la muestra existente de 5.000 | Ya fue generada; no hace falta volver a montar ROTLK para muestrear. |
| Descargas de modelos | Prohibidas | Se trabaja solo con los artefactos locales. |

## Verificaciones realizadas

### Entorno Python

- Existen `~/PyVenvs/LanguageProcessing`, `~/PyVenvs/NetworkAnalysis` y
  `~/PyVenvs/NeuralNetworks`. No existe `~/PyVenvs/NNnPLN`.
- `NetworkAnalysis` tiene Python 3.12.3, torch 2.12.1+cu130 con CUDA
  disponible, transformers 5.12.1, sklearn 1.9.0, sentence-transformers 5.6.0,
  accelerate 1.14.0, safetensors, pandas 3.0.3, PyYAML, lark y pytest.
- Faltan en `NetworkAnalysis`: `keklab` (no instalado), `duckdb`, `tenacity`,
  `zstandard`, `gliner`, `datasets`, `peft`, `gguf` y `llama_cpp`.
- `NeuralNetworks` carece de pytest/duckdb; `LanguageProcessing` carece de la
  pila ML. Ningún entorno está completo para el proyecto.

### llama.cpp

- Build Vulkan `b12255` en
  `/home/flynn/llama-local/vulkan/extracted/llama-b12255`.
- `llama-cli` carga `models/gguf/Qwen3-8B-Q4_K_M.gguf` en la GTX 1070 Ti por
  Vulkan: aproximadamente 64 tok/s de prompt y 36 tok/s de generación, salida
  correcta.
- `llama-server` soporta `--jinja`, `--reasoning off`, `--json-schema`,
  `--chat-template-kwargs` y `--pooling`.
- `llama-cpp-python` no está instalado en ningún venv. La decisión de usar
  `llama-server` por HTTP evita esa dependencia.

### Integridad de modelos

- `DEFAULT_LLM_MODEL` apunta a `models/gguf/qwen3-8b-q4_k_m.gguf`, pero el
  archivo real es `models/gguf/Qwen3-8B-Q4_K_M.gguf` (diferencia de
  mayúsculas).
- SHA256 real de Qwen: `d98cdcbd03e1...`; el pre-registro esperaba
  `90962c51b3...`. La discrepancia queda postergada por decisión del usuario.
- `models/SHA256SUMS` está actualmente vacío en el working tree; el usuario
  indicó que ya verificó el shasum.
- Laya:
  - `laya-Q8_0.gguf` es un encoder ModernBERT-large de 395M parámetros,
    28 capas, hidden 1024, cuantización Q8_0.
  - `laya-head.safetensors` contiene solo la cabeza (`act_head`, `head`,
    `scorer`, `type_emb`, `temperature`), no el encoder.
  - `/home/flynn/modelos_originales/laya-base/model.safetensors` está truncado:
    mide 1.048.576 bytes, pero su cabecera describe offsets hasta
    ~842.587.666 bytes. `safe_open` falla con “incomplete metadata, file not
    fully covered”.
  - Consecuencia: no se puede hacer fine-tuning completo de Laya sin un
    checkpoint PyTorch completo local.
- GLiNER:
  - `gliner-deberta-q8_0.gguf` declara `general.architecture = gliner`.
  - `llama.cpp` b12255 no puede cargarlo: “unknown model architecture:
    'gliner'”.
  - El paquete `gliner` no está en ningún venv y no hay checkpoint PyTorch
    local de `urchade/gliner_medium-v2.1` en la caché de Hugging Face, la caché
    de pip ni las carpetas del proyecto.
  - Consecuencia: sin runtime/checkpoint local no se puede ejecutar ni
    entrenar GLiNER.
- Supervisión de GLiNER: la plata es multi-label a nivel de post, pero GLiNER
  espera spans. La evidencia del LLM es una lista plana, no está asociada a
  cada marco. Se puede derivar supervisión débil usando la evidencia como span
  del marco correspondiente, pero es una aproximación.

### Repositorio y datos

- El contrato del prompt está vigente: `PROMPT_VERSION = v2`,
  `GUIDELINE_VERSION = v0.2`, hash
  `30dc56899dfc77347c2c32cfbab67cb15569e3a8b3c87c472325b91565b01769`.
- Taxonomía vigente: 16 marcos finos y 7 cabezas gruesas.
- El pipeline `classification/` ya incluye backend, batch con sharding y
  reanudación, conversión a plata, export de dataset y manifiestos.
- La suite documentada en la entrada 18 es de 155 pruebas.
- Existe `data/classification/samples/rotlk_5000.jsonl` con 5.000 filas y
  6.216.637 bytes.
- No existen `data/classification/tasks/`, `silver/` ni `splits/` para la
  muestra de 5.000.
- El dump ROTLK externo no está montado, pero la muestra de 5.000 ya fue
  generada, así que no bloquea la corrida.
- El disco raíz tiene ~3,9 GB libres; suficiente para inferencia, ajustado para
  fine-tuning de modelos grandes.

## Bloqueos identificados

1. **Laya no tiene pesos PyTorch completos utilizables.** El GGUF solo sirve
   para inferencia o para extraer features congeladas; el `model.safetensors`
   local está truncado. El fine-tuning completo queda esperando un checkpoint
   local completo.
2. **GLiNER no tiene runtime ni checkpoint local.** El GGUF no carga en
   `llama.cpp` y el paquete/checkpoint PyTorch no están instalados.
3. **La supervisión de spans para GLiNER es débil.** Solo se pueden derivar
   spans de los marcos que traigan evidencia verbatim.
4. **Discrepancia de hash de Qwen.** Postergada explícitamente; no se
   redescarga el modelo.
5. **Espacio en disco.** El fine-tuning de ModernBERT/Laya puede no caber en
   los 3,9 GB libres; se necesitará almacenamiento externo cuando se retome.

## Plan de ejecución acordado

1. Instalar las dependencias faltantes del proyecto en
   `~/PyVenvs/NetworkAnalysis`:

   ```bash
   ~/PyVenvs/NetworkAnalysis/bin/python -m pip install -e ".[dev,ingest,formal]"
   ```

   Instalar `gliner`, `datasets`, `peft` y `gguf` solo cuando existan los
   checkpoints locales correspondientes.

2. Implementar `LlamaServerBackend` contra `/v1/chat/completions`:
   - `enable_thinking=false` y `--reasoning off`;
   - `response_format` con JSON schema;
   - parámetros de servidor y modelo registrados en el manifiesto;
   - preflight/doctor para verificar modelo, hash, prompt, backend y contexto.

3. Auditar la muestra de 5.000:

   ```bash
   keklab annotate audit \
     --input data/classification/samples/rotlk_5000.jsonl \
     --start 2016-06-01T00:00:00Z \
     --end 2019-11-01T23:59:59Z --json
   ```

   Verificar 5.000 posts únicos, 5.000 hilos únicos, 0 textos vacíos, 0 hashes
   duplicados y cobertura temporal correcta.

4. Construir las tareas ciegas y verificar el hash del prompt:

   ```bash
   keklab annotate ai task \
     --input data/classification/samples/rotlk_5000.jsonl \
     --out data/classification/tasks/rotlk_5000.jsonl
   ```

5. Correr el smoke test de 50 posts con el backend HTTP y guardar manifiesto.
   Criterios de corte: 100 % JSON válido tras un reintento, menos de 2 % de
   etiquetas inválidas, sin OOM y tiempo proyectado aceptable.

6. Si el smoke pasa, correr los 5.000 en shards con reanudación:

   ```bash
   keklab classify llm \
     --tasks data/classification/tasks/rotlk_5000.jsonl \
     --out data/classification/llm/raw/rotlk_5000.qwen3-8b-q4_k_m.raw.jsonl \
     --backend llama_server --shard 1/4 --n-ctx 2048 --n-gpu-layers -1 \
     --manifest data/classification/manifests/qwen3-shard-1.json
   ```

7. Convertir la salida cruda a plata, congelar el split por hilo y exportar el
   dataset de modelado.

8. Correr Qwen sobre los 200 posts de oro y reportar el diagnóstico por
   separado. No se usa para entrenar ni para seleccionar modelos.

9. Exportar datasets para GLiNER (spans débiles desde evidencia) y para
   Laya/ModernBERT (multi-label de marcos y toxicidad). Los entrenadores quedan
   implementados y listos para ejecutarse cuando existan los pesos locales.

## Lo que no se hizo

- No se modificó código de producción.
- No se instalaron dependencias todavía.
- No se corrió el smoke test de 50 posts.
- No se generaron tareas, plata, split ni dataset para los 5.000.
- No se ejecutó el diagnóstico contra los 200 de oro.
- No se implementaron los entrenadores de GLiNER/Laya.
- No se descargó ningún modelo.

## Siguiente paso

Instalar las dependencias del proyecto en `NetworkAnalysis` e implementar el
backend HTTP de `llama-server` con su preflight. Después, auditar la muestra de
5.000 y correr el smoke test de 50 posts.

## Estado de git

Esta entrada es el único cambio de la sesión. No se modificó código ni se
tocaron los artefactos de datos.
