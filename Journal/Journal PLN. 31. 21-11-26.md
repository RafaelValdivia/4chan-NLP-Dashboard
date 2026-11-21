# Journal PLN. 31. 21-11-26

Hoy se cierra la compatibilidad del entorno de fine-tuning después de que
`training` quedara integrado en `master`. No se lanzó ningún entrenamiento.

## 1. Diagnóstico

- `torch 2.5.1+cu121` sí ejecuta CUDA en la GTX 1070 Ti (`sm_61`): pasa una
  multiplicación real en GPU. `torch.cuda.get_arch_list()` no lista `sm_61`,
  así que esa comprobación era un falso bloqueo.
- `transformers 5.22.2` desactiva PyTorch cuando torch es menor que 2.6, lo que
  rompe la integración con GLiNER y Laya. La pila compatible es
  `transformers 4.57.6`, `tokenizers 0.22.2` y `huggingface_hub 0.36.2`.
- `vegaml 0.16.1` declara `transformers>=5.17`, pero importa y funciona con
  `4.57.6`; por eso los paquetes de modelo se instalan por separado con
  `--no-deps` y se validan por imports.
- El `setup` quedó atascado por la aserción errónea de `sm_61` y por un bug en
  `queue._run_job`: `_move(..., **job)` pasaba `state` dos veces.

## 2. Cambios

- `src/keklab/training/jobs.py`: pins compatibles, instalación en dos fases,
  verificación con matmul CUDA real y manifiesto con `model_packages`.
- `src/keklab/training/queue.py`: `_move` recibe el estado sin el campo
  duplicado del job.
- `src/keklab/training/gliner_runner.py`: restaura solo los archivos que
  GLiNER usa (`config.json`, `tokenizer_config.json`, `spm.model`) y fija
  `DebertaV2Tokenizer`.
- `docs/finetuning_protocol.md`: documenta la pila pinned y el smoke test CUDA.
- Cola: `setup` en `done`; `evaluate-test-once` y `comparison-report` en
  `blocked` con `HOLD-frozen-test`.

## 3. Verificación

- `setup` terminó correctamente; CUDA matmul pasó en GPU.
- GLiNER y Laya cargan con la pila nueva.
- Tests de cola de entrenamiento: 6/6.
- No se ejecutaron entrenamientos ni evaluaciones del test congelado.
- La suite completa sobre `master` tiene fallos previos y no relacionados en
  DuckDB/analytics; `tests/test_api.py` no se puede colectar porque `fastapi`
  no está instalado en este venv.
