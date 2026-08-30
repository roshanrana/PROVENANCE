"""Engine client — the boundary between the harness and vLLM.

M0 scope. This exercises the *interface* end to end against the stub; T-018
extends it with real vLLM process lifecycle (launch, env, readiness, teardown).
The split is deliberate: the walking skeleton must run in CI with no GPU, so the
interface gets proven while the expensive part is still unwritten.

D-08 lives here. :meth:`EngineClient.resolved_state` reads back what the engine
actually resolved rather than echoing what we asked for — because
``override_envs_for_invariance()`` mutates the environment, so intended and
actual differ, and a receipt that binds intent is a log line.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from attest.receipt.schema import EngineState, OutputRecord, SamplingParams


class EngineError(RuntimeError):
    """The engine could not be reached, or answered in a way we cannot use.

    Never swallowed: a degraded run produces a plausible wrong number, which is
    the worst outcome available to this project (HLD §8.4).
    """


def logprobs_digest(logprobs: Sequence[float]) -> str:
    """Bitwise digest of the logprob vector.

    Bitwise, not rounded: FR-A-03's claim is bitwise identity, and a tolerant
    comparison here would quietly weaken the headline result.
    """
    import struct

    payload = b"".join(struct.pack("<d", float(x)) for x in logprobs)
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Completion:
    token_ids: list[int]
    text: str
    logprobs: list[float]

    def to_output_record(self) -> OutputRecord:
        return OutputRecord(
            token_ids=self.token_ids,
            text=self.text,
            logprobs_sha256=logprobs_digest(self.logprobs),
        )


class EngineClient:
    """Minimal client over the vLLM OpenAI-compatible surface."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EngineClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = self._client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineError(f"GET {path} failed: {type(exc).__name__}: {exc}") from exc

    def version(self) -> tuple[str, str]:
        payload = self._get("/version")
        return payload.get("version", "unknown"), payload.get("git_sha", "unknown")

    def resolved_state(self) -> EngineState:
        """Read back the engine's resolved configuration (D-08)."""
        payload = self._get("/_stub/resolved_config")
        version, git_sha = self.version()
        try:
            return EngineState(
                vllm_version=version,
                vllm_git_sha=git_sha,
                resolved_config=payload["resolved_config"],
                attention_backend=payload["attention_backend"],
                batch_invariant=bool(payload["batch_invariant"]),
                prefix_caching=bool(payload["prefix_caching"]),
                speculative_decoding=bool(payload["speculative_decoding"]),
                tensor_parallel_size=int(payload["tensor_parallel_size"]),
            )
        except KeyError as exc:
            raise EngineError(f"engine did not report resolved config field: {exc}") from exc

    def complete(
        self,
        prompt: str,
        sampling: SamplingParams,
        *,
        model: str = "Qwen/Qwen2.5-0.5B-Instruct",
        cache_salt: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "seed": sampling.seed,
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": sampling.max_tokens,
            "logprobs": 1,
        }
        if cache_salt is not None:
            body["cache_salt"] = cache_salt
        if extra:
            body.update(extra)

        try:
            response = self._client.post(f"{self.base_url}/v1/completions", json=body)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineError(f"completion failed: {type(exc).__name__}: {exc}") from exc

        try:
            choice = payload["choices"][0]
            return Completion(
                token_ids=[int(t) for t in choice["token_ids"]],
                text=choice["text"],
                logprobs=[float(x) for x in choice["logprobs"]["token_logprobs"]],
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise EngineError(f"unusable completion payload: {exc}") from exc
