# Role: stratified sampling for 4plebs (by month/thread). Census first.
# Connects to: ingest/fourplebs_client, ingest/dedupe, common/io.
# 
# Estrategia:
# 1. Censo ligero: contar hilos por mes/año
# 2. Si muchos hilos -> muestreo aleatorio sistemático
# 3. Muestreo a nivel HILO (preservar contexto conversacional)
# 4. Dentro de hilo: tomar posts

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from keklab.common.logging import get_logger

log = get_logger(__name__)


def census_and_group_by_month(threads_list: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    """
    Censo y agrupación por mes en una sola pasada.
    Agrupa por timestamp del OP.
    """
    counts: dict[str, int] = defaultdict(int)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in threads_list:
        op = None
        if isinstance(t, dict):
            if isinstance(t.get("posts"), list) and t["posts"]:
                op = t["posts"][0]
            else:
                op = t
        if not isinstance(op, dict):
            key = "unknown"
        else:
            ts = op.get("time")
            if isinstance(ts, (int, float)):
                try:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    key = dt.strftime("%Y-%m")
                except Exception:
                    key = "unknown"
            else:
                key = "unknown"
        counts[key] += 1
        grouped[key].append(t)
    return dict(sorted(counts.items())), dict(sorted(grouped.items()))


def stratified_sample_threads(
    threads_by_month: dict[str, list[dict[str, Any]]],
    target_per_month: int = 50,
    random_state: int = 1234,
) -> list[dict[str, Any]]:
    """
    Muestreo estratificado por mes.
    Si <= target_per_month toma todos, sino muestreo aleatorio.
    """
    rng = random.Random(random_state)
    sampled = []
    for month, threads in sorted(threads_by_month.items()):
        if not threads:
            continue
        if len(threads) <= target_per_month:
            sampled.extend(threads)
            log.info(f"{month}: tomó todos ({len(threads)})")
        else:
            s = rng.sample(threads, target_per_month)
            sampled.extend(s)
            log.info(f"{month}: muestreó {target_per_month} de {len(threads)}")
    return sampled

