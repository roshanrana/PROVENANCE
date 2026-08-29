"""A stub vLLM engine.

ATTEST cannot run on any machine this project has — batch invariance needs an
NVIDIA GPU of compute capability 8.0 or higher (requirements §6.1). Without this
stub, no ATTEST code could be exercised until GPU day, which would put every
integration bug on the most expensive hardware in the project.

Two capabilities make it worth more than a plain mock:

* **It can fake divergence on demand.** ``divergence_mode="batch_dependent"``
  makes output depend on concurrent in-flight request count, mimicking the real
  phenomenon deterministically. That lets divergence analysis be tested against a
  known-correct answer instead of against hope.
* **Its resolved config deliberately differs from the request.** D-08 says
  receipts must bind what the engine *resolved*, not what the operator asked for.
  If the stub echoed the request back, a bug that recorded intent instead of
  reality would pass every test.

Test infrastructure only — never importable from a production path.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import urlparse

DivergenceMode = Literal["none", "batch_dependent", "random"]

VERSION = "0.11.0-stub"
GIT_SHA = "5tub5ha"
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"


@dataclass
class StubConfig:
    divergence_mode: DivergenceMode = "none"
    #: Values the "engine" resolved to, which must NOT match what a caller asked for.
    resolved_config_overrides: dict[str, Any] = field(
        default_factory=lambda: {
            "cudagraph_mode": "PIECEWISE",
            "enforce_eager": False,
            "max_num_seqs": 256,
        }
    )
    latency_profile: Literal["instant", "fixed", "jittered"] = "instant"
    fixed_latency_s: float = 0.0
    #: Block each request until this many are in flight. Makes concurrency a
    #: guarantee rather than a scheduler coincidence, so tests that need overlap
    #: are deterministic instead of flaky.
    hold_until_inflight: int = 0
    #: Deliberately shorter than any client timeout, so a barrier that cannot be
    #: satisfied surfaces as a failed assertion rather than a client read timeout.
    hold_timeout_s: float = 3.0
    batch_invariant: bool = False
    prefix_caching: bool = False


class _State:
    def __init__(self, config: StubConfig) -> None:
        self.config = config
        self.inflight = 0
        self.peak_inflight = 0
        self.requests = 0
        self.lock = threading.Condition()


def _tokens_for(prompt: str, seed: int, bucket: int, n: int) -> list[int]:
    """Deterministic pseudo-tokens from (prompt, seed, concurrency bucket)."""
    digest = hashlib.sha256(f"{prompt}|{seed}|{bucket}".encode()).digest()
    return [1000 + digest[i % len(digest)] for i in range(n)]


def _bucket_for(batch_size: int) -> int:
    """Buckets mirror how real kernels pick reduction strategies at different
    batch shapes: 1, 2-4, 5-8, 9+."""
    n = batch_size
    return 0 if n <= 1 else 1 if n <= 4 else 2 if n <= 8 else 3


def _concurrency_bucket(state: _State, mode: DivergenceMode, *, batch_size: int) -> int:
    if mode == "none":
        return 0
    if mode == "batch_dependent":
        return _bucket_for(batch_size)
    return state.requests  # "random": different every call


class _Handler(BaseHTTPRequestHandler):
    state: _State

    def log_message(self, *_args: Any) -> None:  # keep test output clean
        return

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/version":
            self._send(200, {"version": VERSION, "git_sha": GIT_SHA})
        elif path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": MODEL_ID}]})
        elif path == "/_stub/resolved_config":
            cfg = self.state.config
            self._send(
                200,
                {
                    "resolved_config": dict(cfg.resolved_config_overrides),
                    "attention_backend": "FLASH_ATTN",
                    "batch_invariant": cfg.batch_invariant,
                    "prefix_caching": cfg.prefix_caching,
                    "speculative_decoding": False,
                    "tensor_parallel_size": 1,
                },
            )
        elif path == "/_stub/stats":
            self._send(
                200,
                {"requests": self.state.requests, "peak_inflight": self.state.peak_inflight},
            )
        else:
            self._send(404, {"error": f"no such path: {path}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/v1/completions":
            self._send(404, {"error": f"no such path: {path}"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._send(400, {"error": f"invalid JSON: {exc}"})
            return

        state = self.state
        with state.lock:
            state.inflight += 1
            state.requests += 1
            state.peak_inflight = max(state.peak_inflight, state.inflight)
            target = state.config.hold_until_inflight
            batch_size = state.inflight
            if target > 1:
                state.lock.notify_all()
                reached = state.lock.wait_for(
                    lambda: state.inflight >= target, timeout=state.config.hold_timeout_s
                )
                state.peak_inflight = max(state.peak_inflight, state.inflight)
                # The barrier defines the batch shape. Reading `inflight` after
                # waking would race: peers wake at different moments and some
                # have already finished, so each caller would see a different
                # number and land in a different bucket — which is precisely the
                # non-determinism this fixture is meant to control, not exhibit.
                batch_size = target if reached else state.inflight
            bucket = _concurrency_bucket(state, state.config.divergence_mode, batch_size=batch_size)
        try:
            cfg = state.config
            if cfg.latency_profile == "fixed":
                time.sleep(cfg.fixed_latency_s)
            elif cfg.latency_profile == "jittered":
                time.sleep(cfg.fixed_latency_s * (1.0 + 0.1 * (state.requests % 3)))

            prompt = body.get("prompt", "")
            seed = int(body.get("seed", 0))
            max_tokens = int(body.get("max_tokens", 16))
            token_ids = _tokens_for(prompt, seed, bucket, max_tokens)
            # Logprobs are a deterministic function of the tokens, so a
            # divergent completion also has divergent logprobs — as on real
            # hardware, where the bits differ before the text does.
            logprobs = [-round(0.001 * t, 6) for t in token_ids]
            self._send(
                200,
                {
                    "id": f"cmpl-{state.requests:06d}",
                    "model": body.get("model", MODEL_ID),
                    "choices": [
                        {
                            "index": 0,
                            "text": " ".join(f"t{t}" for t in token_ids),
                            "token_ids": token_ids,
                            "logprobs": {"token_logprobs": logprobs},
                            "finish_reason": "length",
                        }
                    ],
                    "_stub": {"bucket": bucket, "cache_salt": body.get("cache_salt")},
                },
            )
        finally:
            with state.lock:
                state.inflight -= 1
                state.lock.notify_all()


@dataclass
class RunningStub:
    url: str
    state: _State

    @property
    def requests(self) -> int:
        return self.state.requests


@contextmanager
def stub_engine(config: StubConfig | None = None) -> Iterator[RunningStub]:
    """Run the stub on an ephemeral port for the duration of the context."""
    state = _State(config or StubConfig())
    handler = type("_Bound", (_Handler,), {"state": state})
    # The stdlib default listen backlog is 5. A barrier test needs every client
    # connection to actually reach a handler thread, or it deadlocks waiting for
    # peers that are still queued in the kernel.
    server = type(
        "_Server", (ThreadingHTTPServer,), {"request_queue_size": 256, "daemon_threads": True}
    )(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        hostname = host.decode() if isinstance(host, bytes) else str(host)
        yield RunningStub(url=f"http://{hostname}:{port}", state=state)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
