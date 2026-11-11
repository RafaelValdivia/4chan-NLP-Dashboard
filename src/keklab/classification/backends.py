# Role: LLM backends for local silver annotation (llama.cpp plus a test fake).
# Connects to: classification/batch, classification/manifest, common/paths.

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

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
