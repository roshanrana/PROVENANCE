"""Real SGLang process lifecycle — A-01, the control arm for ADR-009.

This is the sibling of ``attest.harness.vllm``, and it exists for one reason
that is worth stating plainly before any code: **vLLM cannot run
batch-invariant kernels with prefix caching on**, so every cost-of-determinism
number ATTEST can produce on vLLM alone measures determinism *plus* the loss of
the prefix cache, with no way to separate the two. SGLang runs deterministically
with the radix cache on, which supplies the missing cell of the 2x2.

Three differences from the vLLM harness, each of which would silently corrupt a
measurement if handled the way vLLM's is:

* **The switch is a flag, not an environment variable.**
  ``--enable-deterministic-inference`` goes on the command line.
  ``VLLM_BATCH_INVARIANT`` had to be exported before the process existed because
  vLLM reads it at import; that constraint does not apply here, and pretending
  it does would be cargo-culting.
* **The attention backend is part of the determinism claim, not decoration.**
  Upstream supports deterministic inference on FlashInfer, FA3 and Triton — but
  **FlashInfer cannot do it with the radix cache on**. Since the radix cache is
  the entire reason SGLang is in this project, selecting FlashInfer for a
  cache-on deterministic cell is not a slow configuration, it is an invalid one.
  :func:`SGLangConfig.__post_init__` refuses it rather than letting the run
  produce a number nobody can interpret.
* **Prefix caching is disabled by a flag whose sense is inverted.**
  ``--disable-radix-cache`` turns it off; there is no ``--enable-`` counterpart.
  So the "state it explicitly in both directions" rule from ``vllm.py`` cannot
  be followed literally, and the receipt's ``prefix_caching`` field is instead
  reconciled against the readback.

Everything else is deliberately identical to ``vllm.py``: readiness is polled
rather than slept through, configuration is read back rather than assumed
(D-08), and a mismatch between what was requested and what the engine resolved
aborts the run. GPU minutes are the project's scarcest input, and a mislabelled
number is worse than a missing one because it gets published.

Nothing here has been run against a live SGLang engine. It is written to be
correct on inspection and is exercised against a stub; the first real execution
is A-03, on the rented GPU.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx

from attest.harness.engine import EngineClient, EngineError
from attest.harness.vllm import EngineLaunchError, wait_until_ready
from attest.receipt.schema import EngineState

DEFAULT_PORT = 30000  # SGLang's own default, kept so a stray manual run matches
DEFAULT_READY_TIMEOUT_S = 900.0

#: Attention backends upstream documents as supporting deterministic inference.
AttentionBackend = Literal["fa3", "triton", "flashinfer"]
DETERMINISTIC_BACKENDS: frozenset[str] = frozenset({"fa3", "triton", "flashinfer"})

#: Of those, the ones that keep working when the radix cache is on. FlashInfer
#: is documented as incompatible with radix cache under deterministic
#: inference — the one combination this project most needs, so it is the one
#: combination the config refuses.
RADIX_SAFE_DETERMINISTIC_BACKENDS: frozenset[str] = frozenset({"fa3", "triton"})

#: Chosen when the caller does not care. FA3 supports every feature in the
#: upstream compatibility matrix, so it is the backend that constrains the
#: experiment least.
DEFAULT_BACKEND: AttentionBackend = "fa3"


class SGLangConfigError(ValueError):
    """A configuration whose measurement would not mean anything.

    Separate from EngineLaunchError because it is caught before a process
    starts, and because the two say different things to the operator: this one
    means the *experiment* is wrong, not the engine.
    """


@dataclass(frozen=True)
class SGLangConfig:
    """An SGLang invocation. Everything here lands in the receipt."""

    model: str
    deterministic: bool
    #: Unlike vLLM (D-06, where batch invariance and APC are not integrated
    #: upstream), SGLang keeps the radix cache under determinism on FA3 and
    #: Triton. That is the whole point of this harness, so it defaults **on**
    #: here where it defaults off there.
    enable_prefix_caching: bool = True
    attention_backend: AttentionBackend = DEFAULT_BACKEND
    tensor_parallel_size: int = 1
    port: int = DEFAULT_PORT
    host: str = "127.0.0.1"
    #: SGLang seeds sampling from the request; a server-level seed keeps a run
    #: reproducible even for cells that do not set one per request.
    random_seed: int = 0
    mem_fraction_static: float = 0.90
    max_running_requests: int | None = None
    extra_args: tuple[str, ...] = ()
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.deterministic and self.attention_backend not in DETERMINISTIC_BACKENDS:
            raise SGLangConfigError(
                f"attention backend {self.attention_backend!r} does not support "
                f"deterministic inference upstream (supported: "
                f"{sorted(DETERMINISTIC_BACKENDS)}). A run with this combination "
                "would report determinism it does not have."
            )
        if (
            self.deterministic
            and self.enable_prefix_caching
            and self.attention_backend not in RADIX_SAFE_DETERMINISTIC_BACKENDS
        ):
            raise SGLangConfigError(
                f"{self.attention_backend!r} cannot run deterministically with the "
                "radix cache enabled. That cell — determinism WITH caching — is the "
                "one this engine is in the project to measure (ADR-009), so this "
                f"is refused rather than silently downgraded. Use one of "
                f"{sorted(RADIX_SAFE_DETERMINISTIC_BACKENDS)}."
            )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def command(self) -> list[str]:
        argv = [
            "python3",
            "-m",
            "sglang.launch_server",
            "--model-path",
            self.model,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--tp-size",
            str(self.tensor_parallel_size),
            "--mem-fraction-static",
            str(self.mem_fraction_static),
            "--random-seed",
            str(self.random_seed),
            # Always stated, because the receipt records which backend produced
            # the number and "whatever the default was" is not a record.
            "--attention-backend",
            self.attention_backend,
        ]
        if self.deterministic:
            argv.append("--enable-deterministic-inference")
        if not self.enable_prefix_caching:
            # Inverted sense: there is no --enable-radix-cache to pair with it.
            argv.append("--disable-radix-cache")
        if self.max_running_requests is not None:
            argv.extend(["--max-running-requests", str(self.max_running_requests)])
        argv.extend(self.extra_args)
        return argv

    def environment(self) -> dict[str, str]:
        """The child's environment.

        Nothing about SGLang's determinism is set here — it is a command-line
        flag. This method exists so the two harnesses have the same shape and so
        ``extra_env`` remains available for backend-specific tuning.
        """
        env = dict(os.environ)
        env.update(self.extra_env)
        return env

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": "sglang",
            "model": self.model,
            "deterministic": self.deterministic,
            "enable_prefix_caching": self.enable_prefix_caching,
            "attention_backend": self.attention_backend,
            "tensor_parallel_size": self.tensor_parallel_size,
            "command": self.command(),
        }


def read_resolved_state(
    base_url: str, config: SGLangConfig, *, client: httpx.Client | None = None
) -> EngineState:
    """Read back what SGLang resolved (D-08), and refuse a mismatch.

    SGLang exposes ``/get_server_info``, which returns the parsed server
    arguments. Field names move between releases, so this reads defensively and
    records whatever it finds — but a *contradiction* on either of the two axes
    the experiment varies is fatal, because those two axes are the independent
    variables of the whole 2x2.
    """
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        try:
            response = http.get(f"{base_url}/get_server_info")
            response.raise_for_status()
            resolved: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError):
            resolved = {}
        version = str(resolved.get("version") or _read_version(http, base_url))
        # An older engine that exposes neither endpoint is a *degraded* readback,
        # and the run continues with what we set. Nothing answering at all is a
        # dead engine, and returning a confident-looking EngineState for one
        # would put a fabricated configuration into a receipt.
        if not resolved and version == "unknown" and not _is_reachable(http, base_url):
            raise EngineLaunchError(f"nothing answered at {base_url}")
    except httpx.HTTPError as exc:
        raise EngineLaunchError(f"could not read engine state: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    observed_deterministic = _observed(
        resolved, ("enable_deterministic_inference", "deterministic")
    )
    if observed_deterministic is not None and observed_deterministic != config.deterministic:
        raise EngineLaunchError(
            f"engine reports deterministic={observed_deterministic} but the run "
            f"requested {config.deterministic}. Refusing to measure: every number "
            "from this engine would carry the wrong label."
        )

    # The radix cache is the axis SGLang is here for. A run that quietly lost it
    # would produce a "determinism with caching" number measured without caching
    # — which is precisely the confound ADR-009 exists to remove.
    observed_caching = _observed(resolved, ("disable_radix_cache",))
    if observed_caching is not None:
        actual_caching = not observed_caching
        if actual_caching != config.enable_prefix_caching:
            raise EngineLaunchError(
                f"engine reports prefix caching {'on' if actual_caching else 'off'} "
                f"but the run requested {'on' if config.enable_prefix_caching else 'off'}. "
                "Refusing to measure: this is the axis the comparison varies."
            )
    else:
        actual_caching = config.enable_prefix_caching

    backend = str(resolved.get("attention_backend") or config.attention_backend)
    if config.deterministic and backend not in DETERMINISTIC_BACKENDS:
        raise EngineLaunchError(
            f"engine resolved attention backend {backend!r}, which does not support "
            "deterministic inference. Refusing to measure."
        )

    return EngineState.for_engine(
        "sglang",
        deterministic=config.deterministic
        if observed_deterministic is None
        else observed_deterministic,
        engine_version=version,
        engine_git_sha=str(resolved.get("commit") or resolved.get("git_sha") or "unknown"),
        resolved_config=resolved or {"note": "engine exposed no get_server_info endpoint"},
        attention_backend=backend,
        prefix_caching=actual_caching,
        # SGLang's speculative decoding is opt-in via --speculative-algorithm.
        # Recorded because it is a documented interaction with determinism, and a
        # receipt that omits it would be asserting less than it appears to.
        speculative_decoding=bool(resolved.get("speculative_algorithm") or False),
        tensor_parallel_size=int(resolved.get("tp_size", config.tensor_parallel_size)),
    )


def _is_reachable(http: httpx.Client, base_url: str) -> bool:
    """Distinguish 'engine is old' from 'engine is not there'."""
    try:
        http.get(f"{base_url}/health")
    except httpx.HTTPError:
        return False
    return True


def _read_version(http: httpx.Client, base_url: str) -> str:
    try:
        payload = http.get(f"{base_url}/get_model_info").json()
        return str(payload.get("version", "unknown"))
    except (httpx.HTTPError, ValueError):
        return "unknown"


def _observed(resolved: Mapping[str, Any], keys: tuple[str, ...]) -> bool | None:
    """Best-effort read of a boolean the engine reports.

    ``None`` means the engine exposed nothing usable — in which case the receipt
    records what we set, and the writeup must say the readback was unavailable
    rather than implying it was confirmed.
    """
    for key in keys:
        if key in resolved:
            value = resolved[key]
            if isinstance(value, bool):
                return value
            return str(value).lower() not in ("0", "", "false", "none")
    return None


@dataclass
class RunningEngine:
    config: SGLangConfig
    base_url: str
    state: EngineState
    process: subprocess.Popen[bytes] | None
    log_path: Path | None

    def client(self) -> EngineClient:
        return EngineClient(self.base_url)


@contextmanager
def launch(
    config: SGLangConfig,
    *,
    log_dir: Path | None = None,
    ready_timeout_s: float = DEFAULT_READY_TIMEOUT_S,
) -> Iterator[RunningEngine]:
    """Start SGLang, wait for readiness, verify its state, and always tear it down.

    Teardown is in a ``finally`` because a leaked engine holds the GPU, and the
    next cell in a paid session would then fail on memory for reasons that look
    nothing like the real cause.
    """
    log_path: Path | None = None
    log_handle = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        mode = "deterministic" if config.deterministic else "default"
        cache = "cache" if config.enable_prefix_caching else "nocache"
        log_path = log_dir / f"sglang-{mode}-{cache}-{config.port}.log"
        # Not a context manager: the handle must outlive this block and is closed
        # in the finally below, after the process it feeds has exited.
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
                    f"sglang exited with code {process.returncode} before becoming ready.{tail}"
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
    """Inspect an engine someone else started. Returns None if unreachable."""
    try:
        return read_resolved_state(base_url, SGLangConfig(model="unknown", deterministic=False))
    except (EngineLaunchError, EngineError):
        return None
