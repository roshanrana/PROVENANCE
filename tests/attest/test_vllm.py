"""vLLM lifecycle — tested as far as a GPU-free machine allows.

The launch path itself cannot be exercised here; what *can* be, and what actually
carries the risk, is the configuration and refusal logic. A run mislabelled as
batch-invariant would put wrong numbers in a published table, and that mistake
would be invisible until someone tried to reproduce it.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from attest.harness.vllm import (
    EngineLaunchError,
    VllmConfig,
    _observed_batch_invariance,
    probe,
    read_resolved_state,
    wait_until_ready,
)


def _config(**over: object) -> VllmConfig:
    base = dict(model="Qwen/Qwen2.5-0.5B-Instruct", batch_invariant=True)
    base.update(over)
    return VllmConfig(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- command


def test_command_names_the_model_and_pins_the_seed() -> None:
    argv = _config().command()
    assert argv[:3] == ["vllm", "serve", "Qwen/Qwen2.5-0.5B-Instruct"]
    assert "--seed" in argv and argv[argv.index("--seed") + 1] == "0"


def test_prefix_caching_is_stated_explicitly_in_both_directions() -> None:
    """Relying on the upstream default would leave the receipt asserting
    something we never controlled (D-06)."""
    assert "--no-enable-prefix-caching" in _config(enable_prefix_caching=False).command()
    assert "--enable-prefix-caching" in _config(enable_prefix_caching=True).command()


def test_prefix_caching_defaults_off() -> None:
    assert _config().enable_prefix_caching is False


def test_extra_args_are_appended() -> None:
    assert "--max-num-seqs" in _config(extra_args=("--max-num-seqs", "64")).command()


# --------------------------------------------------------------------------- environment


def test_batch_invariant_env_is_set_for_the_child() -> None:
    """vLLM reads this at import time — setting it after launch does nothing."""
    assert _config(batch_invariant=True).environment()["VLLM_BATCH_INVARIANT"] == "1"
    assert _config(batch_invariant=False).environment()["VLLM_BATCH_INVARIANT"] == "0"


def test_environment_inherits_the_parent() -> None:
    env = _config().environment()
    assert env.get("PATH") == os.environ.get("PATH")


def test_extra_env_overrides() -> None:
    env = _config(extra_env={"VLLM_ATTENTION_BACKEND": "FLASHINFER"}).environment()
    assert env["VLLM_ATTENTION_BACKEND"] == "FLASHINFER"


def test_config_serialises_what_the_receipt_needs() -> None:
    doc = _config().to_dict()
    assert doc["VLLM_BATCH_INVARIANT"] == "1"
    assert doc["command"][0] == "vllm"


# --------------------------------------------------------------------------- readiness


def test_readiness_returns_once_health_answers() -> None:
    from tests.support.stub_engine import stub_engine

    # The stub has no /health, so this must time out rather than hang forever.
    with stub_engine() as stub, pytest.raises(EngineLaunchError, match="not ready"):
        wait_until_ready(stub.url, timeout_s=1.0, poll_s=0.2)


def test_readiness_failure_reports_the_last_error() -> None:
    with pytest.raises(EngineLaunchError) as exc:
        wait_until_ready("http://127.0.0.1:1", timeout_s=0.5, poll_s=0.1)
    assert "last:" in str(exc.value)


# --------------------------------------------------------------------------- readback


def _mock_client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mismatched_invariance_is_refused() -> None:
    """The refusal that matters most.

    If we asked for invariance and the engine did not enable it, every number from
    that run carries the wrong label — and a mislabelled number is worse than a
    missing one, because it gets published.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.11.0"})
        return httpx.Response(200, json={"batch_invariant": False})

    with (
        _mock_client(handler) as client,
        pytest.raises(EngineLaunchError, match="Refusing to measure"),
    ):
        read_resolved_state("http://engine", _config(batch_invariant=True), client=client)


def test_matching_invariance_is_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.11.0", "git_sha": "abc"})
        return httpx.Response(
            200,
            json={
                "batch_invariant": True,
                "enable_prefix_caching": False,
                "tensor_parallel_size": 1,
                "attention_backend": "FLASH_ATTN",
            },
        )

    with _mock_client(handler) as client:
        state = read_resolved_state("http://engine", _config(batch_invariant=True), client=client)
    assert state.batch_invariant is True
    assert state.prefix_caching is False
    assert state.attention_backend == "FLASH_ATTN"
    assert state.vllm_version == "0.11.0"


def test_missing_server_info_does_not_crash_the_run() -> None:
    """Older engines expose no server_info. Record that honestly and continue."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.9.0"})
        return httpx.Response(404)

    with _mock_client(handler) as client:
        state = read_resolved_state("http://engine", _config(batch_invariant=True), client=client)
    assert "exposed no server_info" in str(state.resolved_config)


def test_unreadable_invariance_returns_none_rather_than_guessing() -> None:
    """None means 'not confirmed', which the writeup must say — not imply it was."""
    assert _observed_batch_invariance({}, _config()) is None
    assert _observed_batch_invariance({"batch_invariant": True}, _config()) is True
    assert _observed_batch_invariance({"VLLM_BATCH_INVARIANT": "0"}, _config()) is False
    assert _observed_batch_invariance({"VLLM_BATCH_INVARIANT": "1"}, _config()) is True


# --------------------------------------------------------------------------- probe


def test_probe_returns_none_when_nothing_is_listening() -> None:
    assert probe("http://127.0.0.1:1") is None


def test_base_url_is_built_from_host_and_port() -> None:
    assert _config(host="10.0.0.5", port=9001).base_url == "http://10.0.0.5:9001"


def test_log_tail_is_included_when_a_log_exists(tmp_path: Path) -> None:
    from attest.harness.vllm import _log_tail

    log = tmp_path / "vllm.log"
    log.write_text("line one\nCUDA out of memory\n")
    assert "CUDA out of memory" in _log_tail(log)
    assert "no log captured" in _log_tail(None)
