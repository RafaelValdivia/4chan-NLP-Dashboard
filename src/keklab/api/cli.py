# Role: `keklab api serve` command.
# Connects to: api/app, api/settings, common/cli.

from __future__ import annotations

import argparse
import os
from typing import Any


def _cmd_api_serve(args: argparse.Namespace) -> int:
    """Run the FastAPI app with Uvicorn."""
    import uvicorn

    if args.l0:
        os.environ["KEKLAB_L0_GLOB"] = args.l0
    if args.predictions is not None:
        os.environ["KEKLAB_PREDICTIONS"] = args.predictions
    if args.events:
        os.environ["KEKLAB_EVENTS"] = args.events
    if args.web_dir:
        os.environ["KEKLAB_WEB_DIR"] = args.web_dir

    if args.reload:
        uvicorn.run(
            "keklab.api.app:app",
            host=args.host,
            port=args.port,
            reload=True,
        )
        return 0

    from keklab.api.app import create_app
    from keklab.api.settings import Settings

    uvicorn.run(create_app(Settings.from_env()), host=args.host, port=args.port)
    return 0


def add_api_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "api", help="Servidor HTTP del panel y el chatbot"
    )
    api_sub = parser.add_subparsers(dest="api_command", required=True)

    serve = api_sub.add_parser("serve", help="Levantar FastAPI con Uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="Recarga en desarrollo")
    serve.add_argument("--l0", default=None, help="Glob del parquet L0")
    serve.add_argument(
        "--predictions", default=None, help="Tabla o parquet con predicciones (L1)"
    )
    serve.add_argument("--events", default=None, help="YAML de hitos externos")
    serve.add_argument("--web-dir", default=None, help="Directorio del frontend")
    serve.set_defaults(func=_cmd_api_serve)
    return parser
