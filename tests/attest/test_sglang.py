"""SGLang lifecycle — tested as far as a GPU-free machine allows.

Same standard as ``test_vllm.py``: the launch path cannot be exercised here,
but the configuration and refusal logic can, and that is where the risk lives.
A run mislabelled as deterministic — or as cached when the cache was off —
would put a wrong number in the published 2x2, and the mistake would be
invisible until someone tried to reproduce it.
"""

from __future__ import annotations

import httpx
import pytest

from attest.harness.sglang import (
    DETERMINISTIC_BACKENDS,
    RADIX_SAFE_DETERMINISTIC_BACKENDS,
    SGLangConfig,
    SGLangConfigError,
    _observed,
    probe,
    read_resolved_state,
)
from attest.harness.vllm import EngineLaunchError


def _config(**over: object) -> SGLangConfig:
    base: dict[str, object] = dict(model="Qwen/Qwen2.5-0.5B-Instruct", deterministic=True)
    base.update(over)
    return SGLangConfig(**base)  # type: ignore[arg-type]


def _mock_client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler))


def _server_info(**fields: object):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/get_server_info":
            return httpx.Response(200, json=dict(fields))
        return httpx.Response(200, json={"version": "0.5.12"})

    return handler


# --------------------------------------------------------------------------- command


def test_command_launches_the_server_module_and_pins_the_seed() -> None:
    argv = _config().command()
    assert argv[:3] == ["python3", "-m", "sglang.launch_server"]
    assert argv[argv.index("--model-path") + 1] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert argv[argv.index("--random-seed") + 1] == "0"


def test_determinism_is_a_flag_not_an_environment_variable() -> None:
    """The difference from vLLM that would be easy to cargo-cult.

    vLLM reads VLLM_BATCH_INVARIANT at import, so it must be exported before the
    process exists. SGLang takes a flag, and setting a lookalike env var here
    would do nothing at all while looking like it had.
    """
    assert "--enable-deterministic-inference" in _config(deterministic=True).command()
    assert "--enable-deterministic-inference" not in _config(deterministic=False).command()
    assert not any("DETERMINISTIC" in key.upper() for key in _config(deterministic=True).extra_env)


def test_the_attention_backend_is_always_stated() -> None:
    """'Whatever the default was' is not a record of what produced the number."""
    argv = _config().command()
    assert "--attention-backend" in argv
    assert argv[argv.index("--attention-backend") + 1] in DETERMINISTIC_BACKENDS


def test_prefix_caching_uses_the_inverted_flag() -> None:
    assert "--disable-radix-cache" in _config(enable_prefix_caching=False).command()
    assert "--disable-radix-cache" not in _config(enable_prefix_caching=True).command()


def test_prefix_caching_defaults_on_unlike_vllm() -> None:
    """The whole reason SGLang is in the project (ADR-009).

    vLLM pins it off (D-06) because batch invariance and APC are not integrated
    upstream. SGLang keeps it, which is what supplies the missing 2x2 cell.
    """
    assert _config().enable_prefix_caching is True


def test_extra_args_are_appended() -> None:
    assert (
        "--chunked-prefill-size" in _config(extra_args=("--chunked-prefill-size", "2048")).command()
    )


# --------------------------------------------------------------------------- refusals


def test_a_backend_without_deterministic_support_is_refused() -> None:
    with pytest.raises(SGLangConfigError, match="does not support"):
        _config(attention_backend="torch_native")


def test_flashinfer_with_caching_and_determinism_is_refused() -> None:
    """The refusal that protects the experiment.

    FlashInfer supports deterministic inference, and it supports the radix
    cache — but not both at once. That combination is exactly the cell SGLang is
    here to measure, so producing it silently without caching would yield a
    'determinism with caching' number measured without caching.
    """
    assert "flashinfer" in DETERMINISTIC_BACKENDS
    assert "flashinfer" not in RADIX_SAFE_DETERMINISTIC_BACKENDS
    with pytest.raises(SGLangConfigError, match="radix cache"):
        _config(attention_backend="flashinfer", enable_prefix_caching=True)


def test_flashinfer_is_allowed_when_caching_is_off() -> None:
    cfg = _config(attention_backend="flashinfer", enable_prefix_caching=False)
    assert cfg.attention_backend == "flashinfer"


def test_flashinfer_is_allowed_when_determinism_is_off() -> None:
    cfg = _config(attention_backend="flashinfer", deterministic=False)
    assert cfg.enable_prefix_caching is True


# --------------------------------------------------------------------------- readback


def test_mismatched_determinism_is_refused() -> None:
    with (
        _mock_client(_server_info(enable_deterministic_inference=False)) as client,
        pytest.raises(EngineLaunchError, match="Refusing to measure"),
    ):
        read_resolved_state("http://engine", _config(deterministic=True), client=client)


def test_silently_lost_radix_cache_is_refused() -> None:
    """The failure this harness exists to catch.

    An engine that quietly started with the cache off would produce a number
    published as 'deterministic, cache on'. Nothing downstream could detect it.
    """
    handler = _server_info(enable_deterministic_inference=True, disable_radix_cache=True)
    with (
        _mock_client(handler) as client,
        pytest.raises(EngineLaunchError, match="axis the comparison varies"),
    ):
        read_resolved_state(
            "http://engine", _config(deterministic=True, enable_prefix_caching=True), client=client
        )


def test_matching_state_is_accepted_and_recorded() -> None:
    handler = _server_info(
        enable_deterministic_inference=True,
        disable_radix_cache=False,
        attention_backend="fa3",
        tp_size=1,
        version="0.5.12",
        commit="cafe123",
    )
    with _mock_client(handler) as client:
        state = read_resolved_state("http://engine", _config(), client=client)
    assert state.engine == "sglang"
    assert state.deterministic is True
    assert state.prefix_caching is True
    assert state.attention_backend == "fa3"
    assert state.engine_version == "0.5.12"
    assert state.engine_git_sha == "cafe123"


def test_the_mechanism_recorded_is_sglangs_not_vllms() -> None:
    """A receipt naming VLLM_BATCH_INVARIANT for an SGLang run would be a lie.

    It is the same class of mislabelling the readback exists to prevent, one
    level up — and the schema now refuses it, so this is belt and braces.
    """
    with _mock_client(_server_info(enable_deterministic_inference=True)) as client:
        state = read_resolved_state("http://engine", _config(), client=client)
    assert state.determinism_mechanism == "--enable-deterministic-inference"
    assert "VLLM" not in state.determinism_mechanism


def test_missing_server_info_does_not_crash_the_run() -> None:
    """Record honestly and continue, as vllm.py does for older engines."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/get_server_info":
            return httpx.Response(404)
        return httpx.Response(200, json={"version": "0.5.12"})

    with _mock_client(handler) as client:
        state = read_resolved_state("http://engine", _config(), client=client)
    assert "exposed no get_server_info" in str(state.resolved_config)
    assert state.deterministic is True  # what we set, since readback was unavailable


def test_unreadable_flag_returns_none_rather_than_guessing() -> None:
    assert _observed({}, ("enable_deterministic_inference",)) is None
    assert _observed({"enable_deterministic_inference": True}, ("enable_deterministic_inference",))
    assert _observed({"disable_radix_cache": "false"}, ("disable_radix_cache",)) is False


def test_a_deterministic_run_on_an_unsupported_resolved_backend_is_refused() -> None:
    handler = _server_info(enable_deterministic_inference=True, attention_backend="torch_native")
    with (
        _mock_client(handler) as client,
        pytest.raises(EngineLaunchError, match="does not support deterministic"),
    ):
        read_resolved_state("http://engine", _config(), client=client)


# --------------------------------------------------------------------------- misc


def test_probe_returns_none_when_nothing_is_listening() -> None:
    assert probe("http://127.0.0.1:1") is None


def test_base_url_is_built_from_host_and_port() -> None:
    assert _config(host="10.0.0.5", port=30001).base_url == "http://10.0.0.5:30001"


def test_config_serialises_what_the_receipt_needs() -> None:
    doc = _config().to_dict()
    assert doc["engine"] == "sglang"
    assert doc["command"][0] == "python3"
    assert doc["deterministic"] is True
