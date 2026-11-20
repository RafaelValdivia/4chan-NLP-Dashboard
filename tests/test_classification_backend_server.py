from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from keklab.classification.backends import LlamaServerBackend
from keklab.classification.errors import SystemicError, TransportError
from keklab.classification.grammar import output_json_schema


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    mode = "ok"
    total_slots = 1

    def log_message(self, *args: object) -> None:  # noqa: D102 - silence stderr
        return

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/health":
            self._send({"status": "ok"})
        elif self.path == "/props":
            self._send(
                {
                    "model_path": "/models/Qwen3-8B-Q4_K_M.gguf",
                    "model_alias": "qwen3",
                    "n_ctx": 4096,
                    "n_batch": 512,
                    "total_slots": type(self).total_slots,
                    "build_info": "b12255",
                    "chat_template": "{% if enable_thinking %}think{% endif %}",
                }
            )
        else:
            self._send({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))

        if self.path == "/tokenize":
            content = str(payload.get("content") or "")
            self._send({"tokens": list(range(len(content.split())))})
            return

        type(self).requests.append(payload)

        if type(self).mode == "context_exceeded":
            self._send(
                {
                    "error": {
                        "message": (
                            "Context size has been exceeded. "
                            "off = 244, n_batch = 1"
                        )
                    }
                },
                status=500,
            )
            return

        if type(self).mode == "reject_response_format":
            response_format = payload.get("response_format") or {}
            if response_format.get("type") == "json_object":
                self._send({"error": "response_format not supported"}, status=400)
                return

        content = json.dumps({"post_id": "1", "frame_labels": ["none"]})
        self._send(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }
                ]
            }
        )


@pytest.fixture()
def server():
    _Handler.requests = []
    _Handler.mode = "ok"
    _Handler.total_slots = 1
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def make_backend(server: str, **kwargs) -> LlamaServerBackend:
    defaults = {
        "model_path": "/models/Qwen3-8B-Q4_K_M.gguf",
        "base_url": server,
        "timeout": 10.0,
    }
    defaults.update(kwargs)
    return LlamaServerBackend(**defaults)


def test_generate_sends_thinking_flag_and_schema(server):
    backend = make_backend(server)

    result = backend.generate("annotate this", schema=output_json_schema())

    assert json.loads(result)["frame_labels"] == ["none"]
    request = _Handler.requests[-1]
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    assert request["temperature"] == 0.0
    assert request["seed"] == 13
    assert request["response_format"]["type"] == "json_object"
    assert request["response_format"]["schema"]["required"] == [
        "post_id",
        "frame_labels",
        "toxicity",
    ]


def test_generate_can_keep_thinking(server):
    backend = make_backend(server, disable_thinking=False)

    backend.generate("annotate this")

    assert "chat_template_kwargs" not in _Handler.requests[-1]


def test_generate_falls_back_to_openai_json_schema(server):
    _Handler.mode = "reject_response_format"
    backend = make_backend(server)

    result = backend.generate("annotate this", schema=output_json_schema())

    assert json.loads(result)["post_id"] == "1"
    formats = [request.get("response_format") for request in _Handler.requests]
    assert formats[0]["type"] == "json_object"
    assert formats[1]["type"] == "json_schema"


def test_generate_raises_when_server_is_unreachable():
    backend = make_backend("http://127.0.0.1:9", timeout=2.0)

    with pytest.raises(TransportError, match="unreachable"):
        backend.generate("annotate this")


def test_generate_raises_systemic_on_context_overflow(server):
    _Handler.mode = "context_exceeded"
    backend = make_backend(server)

    with pytest.raises(SystemicError, match="Context size"):
        backend.generate("annotate this", schema=output_json_schema())

    # The systemic error must not trigger the response_format fallback.
    assert len(_Handler.requests) == 1


def test_context_report_uses_server_slots_and_tokenizer(server):
    backend = make_backend(server, max_tokens=512)

    report = backend.context_report(["a b c d e f g h i j"])

    assert report["n_ctx"] == 4096
    assert report["total_slots"] == 1
    assert report["per_slot_ctx"] == 4096
    assert report["longest_prompt_tokens"] == 10
    assert report["token_count_method"] == "server"
    assert report["required_tokens"] == 10 + 16 + 384 + 512
    assert report["fits"] is True


def test_context_report_picks_longest_by_tokens_not_chars(server):
    backend = make_backend(server, max_tokens=512)

    # One long single word and one short multi-word prompt: the char-based
    # pick would miss the token-based worst case.
    report = backend.context_report(["x" * 3000, " ".join(["word"] * 20)])

    assert report["longest_prompt_tokens"] == 20
    assert report["longest_prompt_chars"] == len(" ".join(["word"] * 20))


def test_context_report_rejects_prompt_that_exceeds_one_slot(server):
    _Handler.total_slots = 4
    backend = make_backend(server, max_tokens=512)
    long_prompt = " ".join(["word"] * 2000)

    report = backend.context_report([long_prompt])

    assert report["per_slot_ctx"] == 1024
    assert report["required_tokens"] > 1024
    assert report["fits"] is False
    assert report["headroom_tokens"] < 0


def test_preflight_reports_slots_and_per_slot_context(server):
    _Handler.total_slots = 4
    backend = make_backend(server)

    report = backend.preflight()

    assert report["server"]["total_slots"] == 4
    assert report["server"]["per_slot_ctx"] == 1024


def test_preflight_reports_server_state(server):
    backend = make_backend(server)

    report = backend.preflight()

    assert report["reachable"] is True
    assert report["ok"] is True
    assert report["checks"]["model_loaded"] is True
    assert report["checks"]["thinking_toggle_supported"] is True
    assert report["server"]["n_ctx"] == 4096
    assert report["server"]["model_file"] == "Qwen3-8B-Q4_K_M.gguf"


def test_preflight_fails_without_server():
    backend = make_backend("http://127.0.0.1:9", timeout=2.0)

    report = backend.preflight()

    assert report["reachable"] is False
    assert report["ok"] is False
    assert "error" in report
