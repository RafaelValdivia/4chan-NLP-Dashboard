# Journal PLN — Entrada 4 (02-11-2026)

## Decisión: posponer la validación con ROTLK

Se decide continuar el desarrollo sin ejecutar el pipeline sobre el dump real
de ROTLK. La validación con el corpus histórico queda pospuesta hasta que el
archivo esté disponible y su esquema pueda verificarse contra el contrato de
`Post`.

## Qué se pospone

- `ndjson_expand_to_parquet()` y `canonicalize_kek_posts_chunked()` sobre ROTLK.
- El smoke test con datos reales.
- El cierre de E0 (crudo vs saneado) con el corpus histórico.
- Mediciones de volumen/tiempos sobre el corpus completo.

## Cómo se valida mientras tanto

- Fixtures sintéticos que reproducen el contrato: hilo con `posts`, `no`,
  `time`, `resto`, `com`, `sub`, `country`, `filename`, `tim`.
- El smoke test sintético pasa a ser la red de seguridad del pipeline.
- Los tests se versionan en `tests/` con pytest.

## Decisiones

- **Timestamps faltantes:** `Post.timestamp_utc` pasa a ser nullable. Si el post
  no trae `time`, se guarda `None`; no se inventa una fecha con
  `datetime.now()`.
- **Dedupe de vacíos:** el dedupe por `content_hash` solo aplica a posts con
  `text_clean` no vacío. Los posts vacíos se conservan y se deduplican
  únicamente por `(thread_id, post_id)`.

## Qué se puede avanzar sin ROTLK

1. Dedupe de posts vacíos (`content_hash = SHA256("")`).
2. Política de timestamps faltantes.
3. Tests del pipeline (streaming, limpieza, canonicalización, dedupe).
4. `config.py`, `registry.py`, `cli.py`.
5. Esqueleto de E0/E2 desacoplado del corpus.

## Criterios para retomar

1. Disponer del NDJSON de ROTLK.
2. Correr el smoke test real contra el contrato de `Post`.
3. Verificar conteos, timestamps e `is_op`.
4. Recién entonces correr E0/E2 sobre el corpus.

## Estado

- E0: bloqueado para resultados reales; el harness puede prepararse con
  fixtures.
- E1–E6: no iniciados.
