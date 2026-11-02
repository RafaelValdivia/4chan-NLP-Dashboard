# Role: annotation sampling from the 4plebs archive API and canonical ROTLK parquet.
# Connects to: ingest/kek_loader, formal/schema, annotation/schema, annotation/labels.

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # optional HTTP client
    import httpx

    HAS_HTTPX = True
except Exception:  # pragma: no cover - exercised only without httpx
    HAS_HTTPX = False

import pandas as pd

from keklab.annotation.labels import TARGETED_SEARCH_TERMS
from keklab.annotation.schema import ContextPost, SampleContext, SamplePost
from keklab.common.logging import get_logger
from keklab.common.paths import CACHE_DIR
from keklab.ingest.kek_loader import canonicalize_fourplebs_thread

log = get_logger(__name__)

ARCHIVE_BASE = "https://archive.4plebs.org/_/api/chan"
DEFAULT_USER_AGENT = "keklab/0.1 (research)"


# ---------------------------------------------------------------------------
# Small coercion helpers (archive JSON, pandas and DuckDB rows)
# ---------------------------------------------------------------------------
def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> str:
    return "" if _is_missing(value) else str(value)


def _optional_text(value: Any) -> str | None:
    return None if _is_missing(value) else str(value)


def _as_list(value: Any) -> list[Any]:
    if _is_missing(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _coerce_datetime(value: Any) -> datetime | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    elif hasattr(value, "to_pydatetime"):
        dt = value.to_pydatetime()
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _month_key(value: datetime | None) -> str:
    return value.strftime("%Y-%m") if value else "unknown"


# ---------------------------------------------------------------------------
# 4plebs archive client
# ---------------------------------------------------------------------------
class FourplebsArchiveClient:
    """Thin client for the 4plebs FoolFuuka archive API.

    Endpoints:
      index/?board=pol&page=N          -> threads keyed by number, op only
      thread/?board=pol&num=N          -> op plus posts (dict keyed by number)
      search/?boards=pol&text=...&page -> {"0": {"posts": [...]}, "meta": ...}

    A User-Agent is mandatory; without it the archive answers with a policy
    error. Responses are cached on disk and requests are rate-limited.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        sleep: float = 1.0,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        http_client: Any | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else (CACHE_DIR / "fourplebs_archive")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}
        self._http = http_client
        self._curl = shutil.which("curl")

        # The 4plebs archive sits behind a filter that rejects the Python
        # HTTP clients' TLS fingerprint. Prefer curl when available, while
        # still allowing an injected client for tests.
        if self._http is None and not self._curl and HAS_HTTPX:
            self._http = httpx.Client(timeout=timeout, headers=self.headers)

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _fetch_curl(self, url: str) -> Any:
        if not self._curl:
            raise RuntimeError("curl is not available")

        command = [
            self._curl,
            "-fsSL",
            "--compressed",
            "-m",
            str(max(1, int(self.timeout))),
            "-A",
            self.headers["User-Agent"],
            "-H",
            "Accept: application/json",
            url,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"curl failed with exit {result.returncode}: {detail[:300]}"
            )
        return json.loads(result.stdout)

    def _fetch(self, url: str) -> Any:
        if self._http is not None:
            try:
                response = self._http.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception:
                if not self._curl:
                    raise

        if self._curl:
            return self._fetch_curl(url)

        request = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items()))
        url = f"{ARCHIVE_BASE}/{endpoint}/?{query}"
        cache_path = self._cache_path(url)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        data = self._fetch(url)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        if self.sleep:
            time.sleep(self.sleep)
        return data

    def index(self, page: int = 1, board: str = "pol") -> Any:
        return self._get("index", {"board": board, "page": page})

    def thread(self, num: str | int, board: str = "pol") -> Any:
        return self._get("thread", {"board": board, "num": num})

    def search(self, text: str, page: int = 1, board: str = "pol") -> Any:
        return self._get("search", {"boards": board, "text": text, "page": page})


# ---------------------------------------------------------------------------
# Archive payload parsing
# ---------------------------------------------------------------------------
def parse_index_threads(payload: Any) -> list[dict[str, Any]]:
    """Return OP post dicts from an archive index payload."""
    if not isinstance(payload, dict):
        return []

    posts: list[dict[str, Any]] = []
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        op = value.get("op")
        if isinstance(op, dict):
            posts.append(op)
        elif value.get("num") is not None and value.get("op") in (1, True):
            posts.append(value)
    return posts


def parse_thread_posts(payload: Any) -> list[dict[str, Any]]:
    """Return OP + replies from an archive thread payload (dict or list)."""
    if not isinstance(payload, dict):
        return []

    thread: dict[str, Any] = payload
    if "op" not in payload and "posts" not in payload:
        for value in payload.values():
            if isinstance(value, dict) and ("op" in value or "posts" in value):
                thread = value
                break

    raw_posts: list[dict[str, Any]] = []
    op = thread.get("op")
    if isinstance(op, dict):
        raw_posts.append(op)

    posts = thread.get("posts")
    if isinstance(posts, dict):
        raw_posts.extend(p for p in posts.values() if isinstance(p, dict))
    elif isinstance(posts, list):
        raw_posts.extend(p for p in posts if isinstance(p, dict))

    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for post in raw_posts:
        num = post.get("num")
        if num in seen:
            continue
        seen.add(num)
        unique.append(post)
    return unique


def parse_search_posts(payload: Any) -> list[dict[str, Any]]:
    """Return post dicts from every page of an archive search payload."""
    if not isinstance(payload, dict):
        return []

    posts: list[dict[str, Any]] = []
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("op"), dict):
            posts.append(value["op"])
        raw = value.get("posts")
        if isinstance(raw, list):
            posts.extend(p for p in raw if isinstance(p, dict))
        elif isinstance(raw, dict):
            posts.extend(p for p in raw.values() if isinstance(p, dict))

    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for post in posts:
        num = post.get("num")
        if num in seen:
            continue
        seen.add(num)
        unique.append(post)
    return unique


def archive_post_to_canonical(post: dict[str, Any], thread_num: Any = None) -> dict[str, Any]:
    """Map an archive post field-name shape onto the 4chan/kek shape."""
    num = str(post.get("num") or post.get("no") or "")
    thread_id = str(post.get("thread_num") or thread_num or "")
    is_op = bool(post.get("op")) or (bool(num) and num == thread_id)

    comment = post.get("comment")
    if comment is None:
        comment = post.get("comment_sanitized") or ""

    media = post.get("media")
    filename = media.get("media_filename") if isinstance(media, dict) else None

    return {
        "no": num,
        "resto": 0 if is_op else thread_id,
        "time": post.get("timestamp", post.get("time")),
        "sub": post.get("title", post.get("sub")),
        "country": post.get("poster_country", post.get("country")),
        "com": comment,
        "filename": filename,
    }


def canonicalize_archive_thread(posts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonicalize archive posts into `Post`-shaped dict rows."""
    posts = list(posts)
    thread_num = None
    if posts:
        thread_num = posts[0].get("thread_num") or posts[0].get("num")
    mapped = [archive_post_to_canonical(post, thread_num=thread_num) for post in posts]
    return canonicalize_fourplebs_thread({"posts": mapped})


# ---------------------------------------------------------------------------
# Sample construction
# ---------------------------------------------------------------------------
def _row_by_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("post_id")): row
        for row in rows
        if not _is_missing(row.get("post_id"))
    }


def build_sample(
    rows: Iterable[dict[str, Any]],
    target_post_id: str,
    stratum: dict[str, Any],
) -> SamplePost:
    """Build one `SamplePost` from every canonical row of its thread."""
    rows = list(rows)
    by_id = _row_by_id(rows)
    target = by_id.get(str(target_post_id))
    if target is None:
        raise KeyError(f"post {target_post_id!r} not present in thread rows")

    op_row = next(
        (row for row in rows if bool(row.get("is_op"))),
        rows[0] if rows else None,
    )

    op_context = None
    if op_row is not None and str(op_row.get("post_id")) != str(target_post_id):
        op_context = ContextPost(
            post_id=str(op_row.get("post_id")),
            text_raw=_text(op_row.get("raw_html")),
            is_op=True,
        )

    parents: list[ContextPost] = []
    for quote in _as_list(target.get("quotes")):
        quote_id = str(quote)
        parent = by_id.get(quote_id)
        if parent is None or quote_id == str(target_post_id):
            continue
        parents.append(
            ContextPost(
                post_id=quote_id,
                text_raw=_text(parent.get("raw_html")),
                is_op=bool(parent.get("is_op")),
            )
        )

    source = _text(target.get("source")) or "kek"
    if source not in ("kek", "fourplebs"):
        source = "kek"

    period = target.get("period")
    if period not in ("hist_2016_2019", "recent_2020_plus"):
        period = None

    text_clean = _text(target.get("text_clean"))
    content_hash = _text(target.get("content_hash")) or _hash_text(text_clean)

    return SamplePost(
        post_id=str(target.get("post_id")),
        thread_id=str(target.get("thread_id") or ""),
        source=source,
        period=period,
        timestamp_utc=_coerce_datetime(target.get("timestamp_utc")),
        subject=_optional_text(target.get("subject")),
        text_raw=_text(target.get("raw_html")),
        text_clean=text_clean,
        quotes=[str(quote) for quote in _as_list(target.get("quotes"))],
        content_hash=content_hash,
        is_op=bool(target.get("is_op")),
        country=_optional_text(target.get("country")),
        stratum=stratum,
        context=SampleContext(op=op_context, parents=parents),
    )


def _select_post(
    rows: Iterable[dict[str, Any]],
    rng: random.Random,
    used: set[str],
    *,
    require_text: bool,
    preferred_id: str | None = None,
) -> dict[str, Any] | None:
    candidates = []
    for row in rows:
        post_id = _text(row.get("post_id"))
        if not post_id or post_id in used:
            continue
        if require_text and not _text(row.get("text_clean")).strip():
            continue
        candidates.append(row)

    if preferred_id is not None:
        for row in candidates:
            if _text(row.get("post_id")) == str(preferred_id):
                return row
        return None

    return rng.choice(candidates) if candidates else None


# ---------------------------------------------------------------------------
# 4plebs sampling
# ---------------------------------------------------------------------------
def _cutoff(months: int, end: datetime | None = None) -> datetime:
    end = end or datetime.now(timezone.utc)
    return end - timedelta(days=30 * max(months, 1))


def collect_archive_candidates(
    client: Any,
    *,
    months: int = 24,
    max_pages: int = 200,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Walk archive index pages until the window's old edge or the page limit."""
    cutoff = _cutoff(months, end)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        payload = client.index(page)
        ops = parse_index_threads(payload)
        if not ops:
            break

        page_has_recent = False
        for op in ops:
            timestamp = _coerce_datetime(op.get("timestamp", op.get("time")))
            if timestamp is None or timestamp < cutoff:
                continue
            page_has_recent = True
            num = _text(op.get("num") or op.get("no"))
            if not num or num in seen:
                continue
            seen.add(num)
            candidates.append(
                {
                    "num": num,
                    "timestamp": timestamp,
                    "month": _month_key(timestamp),
                }
            )

        # Index pages run newest -> oldest. A page fully outside the window
        # means the following pages are older still.
        if not page_has_recent:
            break

    return candidates


def _round_robin_by_month(
    candidates: Iterable[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        groups[str(candidate.get("month") or "unknown")].append(candidate)

    months = sorted(groups)
    for month in months:
        rng.shuffle(groups[month])

    ordered: list[dict[str, Any]] = []
    while any(groups[month] for month in months):
        for month in months:
            if groups[month]:
                ordered.append(groups[month].pop())
    return ordered


def _sample_random_archive(
    client: Any,
    candidates: list[dict[str, Any]],
    *,
    count: int,
    rng: random.Random,
    include_empty: int,
) -> list[SamplePost]:
    if count <= 0:
        return []

    samples: list[SamplePost] = []
    used: set[str] = set()
    empty_used = 0

    for candidate in _round_robin_by_month(candidates, rng):
        if len(samples) >= count:
            break

        try:
            payload = client.thread(candidate["num"])
        except Exception as exc:  # network/API failure: skip this thread
            log.warning("Could not fetch thread %s: %s", candidate["num"], exc)
            continue

        rows = canonicalize_archive_thread(parse_thread_posts(payload))
        if not rows:
            continue

        target = _select_post(rows, rng, used, require_text=True)
        if target is None and empty_used < include_empty:
            target = _select_post(rows, rng, used, require_text=False)
            if target is not None:
                empty_used += 1
        if target is None:
            continue

        post_id = _text(target.get("post_id"))
        used.add(post_id)
        samples.append(
            build_sample(
                rows,
                post_id,
                {
                    "reason": "random",
                    "month": candidate["month"],
                    "thread_id": candidate["num"],
                },
            )
        )

    return samples


def _targeted_terms() -> list[tuple[str, str]]:
    pairs = [
        (frame, term)
        for frame, terms in TARGETED_SEARCH_TERMS.items()
        for term in terms
    ]
    return pairs


def _sample_targeted_archive(
    client: Any,
    *,
    count: int,
    months: int,
    rng: random.Random,
    exclude_post_ids: set[str],
    end: datetime | None = None,
) -> list[SamplePost]:
    if count <= 0:
        return []

    cutoff = _cutoff(months, end)
    targets = _targeted_terms()
    rng.shuffle(targets)

    frames = list(TARGETED_SEARCH_TERMS)
    max_per_frame = max(1, math.ceil(count / max(len(frames), 1)))

    samples: list[SamplePost] = []
    seen = set(exclude_post_ids)
    per_frame: Counter[str] = Counter()

    for frame, term in targets:
        if len(samples) >= count:
            break
        if per_frame[frame] >= max_per_frame:
            continue

        for page in (1, 2):
            try:
                payload = client.search(term, page=page)
            except Exception as exc:
                log.warning("Search %r failed: %s", term, exc)
                break

            posts = parse_search_posts(payload)
            if not posts:
                break

            for post in posts:
                if len(samples) >= count or per_frame[frame] >= max_per_frame:
                    break

                num = _text(post.get("num"))
                timestamp = _coerce_datetime(post.get("timestamp", post.get("time")))
                if not num or num in seen:
                    continue
                if timestamp is not None and timestamp < cutoff:
                    continue
                text = _text(post.get("comment") or post.get("comment_sanitized"))
                if term.lower() not in text.lower():
                    continue

                thread_num = _text(post.get("thread_num")) or num
                try:
                    thread_payload = client.thread(thread_num)
                except Exception as exc:
                    log.warning("Could not fetch thread %s: %s", thread_num, exc)
                    continue

                rows = canonicalize_archive_thread(parse_thread_posts(thread_payload))
                target = _select_post(
                    rows, rng, seen, require_text=True, preferred_id=num
                )
                if target is None:
                    continue

                post_id = _text(target.get("post_id"))
                seen.add(post_id)
                per_frame[frame] += 1
                samples.append(
                    build_sample(
                        rows,
                        post_id,
                        {
                            "reason": "targeted",
                            "frame": frame,
                            "term": term,
                            "month": _month_key(timestamp),
                        },
                    )
                )

    return samples


def sample_fourplebs(
    *,
    random_count: int = 20,
    targeted_count: int = 10,
    months: int = 24,
    seed: int = 13,
    max_pages: int = 200,
    include_empty: int = 0,
    client: Any | None = None,
) -> list[SamplePost]:
    """Sample random + targeted posts from the 4plebs archive API."""
    client = client or FourplebsArchiveClient()
    rng = random.Random(seed)
    end = datetime.now(timezone.utc)

    candidates = collect_archive_candidates(
        client, months=months, max_pages=max_pages, end=end
    )
    log.info("Archive candidates in window: %d", len(candidates))

    random_samples = _sample_random_archive(
        client,
        candidates,
        count=random_count,
        rng=rng,
        include_empty=include_empty,
    )
    targeted_samples = _sample_targeted_archive(
        client,
        count=targeted_count,
        months=months,
        rng=rng,
        exclude_post_ids={sample.post_id for sample in random_samples},
        end=end,
    )

    if len(random_samples) < random_count:
        log.warning(
            "Only %d/%d random posts sampled", len(random_samples), random_count
        )
    if len(targeted_samples) < targeted_count:
        log.warning(
            "Only %d/%d targeted posts sampled",
            len(targeted_samples),
            targeted_count,
        )

    return random_samples + targeted_samples


# ---------------------------------------------------------------------------
# ROTLK / canonical parquet sampling
# ---------------------------------------------------------------------------
def _quote_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve()).replace("'", "''")


def _rows_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict("records")


def _rotlk_window(
    con: Any,
    parquet: str | Path,
    months: int,
) -> tuple[datetime | None, list[str]]:
    path = _quote_path(parquet)
    row = con.execute(
        f"SELECT max(epoch(timestamp_utc)) FROM read_parquet('{path}')"
    ).fetchall()[0]
    max_ts = _coerce_datetime(row[0])
    if max_ts is None:
        return None, []

    cutoff = _cutoff(months, max_ts)
    rows = con.execute(
        f"""
        SELECT DISTINCT strftime(timestamp_utc, '%Y-%m') AS month
        FROM read_parquet('{path}')
        WHERE timestamp_utc IS NOT NULL
          AND text_clean IS NOT NULL
          AND text_clean <> ''
        ORDER BY month
        """
    ).fetchall()
    months_present = [
        str(item[0]) for item in rows if item[0] and str(item[0]) >= cutoff.strftime("%Y-%m")
    ]
    return max_ts, months_present


def _allocate_counts(
    count: int,
    months: list[str],
    rng: random.Random,
) -> dict[str, int]:
    if count <= 0 or not months:
        return {}
    months = list(months)
    rng.shuffle(months)
    base, remainder = divmod(count, len(months))
    allocation = {month: base for month in months}
    for month in months[:remainder]:
        allocation[month] += 1
    return allocation


def _thread_rows(con: Any, parquet: str | Path, thread_id: str) -> list[dict[str, Any]]:
    path = _quote_path(parquet)
    df = con.execute(
        f"""
        SELECT * EXCLUDE (timestamp_utc), epoch(timestamp_utc) AS timestamp_utc
        FROM read_parquet('{path}')
        WHERE thread_id = ?
        """,
        [str(thread_id)],
    ).df()
    return _rows_df(df)


def sample_rotlk(
    parquet: str | Path,
    *,
    random_count: int = 20,
    targeted_count: int = 10,
    months: int = 24,
    seed: int = 13,
    include_empty: int = 0,
) -> list[SamplePost]:
    """Sample random + targeted posts from a canonical ROTLK parquet."""
    import duckdb

    rng = random.Random(seed)
    con = duckdb.connect()
    path = _quote_path(parquet)

    try:
        _max_ts, months_present = _rotlk_window(con, parquet, months)
        if not months_present:
            log.warning("No months in window for %s", parquet)
            return []

        samples: list[SamplePost] = []
        used_threads: set[str] = set()

        allocation = _allocate_counts(random_count, months_present, rng)
        for month, count in sorted(allocation.items()):
            if count <= 0:
                continue
            df = con.execute(
                f"""
                SELECT * EXCLUDE (timestamp_utc), epoch(timestamp_utc) AS timestamp_utc
                FROM read_parquet('{path}')
                WHERE strftime(timestamp_utc, '%Y-%m') = ?
                  AND text_clean IS NOT NULL
                  AND text_clean <> ''
                ORDER BY hash(post_id || '{int(seed)}')
                LIMIT {int(count * 4)}
                """,
                [month],
            ).df()

            picked = 0
            for row in _rows_df(df):
                if picked >= count:
                    break
                thread_id = _text(row.get("thread_id"))
                if not thread_id or thread_id in used_threads:
                    continue
                rows = _thread_rows(con, parquet, thread_id)
                target = _select_post(
                    rows, rng, set(), require_text=True, preferred_id=_text(row.get("post_id"))
                )
                if target is None:
                    continue
                used_threads.add(thread_id)
                picked += 1
                samples.append(
                    build_sample(
                        rows,
                        _text(target.get("post_id")),
                        {"reason": "random", "month": month, "thread_id": thread_id},
                    )
                )

        # Deliberately keep a few empty/media-only posts if requested.
        empty_needed = max(0, include_empty - sum(
            1 for sample in samples if not sample.text_clean.strip()
        ))
        if empty_needed:
            df = con.execute(
                f"""
                SELECT * EXCLUDE (timestamp_utc), epoch(timestamp_utc) AS timestamp_utc
                FROM read_parquet('{path}')
                WHERE timestamp_utc IS NOT NULL
                  AND (text_clean IS NULL OR text_clean = '')
                ORDER BY hash(post_id || '{int(seed)}')
                LIMIT {int(empty_needed * 3)}
                """
            ).df()
            for row in _rows_df(df):
                if empty_needed <= 0:
                    break
                thread_id = _text(row.get("thread_id"))
                if not thread_id or thread_id in used_threads:
                    continue
                rows = _thread_rows(con, parquet, thread_id)
                target = _select_post(
                    rows, rng, set(), require_text=False, preferred_id=_text(row.get("post_id"))
                )
                if target is None or _text(target.get("text_clean")).strip():
                    continue
                used_threads.add(thread_id)
                empty_needed -= 1
                samples.append(
                    build_sample(
                        rows,
                        _text(target.get("post_id")),
                        {"reason": "random_empty", "thread_id": thread_id},
                    )
                )

        # Targeted search over seed terms.
        if targeted_count > 0:
            frames = list(TARGETED_SEARCH_TERMS)
            max_per_frame = max(1, math.ceil(targeted_count / max(len(frames), 1)))
            per_frame: Counter[str] = Counter()
            targets = _targeted_terms()
            rng.shuffle(targets)

            for frame, term in targets:
                if sum(per_frame.values()) >= targeted_count:
                    break
                if per_frame[frame] >= max_per_frame:
                    continue

                pattern = f"%{term.lower()}%"
                df = con.execute(
                    f"""
                    SELECT * EXCLUDE (timestamp_utc), epoch(timestamp_utc) AS timestamp_utc
                    FROM read_parquet('{path}')
                    WHERE lower(coalesce(text_clean, '')) LIKE ?
                      AND text_clean IS NOT NULL
                      AND text_clean <> ''
                    ORDER BY hash(post_id || '{int(seed)}')
                    LIMIT {int(max_per_frame * 4)}
                    """,
                    [pattern],
                ).df()

                for row in _rows_df(df):
                    if per_frame[frame] >= max_per_frame:
                        break
                    thread_id = _text(row.get("thread_id"))
                    if not thread_id or thread_id in used_threads:
                        continue
                    rows = _thread_rows(con, parquet, thread_id)
                    target = _select_post(
                        rows,
                        rng,
                        set(),
                        require_text=True,
                        preferred_id=_text(row.get("post_id")),
                    )
                    if target is None:
                        continue
                    used_threads.add(thread_id)
                    per_frame[frame] += 1
                    samples.append(
                        build_sample(
                            rows,
                            _text(target.get("post_id")),
                            {
                                "reason": "targeted",
                                "frame": frame,
                                "term": term,
                                "month": _month_key(
                                    _coerce_datetime(target.get("timestamp_utc"))
                                ),
                            },
                        )
                    )

        return samples
    finally:
        con.close()
