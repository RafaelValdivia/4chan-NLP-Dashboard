# Modelos locales

Los pesos no se versionan. Esta carpeta documenta qué archivo se espera, para
qué se usa y cómo verificar su integridad antes de una corrida.

## Estructura

```text
models/
├── README.md
├── SHA256SUMS
└── gguf/
    ├── qwen3-8b-q4_k_m.gguf
    ├── laya-q8_0.gguf
    ├── laya-head.safetensors
    └── gliner-deberta-q8_0.gguf
```

`models/gguf/` está en `.gitignore`. Para usar otra ubicación, definir
`KEKLAB_MODELS_DIR`; el default es `models/gguf/` dentro del repositorio.

## Archivos esperados

| Archivo | Rol | Tamaño aproximado |
|---|---|---:|
| `qwen3-8b-q4_k_m.gguf` | Maestro de etiquetado plata y referencia del chatbot | ~4,68 GiB |
| `laya-q8_0.gguf` | Clasificador zero-shot de marcos | ~402 MiB |
| `laya-head.safetensors` | Cabeza de clasificación de Laya | ~101 MiB |
| `gliner-deberta-q8_0.gguf` | Extracción de marcos/entidades | ~201 MiB |

`GLiClass` es opcional y queda fuera de la primera corrida hasta que se provea
su checkpoint.

## Verificación

```bash
cd models
sha256sum -c SHA256SUMS
```

El hash de `laya-head.safetensors` se agrega cuando el archivo esté disponible;
hasta entonces la línea correspondiente queda comentada en `SHA256SUMS`.
