# Role: LLM backends for local silver annotation (llama.cpp plus a test fake).
# Connects to: classification/batch, classification/manifest, common/paths.

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

from keklab.classification.errors import (
    BackendError,
    SystemicError,
    TransportError,
    classify_message,
)
from keklab.common.paths import DEFAULT_LLM_MODEL


class LLMBackend(Protocol):
    name: str
    provider: str

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        ...


class FakeBackend:
    """Deterministic backend for tests and dry runs."""

    name = "fake"
    provider = "test"

    def __init__(
        self,
        responses: Iterable[str] | Callable[[str], str],
        *,
        name: str = "fake",
    ) -> None:
        if callable(responses):
            self._callable = responses
            self._responses: Sequence[str] | None = None
        else:
            self._callable = None
            self._responses = list(responses)
            self._index = 0
        self.name = name
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        self.prompts.append(prompt)
        if self._callable is not None:
            return str(self._callable(prompt))
        assert self._responses is not None
        if self._index >= len(self._responses):
            raise RuntimeError("FakeBackend ran out of responses")
        response = self._responses[self._index]
        self._index += 1
        return response


class LlamaCppBackend:
    """Lazy wrapper around `llama_cpp.Llama` for chat-completion inference.

    The import is deferred so the rest of `keklab` works without the optional
    dependency. `disable_thinking` appends `/no_think` for Qwen3 models; the
    flag is also recorded in the run manifest.
    """

    provider = "llama.cpp"

    def __init__(
        self,
        model_path: str | Path = DEFAULT_LLM_MODEL,
        *,
        n_ctx: int = 2048,
        n_batch: int = 256,
        n_gpu_layers: int = 0,
        temperature: float = 0.0,
        seed: int = 13,
        max_tokens: int = 512,
        disable_thinking: bool = True,
        verbose: bool = False,
    ) -> None:
        self.model_path = Path(model_path).expanduser()
        self.name = self.model_path.name
        self.n_ctx = int(n_ctx)
        self.n_batch = int(n_batch)
        self.n_gpu_layers = int(n_gpu_layers)
        self.temperature = float(temperature)
        self.seed = int(seed)
        self.max_tokens = int(max_tokens)
        self.disable_thinking = bool(disable_thinking)
        self.verbose = bool(verbose)
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"GGUF model not found: {self.model_path}. "
                "Put it in models/gguf/ or set KEKLAB_MODELS_DIR."
            )
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "llama-cpp-python is not installed in this environment"
            ) from exc

        self._model = Llama(
            model_path=str(self.model_path),
            n_ctx=self.n_ctx,
            n_batch=self.n_batch,
            n_gpu_layers=self.n_gpu_layers,
            seed=self.seed,
            verbose=self.verbose,
        )
        return self._model

    def _prepare_prompt(self, prompt: str) -> str:
        if self.disable_thinking and "qwen3" in self.name.lower():
            return prompt.rstrip() + "\n\n/no_think"
        return prompt

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        model = self._load()
        messages = [{"role": "user", "content": self._prepare_prompt(prompt)}]
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
        }
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object", "schema": schema}

        try:
            response = model.create_chat_completion(**kwargs)
        except TypeError:
            # Older llama-cpp-python builds do not accept `schema`.
            kwargs.pop("response_format", None)
            response = model.create_chat_completion(**kwargs)

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected llama.cpp response: {response!r}") from exc
        return str(content or "")

    def metadata(self) -> dict[str, Any]:
        model = self._load()
        from keklab.classification.manifest import chat_template_sha256

        return {
            "model_path": str(self.model_path),
            "model_file": self.model_path.name,
            "provider": self.provider,
            "n_ctx": self.n_ctx,
            "n_batch": self.n_batch,
            "n_gpu_layers": self.n_gpu_layers,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "disable_thinking": self.disable_thinking,
            "chat_template_sha256": chat_template_sha256(model),
        }


class LlamaServerBackend:
    """HTTP client for `llama-server`'s OpenAI-compatible chat endpoint.

    The server owns the model and context; this class only sends one chat
    completion per task. `disable_thinking` is forwarded as a chat-template
    kwarg so Qwen3 does not emit reasoning tokens, and `schema` is sent as a
    llama.cpp JSON response format when supported.
    """

    provider = "llama.cpp-server"

    def __init__(
        self,
        model_path: str | Path = DEFAULT_LLM_MODEL,
        *,
        base_url: str = "http://127.0.0.1:8080",
        n_ctx: int = 2048,
        n_batch: int = 256,
        n_gpu_layers: int = -1,
        temperature: float = 0.0,
        seed: int = 13,
        max_tokens: int = 512,
        disable_thinking: bool = True,
        timeout: float = 180.0,
    ) -> None:
        self.model_path = Path(model_path).expanduser()
        self.name = self.model_path.name
        self.base_url = str(base_url).rstrip("/")
        self.n_ctx = int(n_ctx)
        self.n_batch = int(n_batch)
        self.n_gpu_layers = int(n_gpu_layers)
        self.temperature = float(temperature)
        self.seed = int(seed)
        self.max_tokens = int(max_tokens)
        self.disable_thinking = bool(disable_thinking)
        self.timeout = float(timeout)
        self._props: dict[str, Any] | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            message = f"llama-server HTTP {exc.code} at {path}: {detail[:800]}"
            kind = classify_message(detail)
            if kind == "systemic":
                raise SystemicError(message) from exc
            if exc.code >= 500 or exc.code == 429:
                raise TransportError(message) from exc
            raise BackendError(message) from exc
        except urllib.error.URLError as exc:
            raise TransportError(
                f"llama-server unreachable at {self.base_url}: {exc.reason}"
            ) from exc
        except (TimeoutError, ConnectionError) as exc:
            raise TransportError(
                f"llama-server connection failed at {self.base_url}: {exc}"
            ) from exc

        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackendError(
                f"llama-server returned non-JSON at {path}: {body[:300]!r}"
            ) from exc
        if not isinstance(value, dict):
            raise BackendError(
                f"llama-server returned {type(value).__name__} at {path}"
            )
        return value

    def health(self) -> dict[str, Any]:
        return self._request("/health")

    def props(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._props is None or refresh:
            self._props = self._request("/props")
        return self._props

    def _count_tokens(self, text: str) -> tuple[int, str]:
        """Count prompt tokens with the server tokenizer, else estimate.

        `llama-server` exposes `/tokenize`, so the count is exact when the
        server is reachable. The fallback keeps the guard usable offline.
        """
        try:
            value = self._request("/tokenize", {"content": text})
            tokens = value.get("tokens")
            if isinstance(tokens, list):
                return len(tokens), "server"
        except BackendError:
            pass
        return max(1, math.ceil(len(text) / 3.5)), "estimate"

    def context_report(
        self,
        prompts: Sequence[str],
        *,
        repair_overhead_tokens: int = 384,
        template_overhead_tokens: int = 16,
    ) -> dict[str, Any]:
        """Check that the longest prompt fits one server slot.

        `llama-server` divides the total `n_ctx` across its parallel slots.
        A prompt that fits the total context but not one slot fails with
        `Context size has been exceeded`, so the guard compares against the
        per-slot budget, including room for the repair prompt and output.
        """
        props = self.props()
        generation = props.get("default_generation_settings") or {}
        total_slots = int(
            props.get("total_slots") or props.get("n_parallel") or 1
        )
        total_slots = max(1, total_slots)
        n_ctx = int(
            props.get("n_ctx") or generation.get("n_ctx") or self.n_ctx
        )
        per_slot_ctx = max(1, n_ctx // total_slots)

        # The worst case is the prompt with the most *tokens*, not the most
        # characters: dense Unicode/art posts can exceed one token per char and
        # a char-based pick silently underestimates the budget.
        if prompts:
            longest_by_chars = max(prompts, key=len)
            probe_tokens, method = self._count_tokens(longest_by_chars)
            if method == "server":
                prompt_tokens = probe_tokens
                longest = longest_by_chars
                for prompt in prompts:
                    if prompt is longest_by_chars:
                        continue
                    count, _ = self._count_tokens(prompt)
                    if count > prompt_tokens:
                        prompt_tokens, longest = count, prompt
            else:
                prompt_tokens, _, longest = max(
                    (
                        (max(1, math.ceil(len(prompt) / 3.5)), len(prompt), prompt)
                        for prompt in prompts
                    ),
                    key=lambda item: item[0],
                )
        else:
            prompt_tokens, method, longest = 1, "estimate", ""
        required = (
            prompt_tokens
            + template_overhead_tokens
            + repair_overhead_tokens
            + self.max_tokens
        )
        return {
            "n_ctx": n_ctx,
            "total_slots": total_slots,
            "per_slot_ctx": per_slot_ctx,
            "longest_prompt_chars": len(longest),
            "longest_prompt_tokens": prompt_tokens,
            "token_count_method": method,
            "template_overhead_tokens": template_overhead_tokens,
            "repair_overhead_tokens": repair_overhead_tokens,
            "max_tokens": self.max_tokens,
            "required_tokens": required,
            "headroom_tokens": per_slot_ctx - required,
            "fits": required <= per_slot_ctx,
        }

    def _response_formats(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"type": "json_object", "schema": schema},
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "keklab_annotation",
                    "schema": schema,
                    "strict": True,
                },
            },
        ]

    def _message_text(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            content = "".join(parts)
        text = str(content or "")
        if text.strip():
            return text
        if message.get("reasoning_content"):
            raise RuntimeError(
                "empty content with reasoning_content present; "
                "the server is still thinking (check enable_thinking)"
            )
        raise RuntimeError("llama-server returned empty message content")

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
            "stream": False,
        }
        if self.disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        formats: list[dict[str, Any] | None]
        if schema is None:
            formats = [None]
        else:
            formats = list(self._response_formats(schema))

        response: dict[str, Any] | None = None
        last_error: Exception | None = None
        for response_format in formats:
            attempt = dict(payload)
            if response_format is not None:
                attempt["response_format"] = response_format
            try:
                response = self._request("/v1/chat/completions", attempt)
                break
            except (SystemicError, TransportError):
                # Retrying a different response_format cannot fix a dead
                # server or an exhausted context.
                raise
            except BackendError as exc:
                last_error = exc
                if response_format is not None and "response_format" in str(exc).lower():
                    continue
                raise

        if response is None:
            raise last_error or RuntimeError("llama-server request failed")

        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"unexpected llama-server response: {response!r}"
            ) from exc
        return self._message_text(message)

    def preflight(self) -> dict[str, Any]:
        from keklab.classification.manifest import sha256_text

        report: dict[str, Any] = {
            "base_url": self.base_url,
            "model_path": str(self.model_path),
            "model_file": self.model_path.name,
            "model_file_exists": self.model_path.exists(),
            "model_file_size": (
                self.model_path.stat().st_size
                if self.model_path.exists()
                else None
            ),
            "reachable": False,
            "health": None,
            "server": {},
            "checks": {},
        }

        try:
            report["health"] = self.health()
            report["reachable"] = True
        except Exception as exc:  # noqa: BLE001 - report instead of raising
            report["error"] = f"{type(exc).__name__}: {exc}"

        props: dict[str, Any] = {}
        if report["reachable"]:
            try:
                props = self.props(refresh=True)
            except Exception as exc:  # noqa: BLE001
                report["error"] = f"{type(exc).__name__}: {exc}"

        generation = props.get("default_generation_settings") or {}
        server_n_ctx = props.get("n_ctx") or generation.get("n_ctx")
        total_slots = int(
            props.get("total_slots") or props.get("n_parallel") or 1
        )
        total_slots = max(1, total_slots)
        chat_template = props.get("chat_template")
        server_model_path = props.get("model_path")
        server_model_file = (
            Path(str(server_model_path)).name if server_model_path else None
        )
        report["server"] = {
            "model_path": server_model_path,
            "model_file": server_model_file,
            "model_alias": props.get("model_alias"),
            "n_ctx": server_n_ctx,
            "total_slots": total_slots,
            "per_slot_ctx": (
                int(server_n_ctx) // total_slots if server_n_ctx else None
            ),
            "n_batch": props.get("n_batch") or generation.get("n_batch"),
            "build_info": props.get("build_info"),
            "chat_template_sha256": (
                sha256_text(str(chat_template)) if chat_template else None
            ),
        }

        report["checks"] = {
            "server_reachable": report["reachable"],
            "model_loaded": bool(server_model_path or props.get("model_alias")),
            "model_file_exists": report["model_file_exists"],
            "model_name_matches_server": (
                server_model_file == self.model_path.name
                if server_model_file
                else None
            ),
            "context_reported": bool(server_n_ctx),
            "thinking_toggle_supported": (
                "enable_thinking" in str(chat_template)
                if chat_template
                else None
            ),
        }
        report["ok"] = bool(
            report["checks"]["server_reachable"]
            and report["checks"]["model_loaded"]
        )
        return report

    def metadata(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        try:
            props = self.props()
        except Exception:  # noqa: BLE001 - manifest still records local settings
            pass

        from keklab.classification.manifest import sha256_text

        generation = props.get("default_generation_settings") or {}
        chat_template = props.get("chat_template")
        return {
            "model_path": str(self.model_path),
            "model_file": self.model_path.name,
            "provider": self.provider,
            "base_url": self.base_url,
            "n_ctx": props.get("n_ctx") or generation.get("n_ctx") or self.n_ctx,
            "n_batch": (
                props.get("n_batch") or generation.get("n_batch") or self.n_batch
            ),
            "n_gpu_layers": self.n_gpu_layers,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "disable_thinking": self.disable_thinking,
            "server_model_path": props.get("model_path"),
            "server_model_alias": props.get("model_alias"),
            "server_build_info": props.get("build_info"),
            "chat_template_sha256": (
                sha256_text(str(chat_template)) if chat_template else None
            ),
        }
