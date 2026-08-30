"""Attestation receipt types.

**Frozen contract — LLD §4.1.** Field names and nesting are fixed; changing one is
a plan change requiring sign-off and propagation to every affected task pack.

Two design points carry the weight here:

* **Model identity anchors to the Hugging Face Hub** (D-12) — repo id, commit SHA,
  and the weight file's LFS sha256. A locally computed hash proves only internal
  consistency; anchoring to a root the validator trusts and we do not control is
  what makes this an attestation rather than a log line.
* **``resolved_config`` is read back from the engine** (D-08), never the flags the
  operator intended to pass. ``override_envs_for_invariance()`` mutates the
  environment, so intended and actual differ.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://provenance.dev/attestation/v0.1"
PREDICATE_MAJOR = 0

Resolution = Literal["online", "offline", "unresolved"]


class ReceiptSchemaError(ValueError):
    """Malformed, incomplete, or unsupported receipt document."""


class SubjectDigestMismatch(ReceiptSchemaError):
    """The declared subject digest disagrees with the bound output.

    Distinct from a generic malformed document because it means something
    different to a validator: the document was *edited*, not merely corrupted.
    The CLI maps the two to different exit codes for exactly that reason.
    """


def _require(doc: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in doc:
        raise ReceiptSchemaError(f"missing required field: {where}.{key}")
    return doc[key]


def _reject_unknown(doc: Mapping[str, Any], allowed: set[str], where: str) -> None:
    """Unknown fields are rejected, never ignored.

    Silently dropping a field a producer thought it was binding would make the
    receipt claim less than the producer believed — the failure mode an
    attestation format exists to prevent.
    """
    unknown = set(doc) - allowed
    if unknown:
        raise ReceiptSchemaError(f"unknown field(s) in {where}: {sorted(unknown)}")


@dataclass(frozen=True)
class ModelIdentity:
    repo_id: str
    commit_sha: str
    weights_file: str
    weights_lfs_sha256: str
    resolution: Resolution
    hub: Literal["huggingface"] = "huggingface"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hub": self.hub,
            "repo_id": self.repo_id,
            "commit_sha": self.commit_sha,
            "weights": {"file": self.weights_file, "lfs_sha256": self.weights_lfs_sha256},
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> ModelIdentity:
        _reject_unknown(doc, {"hub", "repo_id", "commit_sha", "weights", "resolution"}, "model")
        weights = _require(doc, "weights", "model")
        _reject_unknown(weights, {"file", "lfs_sha256"}, "model.weights")
        resolution = _require(doc, "resolution", "model")
        if resolution not in ("online", "offline", "unresolved"):
            raise ReceiptSchemaError(f"model.resolution not recognised: {resolution!r}")
        hub = doc.get("hub", "huggingface")
        if hub != "huggingface":
            raise ReceiptSchemaError(f"model.hub not recognised: {hub!r}")
        return cls(
            repo_id=_require(doc, "repo_id", "model"),
            commit_sha=_require(doc, "commit_sha", "model"),
            weights_file=_require(weights, "file", "model.weights"),
            weights_lfs_sha256=_require(weights, "lfs_sha256", "model.weights"),
            resolution=resolution,
            hub=hub,
        )


@dataclass(frozen=True)
class EngineState:
    vllm_version: str
    vllm_git_sha: str
    resolved_config: Mapping[str, Any]
    attention_backend: str
    batch_invariant: bool
    prefix_caching: bool
    speculative_decoding: bool
    tensor_parallel_size: int

    _FIELDS: ClassVar[set[str]] = {
        "vllm_version",
        "vllm_git_sha",
        "resolved_config",
        "attention_backend",
        "batch_invariant",
        "prefix_caching",
        "speculative_decoding",
        "tensor_parallel_size",
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "vllm_version": self.vllm_version,
            "vllm_git_sha": self.vllm_git_sha,
            "resolved_config": dict(self.resolved_config),
            "attention_backend": self.attention_backend,
            "batch_invariant": self.batch_invariant,
            "prefix_caching": self.prefix_caching,
            "speculative_decoding": self.speculative_decoding,
            "tensor_parallel_size": self.tensor_parallel_size,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> EngineState:
        _reject_unknown(doc, set(cls._FIELDS), "engine")
        for key in cls._FIELDS:
            _require(doc, key, "engine")
        return cls(
            vllm_version=doc["vllm_version"],
            vllm_git_sha=doc["vllm_git_sha"],
            resolved_config=dict(doc["resolved_config"]),
            attention_backend=doc["attention_backend"],
            batch_invariant=bool(doc["batch_invariant"]),
            prefix_caching=bool(doc["prefix_caching"]),
            speculative_decoding=bool(doc["speculative_decoding"]),
            tensor_parallel_size=int(doc["tensor_parallel_size"]),
        )


@dataclass(frozen=True)
class SamplingParams:
    seed: int
    temperature: float
    top_p: float
    max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> SamplingParams:
        _reject_unknown(doc, {"seed", "temperature", "top_p", "max_tokens"}, "sampling")
        for key in ("seed", "temperature", "top_p", "max_tokens"):
            _require(doc, key, "sampling")
        return cls(
            seed=int(doc["seed"]),
            temperature=float(doc["temperature"]),
            top_p=float(doc["top_p"]),
            max_tokens=int(doc["max_tokens"]),
        )


@dataclass(frozen=True)
class OutputRecord:
    token_ids: Sequence[int]
    text: str
    logprobs_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_ids": list(self.token_ids),
            "text": self.text,
            "logprobs_sha256": self.logprobs_sha256,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> OutputRecord:
        _reject_unknown(doc, {"token_ids", "text", "logprobs_sha256"}, "output")
        for key in ("token_ids", "text", "logprobs_sha256"):
            _require(doc, key, "output")
        return cls(
            token_ids=[int(t) for t in doc["token_ids"]],
            text=doc["text"],
            logprobs_sha256=doc["logprobs_sha256"],
        )


@dataclass(frozen=True)
class RunRef:
    run_id: str
    cell_id: str
    timestamp_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cell_id": self.cell_id,
            "timestamp_utc": self.timestamp_utc,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> RunRef:
        _reject_unknown(doc, {"run_id", "cell_id", "timestamp_utc"}, "run")
        for key in ("run_id", "cell_id", "timestamp_utc"):
            _require(doc, key, "run")
        return cls(run_id=doc["run_id"], cell_id=doc["cell_id"], timestamp_utc=doc["timestamp_utc"])


def subject_digest(token_ids: Sequence[int]) -> str:
    """sha256 over the canonical rendering of the output token ids."""
    import hashlib

    payload = ",".join(str(int(t)) for t in token_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Receipt:
    model: ModelIdentity
    engine: EngineState
    sampling: SamplingParams
    output: OutputRecord
    run: RunRef

    def to_statement(self) -> dict[str, Any]:
        return {
            "_type": STATEMENT_TYPE,
            "subject": [
                {
                    "name": "inference-output",
                    "digest": {"sha256": subject_digest(self.output.token_ids)},
                }
            ],
            "predicateType": PREDICATE_TYPE,
            "predicate": {
                "model": self.model.to_dict(),
                "engine": self.engine.to_dict(),
                "sampling": self.sampling.to_dict(),
                "output": self.output.to_dict(),
                "run": self.run.to_dict(),
            },
        }

    @classmethod
    def from_statement(cls, doc: Mapping[str, Any]) -> Receipt:
        _reject_unknown(doc, {"_type", "subject", "predicateType", "predicate"}, "statement")
        if _require(doc, "_type", "statement") != STATEMENT_TYPE:
            raise ReceiptSchemaError(f"unsupported statement type: {doc['_type']!r}")

        predicate_type = _require(doc, "predicateType", "statement")
        check_predicate_type(predicate_type)

        predicate = _require(doc, "predicate", "statement")
        _reject_unknown(predicate, {"model", "engine", "sampling", "output", "run"}, "predicate")

        receipt = cls(
            model=ModelIdentity.from_dict(_require(predicate, "model", "predicate")),
            engine=EngineState.from_dict(_require(predicate, "engine", "predicate")),
            sampling=SamplingParams.from_dict(_require(predicate, "sampling", "predicate")),
            output=OutputRecord.from_dict(_require(predicate, "output", "predicate")),
            run=RunRef.from_dict(_require(predicate, "run", "predicate")),
        )

        # The subject digest is derived, so a mismatch means the document was
        # edited after signing — or built by something that disagrees with us
        # about canonicalisation. Either way it is not a valid receipt.
        subject = _require(doc, "subject", "statement")
        if not isinstance(subject, list) or len(subject) != 1:
            raise ReceiptSchemaError("statement.subject must be a single-element list")
        declared = subject[0].get("digest", {}).get("sha256")
        expected = subject_digest(receipt.output.token_ids)
        if declared != expected:
            raise SubjectDigestMismatch(
                f"subject digest does not match output.token_ids "
                f"(declared={declared!r}, computed={expected!r})"
            )
        return receipt


def check_predicate_type(predicate_type: str) -> None:
    """Reject an unknown predicate major version (LLD §9)."""
    if not predicate_type.startswith("https://provenance.dev/attestation/v"):
        raise ReceiptSchemaError(f"unsupported predicateType: {predicate_type!r}")
    version = predicate_type.rsplit("/v", 1)[1]
    try:
        major = int(version.split(".")[0])
    except ValueError as exc:
        raise ReceiptSchemaError(f"unparseable predicate version: {predicate_type!r}") from exc
    if major != PREDICATE_MAJOR:
        raise ReceiptSchemaError(
            f"unsupported predicate major version {major} (this build understands "
            f"{PREDICATE_MAJOR}): {predicate_type!r}"
        )
