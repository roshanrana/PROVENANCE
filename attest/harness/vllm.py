"""Real vLLM process lifecycle — T-018.

The one piece of ATTEST a stub cannot stand in for. Everything else was built and
tested against ``tests/support/stub_engine``; this is what replaces it on the
rented GPU.

Three things it must get right, all of them because GPU minutes are the scarce
resource and a silent misconfiguration is worse than a crash:

* **Environment is set before the process starts.** ``VLLM_BATCH_INVARIANT`` is
  read at import time, so setting it after launch does nothing at all — and the
  run would look fine while measuring the wrong thing.
* **Readiness is waited for, not slept through.** A fixed sleep either wastes
  minutes or races a slow model load.
* **Configuration is read back, never assumed** (D-08). vLLM's
  ``override_envs_for_invariance()`` mutates the environment, so what the engine
  resolved is not what we passed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from attest.harness.engine import EngineClient, EngineError
from attest.receipt.schema import EngineState

DEFAULT_PORT = 8000
DEFAULT_READY_TIMEOUT_S = 900.0  # a cold 7B load on a slow disk is minutes


class EngineLaunchError(RuntimeError):
    """The engine did not start, or started in a state we refuse to measure."""


@dataclass(frozen=True)
class VllmConfig:
    """A vLLM invocation. Everything here lands in the receipt."""

    model: str
    batch_invariant: bool
    #: D-06: pinned off for ATTEST's primary claim. Batch invariance and prefix
    #: caching are not integrated upstream, so a determinism claim made with APC
    #: in an unknown state is not a claim.
    enable_prefix_caching: bool = False
    tensor_parallel_size: int = 1
    port: int = DEFAULT_PORT
    host: str = "127.0.0.1"
    max_model_len: int | None = None
    gpu_memory_utilization: float = 0.90
    extra_args: tuple[str, ...] = ()
    extra_env: Mapping[str, str] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def command(self) -> list[str]:
        argv = [
            "vllm",
            "serve",
            self.model,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--tensor-parallel-size",
            str(self.tensor_parallel_size),
            "--gpu-memory-utilization",
            str(self.gpu_memory_utilization),
            "--seed",
            "0",
        ]
        # Prefix caching is stated explicitly in both directions. Relying on the
        # upstream default would leave the receipt's `prefix_caching` field
        # asserting something we never actually controlled.
        argv.append(
            "--enable-prefix-caching"
            if self.enable_prefix_caching
            else "--no-enable-prefix-caching"
        )
        argv.extend(self.extra_args)
        return argv

    def environment(self) -> dict[str, str]:
        """The child's environment.

        ``VLLM_BATCH_INVARIANT`` is read at import time inside vLLM, so it must be
        set here — before the process exists — not afterwards.
        """
        env = dict(os.environ)
        env["VLLM_BATCH_INVARIANT"] = "1" if self.batch_invariant else "0"
        # Speculative decoding is incompatible with batch invariance upstream, and
        # a run that quietly enabled it would produce a receipt asserting
        # something false.
        env.setdefault("VLLM_USE_V1", "1")
        env.update(self.extra_env)
        return env

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "batch_invariant": self.batch_invariant,
            "enable_prefix_caching": self.enable_prefix_caching,
            "tensor_parallel_size": self.tensor_parallel_size,
            "command": self.command(),
            "VLLM_BATCH_INVARIANT": "1" if self.batch_invariant else "0",
        }


def wait_until_ready(
    base_url: str, *, timeout_s: float = DEFAULT_READY_TIMEOUT_S, poll_s: float = 2.0
) -> None:
    """Poll ``/health`` until the engine answers, or give up loudly."""
    deadline = time.monotonic() + timeout_s
    last: str = "never attempted"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=5.0)
            if response.status_code == 200:
                return
            last = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(poll_s)
    raise EngineLaunchError(
        f"engine at {base_url} was not ready within {timeout_s:.0f}s (last: {last})"
    )


def read_resolved_state(
    base_url: str, config: VllmConfig, *, client: httpx.Client | None = None
) -> EngineState:
    """Read back what the engine resolved (D-08), and refuse a mismatch.

    The refusal is the point. If we asked for batch invariance and the engine did
    not enable it, every number in that run would be mislabelled — and mislabelled
    numbers are worse than missing ones, because they get published.
    """
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        version = http.get(f"{base_url}/version").json()
        # vLLM exposes its resolved engine arguments here; fields have moved
        # between releases, so we read defensively and record what we find.
        try:
            response = http.get(f"{base_url}/v1/server_info")
            response.raise_for_status()
            resolved: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError):
            resolved = {}
    except (httpx.HTTPError, ValueError) as exc:
        raise EngineLaunchError(f"could not read engine state: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    observed_invariant = _observed_batch_invariance(resolved, config)
    if observed_invariant is not None and observed_invariant != config.batch_invariant:
        raise EngineLaunchError(
            f"engine reports batch_invariant={observed_invariant} but the run "
            f"requested {config.batch_invariant}. Refusing to measure: every "
            "number from this engine would carry the wrong label."
        )

    return EngineState(
        vllm_version=str(version.get("version", "unknown")),
        vllm_git_sha=str(version.get("git_sha", resolved.get("vllm_commit", "unknown"))),
        resolved_config=resolved or {"note": "engine exposed no server_info endpoint"},
        attention_backend=str(
            resolved.get("attention_backend") or os.environ.get("VLLM_ATTENTION_BACKEND", "unknown")
        ),
        batch_invariant=config.batch_invariant
        if observed_invariant is None
        else observed_invariant,
        prefix_caching=bool(resolved.get("enable_prefix_caching", config.enable_prefix_caching)),
        speculative_decoding=bool(resolved.get("speculative_config") or False),
        tensor_parallel_size=int(resolved.get("tensor_parallel_size", config.tensor_parallel_size)),
    )


def _observed_batch_invariance(resolved: Mapping[str, Any], config: VllmConfig) -> bool | None:
    """Best-effort read of the engine's actual invariance state.

    Returns ``None`` when the engine exposes nothing usable — in which case the
    receipt records what we set, and the writeup must say the readback was
    unavailable rather than implying it was confirmed.
    """
    for key in ("batch_invariant", "vllm_batch_invariant", "VLLM_BATCH_INVARIANT"):
        if key in resolved:
            value = resolved[key]
            return bool(value) if isinstance(value, bool) else str(value) not in ("0", "", "false")
    return None


@dataclass
class RunningEngine:
    config: VllmConfig
    base_url: str
    state: EngineState
    process: subprocess.Popen[bytes] | None
    log_path: Path | None

    def client(self) -> EngineClient:
        return EngineClient(self.base_url)


@contextmanager
def launch(
    config: VllmConfig,
    *,
    log_dir: Path | None = None,
    ready_timeout_s: float = DEFAULT_READY_TIMEOUT_S,
) -> Iterator[RunningEngine]:
    """Start vLLM, wait for readiness, verify its state, and always tear it down.

    Teardown is in a ``finally`` because a leaked engine holds the GPU, and the
    next cell in a paid session would then fail on memory for reasons that look
    nothing like the real cause.
    """
    log_path: Path | None = None
    log_handle = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        suffix = "invariant" if config.batch_invariant else "default"
        log_path = log_dir / f"vllm-{suffix}-{config.port}.log"
        # Not a context manager: the handle must outlive this block and is
        # closed in the finally below, after the process it feeds has exited.
        log_handle = open(log_path, "wb")  # noqa: SIM115

    process = subprocess.Popen(
        config.command(),
        env=config.environment(),
        stdout=log_handle or subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # so the whole group can be signalled
    )

    try:
        try:
            wait_until_ready(config.base_url, timeout_s=ready_timeout_s)
        except EngineLaunchError:
            if process.poll() is not None:
                tail = _log_tail(log_path)
                raise EngineLaunchError(
                    f"vllm exited with code {process.returncode} before becoming ready.{tail}"
                ) from None
            raise

        state = read_resolved_state(config.base_url, config)
        yield RunningEngine(
            config=config,
            base_url=config.base_url,
            state=state,
            process=process,
            log_path=log_path,
        )
    finally:
        _terminate(process)
        if log_handle is not None:
            log_handle.close()


def _log_tail(log_path: Path | None, lines: int = 20) -> str:
    if log_path is None or not log_path.exists():
        return " (no log captured — pass log_dir to keep one)"
    tail = log_path.read_text(errors="replace").splitlines()[-lines:]
    return "\n  " + "\n  ".join(tail)


def _terminate(process: subprocess.Popen[bytes], *, grace_s: float = 30.0) -> None:
    """SIGTERM the process group, then SIGKILL. A leaked engine holds the GPU."""
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    process.wait(timeout=grace_s)


def probe(base_url: str) -> EngineState | None:
    """Inspect an engine someone else started. Returns None if unreachable.

    Useful when the GPU box runs vLLM under systemd or in a container and the
    harness only needs to attach.
    """
    try:
        return read_resolved_state(base_url, VllmConfig(model="unknown", batch_invariant=False))
    except (EngineLaunchError, EngineError):
        return None
