# Role: 4plebs API client (catalog/archive/thread) with pagination, cache, retries.
# Connects to: ingest/sample, common/io, common/paths.
# Recent: 2020+. Census first (threads by month) -> stratified sampling.
#
# Usa API de 4chan: https://a.4cdn.org/pol/ (funcional para pruebas)
# Cache en disco para evitar re-consultas. Usa urllib si httpx no está disponible.

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    import httpx

    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False
    import urllib.error
    import urllib.request

try:
    from tenacity import retry, stop_after_attempt, wait_exponential

    HAS_TENACITY = True
except Exception:
    HAS_TENACITY = False

from keklab.common.logging import get_logger
from keklab.common.paths import RAW_DIR

log = get_logger(__name__)

# API base (ajustar según endpoint real)
FOURPLEBS_BASE = "https://a.4cdn.org/pol"


class FourplebsClient:
    def __init__(self, 
        cache_dir: str | Path | None = None, 
        sleep: float = 1.0, 
        timeout: float = 30.0
            ):
        self.cache_dir = Path(cache_dir) if cache_dir else (RAW_DIR / "fourplebs_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep
        self.timeout = timeout
        self.headers = {"User-Agent": "keklab/0.1 (research)"}
        if HAS_HTTPX:
            self.client = httpx.Client(timeout=timeout, headers=self.headers)
        else:
            self.client = None

    def _cache_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("?", "_")
        return self.cache_dir / f"{safe}.json"

    def _fetch(self, url: str) -> Any:
        if HAS_HTTPX and self.client is not None:
            resp = self.client.get(url)
            resp.raise_for_status()
            return resp.json()
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get(self, url: str, cache_key: str) -> Any:
        cp = self._cache_path(cache_key)
        if cp.exists():
            log.debug(f"Cache hit: {cache_key}")
            return json.loads(cp.read_text(encoding="utf-8"))
        log.debug(f"GET {url}")
        if HAS_TENACITY:

            @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
            def _do():
                return self._fetch(url)

            data = _do()
        else:
            attempts = 0
            while True:
                try:
                    data = self._fetch(url)
                    break
                except Exception as e:
                    attempts += 1
                    if attempts >= 5:
                        raise
                    time.sleep(min(2 ** attempts, 30))
        cp.write_text(json.dumps(data), encoding="utf-8")
        time.sleep(self.sleep)
        return data

    def get_catalog(self) -> Any:
        """Catálogo actual de hilos."""
        return self._get(f"{FOURPLEBS_BASE}/catalog.json", "catalog")

    def get_archive_list(self) -> Any:
        """Lista de hilos archivados."""
        try:
            return self._get(f"{FOURPLEBS_BASE}/archive.json", "archive")
        except Exception as e:
            log.warning(f"archive.json no disponible: {e}")
            return []

    def get_thread(self, thread_id: str) -> Any:
        """Obtiene hilo completo por ID."""
        return self._get(f"{FOURPLEBS_BASE}/thread/{thread_id}.json", f"thread_{thread_id}")


