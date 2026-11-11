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
from typing import Any, Callable, Iterable

try:  # optional HTTP client
    import httpx

    HAS_HTTPX = True
except Exception:  # pragma: no cover - exercised only without httpx
    HAS_HTTPX = False

import pandas as pd

from keklab.annotation.labels import TARGETED_SEARCH_TERMS
from keklab.annotation.schema import ContextPost, SampleContext, SamplePost
from keklab.common.io import iter_ndjson
from keklab.common.logging import get_logger
from keklab.common.paths import CACHE_DIR
from keklab.ingest.kek_loader import canonicalize_fourplebs_thread

log = get_logger(__name__)

ARCHIVE_BASE = "https://archive.4plebs.org/_/api/chan"
DEFAULT_USER_AGENT = "keklab/0.1 (research)"

# Seed terms sorted longest-first so "russian" wins over "russia". Matching is
# done on lowercased text: substring checks are much cheaper than a
# case-insensitive regex over every post in a 114 GB stream.
_TARGET_TERM_TO_FRAME: dict[str, str] = {
    term.lower(): frame
    for frame, terms in TARGETED_SEARCH_TERMS.items()
    for term in terms
}
_TARGET_TERMS: tuple[tuple[str, str], ...] = tuple(
    (term, _TARGET_TERM_TO_FRAME[term])
    for term in sorted(_TARGET_TERM_TO_FRAME, key=len, reverse=True)
)


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


def _epoch_value(value: Any) -> float | None:
    """Cheap epoch extraction for the hot loop.

    ROTLK timestamps are integers; avoid pandas/datetime coercion unless the
    value is not numeric.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    timestamp = _coerce_datetime(value)
    return timestamp.timestamp() if timestamp is not None else None


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
        used_hashes: set[str] = set()

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
                sample = build_sample(
                    rows,
                    _text(target.get("post_id")),
                    {"reason": "random", "month": month, "thread_id": thread_id},
                )
                if sample.content_hash in used_hashes:
                    continue
                used_threads.add(thread_id)
                used_hashes.add(sample.content_hash)
                picked += 1
                samples.append(sample)

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
                sample = build_sample(
                    rows,
                    _text(target.get("post_id")),
                    {"reason": "random_empty", "thread_id": thread_id},
                )
                if sample.content_hash in used_hashes:
                    continue
                used_threads.add(thread_id)
                used_hashes.add(sample.content_hash)
                empty_needed -= 1
                samples.append(sample)

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
                    sample = build_sample(
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
                    if sample.content_hash in used_hashes:
                        continue
                    used_threads.add(thread_id)
                    used_hashes.add(sample.content_hash)
                    per_frame[frame] += 1
                    samples.append(sample)

        return samples
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Direct ROTLK streaming sampler (no extraction, no canonical parquet)
# ---------------------------------------------------------------------------
class _Reservoir:
    """Uniform reservoir of at most `capacity` items (Algorithm R)."""

    __slots__ = ("capacity", "items", "seen")

    def __init__(self, capacity: int) -> None:
        self.capacity = max(0, int(capacity))
        self.items: list[SamplePost] = []
        self.seen = 0

    def offer(
        self,
        factory: Callable[[], SamplePost | None],
        rng: random.Random,
    ) -> bool:
        """Offer a candidate, building it only when it is kept."""
        if self.capacity <= 0:
            return False

        self.seen += 1
        if len(self.items) < self.capacity:
            item = factory()
            if item is not None:
                self.items.append(item)
                return True
            return False

        index = rng.randrange(self.seen)
        if index >= self.capacity:
            return False

        item = factory()
        if item is None:
            return False
        self.items[index] = item
        return True


def _choose_post(
    posts: Iterable[dict[str, Any]],
    *,
    want_text: bool,
    rng: random.Random,
) -> dict[str, Any] | None:
    """Pick a post from a thread, filtered by text/metadata presence."""
    candidates: list[dict[str, Any]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        com = post.get("com")
        has_text = isinstance(com, str) and bool(com.strip())
        if has_text != want_text:
            continue
        if _epoch_value(post.get("time")) is None:
            continue
        candidates.append(post)
    return rng.choice(candidates) if candidates else None


def _match_frames(text: str) -> dict[str, str]:
    """Return {frame: matched_term} for every seed term found in text."""
    if not text:
        return {}
    lowered = text.lower()
    matches: dict[str, str] = {}
    for term, frame in _TARGET_TERMS:
        if term in lowered:
            matches.setdefault(frame, term)
            if len(matches) == len(TARGETED_SEARCH_TERMS):
                break
    return matches


def _windowed(
    samples: Iterable[SamplePost],
    cutoff: datetime,
    end: datetime | None = None,
) -> list[SamplePost]:
    """Filter to samples inside the [cutoff, end] window.

    Month keys are too coarse for the edge of the window: a post from the
    cutoff month can still predate the cutoff day. Compare real timestamps.
    """
    kept: list[SamplePost] = []
    for sample in samples:
        timestamp = sample.timestamp_utc
        if timestamp is None:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if timestamp < cutoff:
            continue
        if end is not None and timestamp > end:
            continue
        kept.append(sample)
    return kept


def _thread_sample(
    thread: dict[str, Any],
    target_post_id: str,
    stratum: dict[str, Any],
    *,
    require_text: bool = True,
) -> SamplePost | None:
    """Canonicalize one thread and build its annotation sample.

    `require_text` drops posts that are only quotes or markup once cleaned;
    they are not useful for frame annotation. Empty/media-only samples pass
    `require_text=False` when requested explicitly.
    """
    posts = thread.get("posts") or []
    if not posts:
        return None

    try:
        rows = canonicalize_fourplebs_thread({"posts": posts}, source="kek")
        sample = build_sample(rows, target_post_id, stratum)
    except Exception as exc:  # one bad thread must not abort a 114 GB pass
        log.debug("Could not build ROTLK sample for %s: %s", target_post_id, exc)
        return None

    if require_text and not sample.text_clean.strip():
        return None
    return sample


def _in_window(
    timestamp: datetime | None,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    """True when `timestamp` falls inside the optional [start, end] window."""
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if start is not None and timestamp < start:
        return False
    if end is not None and timestamp > end:
        return False
    return True


def _expected_months(start: datetime | None, end: datetime | None, months: int) -> int:
    if start is not None and end is not None:
        return max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
    return max(1, int(months))


def sample_rotlk_stream(
    dataset: str | Path,
    *,
    random_count: int = 20,
    targeted_count: int = 10,
    months: int = 24,
    seed: int = 13,
    include_empty: int = 0,
    limit_threads: int | None = None,
    window_start: datetime | str | None = None,
    window_end: datetime | str | None = None,
) -> list[SamplePost]:
    """Sample random + targeted posts directly from a ROTLK NDJSON source.

    The source may be a plain `.ndjson`, `.ndjson.gz`, `.ndjson.zst` or a
    `.tar.zst` archive containing NDJSON. A single pass keeps per-month
    reservoirs, so the archive is read in place and never extracted.

    By default the window is anchored to the newest timestamp in the data and
    spans `months` months. `window_start`/`window_end` override that window
    with exact ISO timestamps; this is what the 5,000-post silver sample uses.

    Reservoirs are sized from the expected number of months, not from the
    total sample size, so a 5,000-post request does not keep 5,000 candidates
    per month in memory.
    """
    path = Path(dataset).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)

    start = _coerce_datetime(window_start) if window_start is not None else None
    end = _coerce_datetime(window_end) if window_end is not None else None
    if window_start is not None and start is None:
        raise ValueError(f"Invalid window_start: {window_start!r}")
    if window_end is not None and end is None:
        raise ValueError(f"Invalid window_end: {window_end!r}")
    if start is not None and end is not None and start > end:
        raise ValueError("window_start must be <= window_end")

    rng = random.Random(seed)
    frames = list(TARGETED_SEARCH_TERMS)
    max_per_frame = max(1, math.ceil(targeted_count / max(len(frames), 1)))
    frame_base, frame_remainder = divmod(targeted_count, max(len(frames), 1))
    frame_quota = {
        frame: frame_base + (1 if index < frame_remainder else 0)
        for index, frame in enumerate(frames)
    }

    expected_months = _expected_months(start, end, months)
    # At least 64 candidates per month keeps small requests working when the
    # dump covers fewer months than the nominal window; 2x the equal quota
    # leaves room for the remainder. For 5,000 posts over 41 months this is
    # ~244 per month instead of 5,000.
    random_cap = max(
        64, math.ceil(random_count / expected_months) * 2
    ) if random_count > 0 else 0
    empty_cap = max(
        8, math.ceil(include_empty / expected_months) * 2
    ) if include_empty > 0 else 0

    random_res: dict[str, _Reservoir] = defaultdict(
        lambda: _Reservoir(random_cap)
    )
    empty_res: dict[str, _Reservoir] = defaultdict(
        lambda: _Reservoir(empty_cap)
    )
    target_res: dict[str, dict[str, _Reservoir]] = {
        frame: defaultdict(lambda: _Reservoir(max_per_frame))
        for frame in frames
    }

    max_epoch: float | None = None
    threads = 0
    posts_seen = 0
    started = time.monotonic()

    for thread in iter_ndjson(path):
        if not isinstance(thread, dict):
            continue

        threads += 1
        posts = [p for p in (thread.get("posts") or []) if isinstance(p, dict)]
        posts_seen += len(posts)

        for post in posts:
            timestamp = _epoch_value(post.get("time"))
            if timestamp is not None and (
                max_epoch is None or timestamp > max_epoch
            ):
                max_epoch = timestamp

        if random_count > 0:
            target_post = _choose_post(posts, want_text=True, rng=rng)
            if target_post is not None:
                target_id = _text(target_post.get("no"))
                timestamp = _coerce_datetime(target_post.get("time"))
                if target_id and _in_window(timestamp, start, end):
                    month = _month_key(timestamp)
                    stratum = {"reason": "random", "month": month}
                    random_res[month].offer(
                        lambda thread=thread, post_id=target_id, st=stratum: (
                            _thread_sample(thread, post_id, st)
                        ),
                        rng,
                    )

        if include_empty > 0:
            target_post = _choose_post(posts, want_text=False, rng=rng)
            if target_post is not None:
                target_id = _text(target_post.get("no"))
                timestamp = _coerce_datetime(target_post.get("time"))
                if target_id and _in_window(timestamp, start, end):
                    month = _month_key(timestamp)
                    stratum = {"reason": "random_empty", "month": month}
                    empty_res[month].offer(
                        lambda thread=thread, post_id=target_id, st=stratum: (
                            _thread_sample(
                                thread,
                                post_id,
                                st,
                                require_text=False,
                            )
                        ),
                        rng,
                    )

        if targeted_count > 0:
            for post in posts:
                com = post.get("com")
                if not isinstance(com, str) or not com.strip():
                    continue

                matched = _match_frames(com)
                if not matched:
                    continue

                target_id = _text(post.get("no"))
                timestamp = _coerce_datetime(post.get("time"))
                if not target_id or not _in_window(timestamp, start, end):
                    continue

                month = _month_key(timestamp)
                for frame, term in matched.items():
                    stratum = {
                        "reason": "targeted",
                        "frame": frame,
                        "term": term,
                        "month": month,
                    }
                    target_res[frame][month].offer(
                        lambda thread=thread, post_id=target_id, st=stratum: (
                            _thread_sample(thread, post_id, st)
                        ),
                        rng,
                    )

        if threads % 100_000 == 0:
            log.info(
                "ROTLK stream: %d threads, %d posts, %.0f s",
                threads,
                posts_seen,
                time.monotonic() - started,
            )

        if limit_threads is not None and threads >= int(limit_threads):
            log.info("Stopped ROTLK stream after %d threads", threads)
            break

    log.info(
        "ROTLK stream finished: %d threads, %d posts in %.1f s",
        threads,
        posts_seen,
        time.monotonic() - started,
    )

    if max_epoch is None and start is None:
        log.warning("No timestamps found in %s", path)
        return []

    if start is not None:
        cutoff = start
        window_end = end
    else:
        max_ts = _coerce_datetime(max_epoch)
        if max_ts is None:
            log.warning("Could not interpret dataset timestamp in %s", path)
            return []
        cutoff = _cutoff(months, max_ts)
        window_end = end

    log.info(
        "ROTLK window: %s -> %s",
        cutoff.isoformat(),
        window_end.isoformat() if window_end else "(latest in dump)",
    )

    samples: list[SamplePost] = []
    used_posts: set[str] = set()
    used_threads: set[str] = set()
    used_hashes: set[str] = set()

    # Random sample: preserve the per-month allocation used by the parquet
    # sampler, but read each month's reservoir from the single pass.
    if random_count > 0:
        eligible = {
            month: _windowed(reservoir.items, cutoff, window_end)
            for month, reservoir in random_res.items()
            if month != "unknown"
        }
        months_present = sorted(
            month for month, items in eligible.items() if items
        )
        allocation = _allocate_counts(random_count, months_present, rng)
        for month in sorted(allocation):
            need = allocation[month]
            if need <= 0:
                continue

            candidates = list(eligible[month])
            rng.shuffle(candidates)
            picked = 0
            for sample in candidates:
                if picked >= need:
                    break
                if sample.post_id in used_posts or sample.thread_id in used_threads:
                    continue
                if sample.content_hash in used_hashes:
                    continue
                samples.append(sample)
                used_posts.add(sample.post_id)
                used_threads.add(sample.thread_id)
                used_hashes.add(sample.content_hash)
                picked += 1

            if picked < need:
                log.warning(
                    "Only %d/%d random ROTLK posts available for %s",
                    picked,
                    need,
                    month,
                )

        # Copypasta across threads can leave a month short after dedupe.
        # Redistribute the deficit over months that still have candidates.
        if len(samples) < random_count:
            shortfall = random_count - len(samples)
            log.warning(
                "Redistributing %d short random ROTLK posts across months",
                shortfall,
            )
            pools = {
                month: [
                    candidate
                    for candidate in eligible[month]
                    if candidate.post_id not in used_posts
                    and candidate.thread_id not in used_threads
                    and candidate.content_hash not in used_hashes
                ]
                for month in sorted(eligible)
            }
            for pool in pools.values():
                rng.shuffle(pool)

            added = 0
            while added < shortfall:
                progressed = False
                for month in sorted(pools):
                    if added >= shortfall:
                        break
                    pool = pools[month]
                    while pool:
                        sample = pool.pop()
                        if (
                            sample.post_id in used_posts
                            or sample.thread_id in used_threads
                            or sample.content_hash in used_hashes
                        ):
                            continue
                        samples.append(sample)
                        used_posts.add(sample.post_id)
                        used_threads.add(sample.thread_id)
                        used_hashes.add(sample.content_hash)
                        added += 1
                        progressed = True
                        break
                if not progressed:
                    break

            if added < shortfall:
                log.warning(
                    "Only %d/%d random ROTLK posts sampled after redistribution",
                    len(samples),
                    random_count,
                )

    # Targeted sample: collect candidates from the window, then take a
    # balanced number per frame while avoiding threads already selected.
    if targeted_count > 0:
        pools: dict[str, list[SamplePost]] = {}
        for frame in frames:
            by_month = target_res[frame]
            candidates = _windowed(
                (
                    sample
                    for month in sorted(by_month)
                    if month != "unknown"
                    for sample in by_month[month].items
                ),
                cutoff,
                window_end,
            )
            rng.shuffle(candidates)
            pools[frame] = candidates

        per_frame: Counter[str] = Counter()
        targeted_added = 0

        def take(frame: str) -> SamplePost | None:
            while pools[frame]:
                sample = pools[frame].pop()
                if sample.post_id in used_posts or sample.thread_id in used_threads:
                    continue
                if sample.content_hash in used_hashes:
                    continue
                used_posts.add(sample.post_id)
                used_threads.add(sample.thread_id)
                used_hashes.add(sample.content_hash)
                per_frame[frame] += 1
                return sample
            return None

        for frame in frames:
            while (
                per_frame[frame] < frame_quota[frame]
                and targeted_added < targeted_count
            ):
                sample = take(frame)
                if sample is None:
                    break
                samples.append(sample)
                targeted_added += 1

        while targeted_added < targeted_count:
            progressed = False
            for frame in frames:
                if targeted_added >= targeted_count:
                    break
                sample = take(frame)
                if sample is not None:
                    samples.append(sample)
                    targeted_added += 1
                    progressed = True
            if not progressed:
                break

        if targeted_added < targeted_count:
            log.warning(
                "Only %d/%d targeted ROTLK posts sampled",
                targeted_added,
                targeted_count,
            )

    # Deliberately keep a few empty/media-only posts if requested.
    if include_empty > 0:
        empty_added = 0
        candidates = _windowed(
            (
                sample
                for month in sorted(empty_res)
                if month != "unknown"
                for sample in empty_res[month].items
            ),
            cutoff,
            window_end,
        )
        rng.shuffle(candidates)
        for sample in candidates:
            if empty_added >= include_empty:
                break
            if sample.post_id in used_posts or sample.thread_id in used_threads:
                continue
            if sample.content_hash in used_hashes:
                continue
            samples.append(sample)
            used_posts.add(sample.post_id)
            used_threads.add(sample.thread_id)
            used_hashes.add(sample.content_hash)
            empty_added += 1

        if empty_added < include_empty:
            log.warning(
                "Only %d/%d empty ROTLK posts sampled",
                empty_added,
                include_empty,
            )

    return samples
