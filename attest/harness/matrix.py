"""Experiment matrix generation — a pure function of (seed, config).

FR-A-02 and NFR-03. Keeping this pure and separately testable means a bug in
*scheduling* can never masquerade as a bug in the *engine*, which matters because
the engine only exists for four hours on rented hardware.

The two stages come from requirements §7.1, and the split is the response to
RSK-01 — divergence may simply not appear at 0.5B:

* **Stage 1, divergence hunt (~90 min).** An escalation ladder, cheapest first.
  Stops at the first configuration showing reliable divergence.
* **Stage 2, measured matrix (~2.5 h).** The full invariance on/off sweep at
  whatever Stage 1 selected — a configuration chosen from measurement, not from a
  guess made weeks earlier.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Stage = Literal[1, 2]

#: Cheapest first. Stage 1 walks this until divergence appears, so a run that
#: finds the effect early never pays for the larger models.
ESCALATION_MODELS: tuple[str, ...] = (
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
)

#: Divergence in published demonstrations appears *after* a shared prefix of
#: roughly a hundred tokens, so a short generation can hide a real effect.
ESCALATION_MAX_TOKENS: tuple[int, ...] = (64, 256, 1024)

#: Concurrency levels straddling the batch shapes where kernels switch reduction
#: strategy (1, 2-4, 5-8, 9+).
ESCALATION_CONCURRENCY: tuple[int, ...] = (1, 4, 16, 64)


@dataclass(frozen=True)
class CellParams:
    """One point in the experiment matrix."""

    model: str
    max_tokens: int
    concurrency: int
    batch_invariant: bool
    #: Spread of filler-prompt lengths sharing the batch. Heterogeneous batches
    #: change reduction shapes more than uniform ones.
    length_heterogeneity: Literal["uniform", "mixed", "extreme"]
    arrival: Literal["burst", "staggered"]
    trials: int
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Cell:
    cell_id: str
    params: CellParams
    #: Ascending. Stage 1 runs in this order so the cheapest evidence arrives first.
    cost_rank: int = 0

    def to_ledger_entry(self) -> dict[str, Any]:
        return {"cell_id": self.cell_id, "params": self.params.to_dict()}


@dataclass(frozen=True)
class MatrixSpec:
    """Everything needed to regenerate a matrix. Committed alongside results."""

    stage: Stage
    seed: int
    models: Sequence[str] = field(default_factory=lambda: ESCALATION_MODELS)
    max_tokens: Sequence[int] = field(default_factory=lambda: ESCALATION_MAX_TOKENS)
    concurrency: Sequence[int] = field(default_factory=lambda: ESCALATION_CONCURRENCY)
    heterogeneity: Sequence[str] = ("uniform", "mixed", "extreme")
    arrivals: Sequence[str] = ("burst",)
    trials: int = 32

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "seed": self.seed,
            "models": list(self.models),
            "max_tokens": list(self.max_tokens),
            "concurrency": list(self.concurrency),
            "heterogeneity": list(self.heterogeneity),
            "arrivals": list(self.arrivals),
            "trials": self.trials,
        }

    def fingerprint(self) -> str:
        """Stable digest of the spec. Two runs with the same fingerprint ran the
        same experiment — which is what makes NFR-01's traceability checkable
        rather than asserted."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


def _cell_id(index: int) -> str:
    return f"c{index:04d}"


def _estimated_cost(model: str, max_tokens: int, concurrency: int, trials: int) -> float:
    """Relative cost, for ordering only — never reported as a measurement.

    Rough and deliberately so: it decides what runs first, not what is published.
    """
    size_b = {"0.5B": 0.5, "1.5B": 1.5, "7B": 7.0}
    weight: float = next((v for k, v in size_b.items() if k in model), 1.0)
    return float(weight * max_tokens * trials * max(1, concurrency) ** 0.5)


def build_matrix(spec: MatrixSpec) -> list[Cell]:
    """Generate the matrix. Pure: identical spec in, identical cells out."""
    if spec.trials < 2:
        raise ValueError(f"trials must be at least 2 to observe divergence, got {spec.trials}")
    if spec.stage not in (1, 2):
        raise ValueError(f"stage must be 1 or 2, got {spec.stage}")

    # Stage 1 hunts with invariance OFF only — turning it on proves nothing until
    # there is a divergence to suppress, and GPU minutes spent proving the
    # already-known are minutes not spent finding the effect.
    invariance_settings: tuple[bool, ...] = (False,) if spec.stage == 1 else (False, True)

    raw: list[tuple[float, CellParams]] = []
    for model in spec.models:
        for max_tokens in spec.max_tokens:
            for concurrency in spec.concurrency:
                for heterogeneity in spec.heterogeneity:
                    for arrival in spec.arrivals:
                        for invariant in invariance_settings:
                            # A batch of one cannot be heterogeneous. Emitting
                            # those cells would pad the matrix with duplicates
                            # and quietly inflate any "we ran N cells" claim.
                            if concurrency == 1 and heterogeneity != "uniform":
                                continue
                            params = CellParams(
                                model=model,
                                max_tokens=max_tokens,
                                concurrency=concurrency,
                                batch_invariant=invariant,
                                length_heterogeneity=heterogeneity,  # type: ignore[arg-type]
                                arrival=arrival,  # type: ignore[arg-type]
                                trials=spec.trials,
                                seed=spec.seed,
                            )
                            cost = _estimated_cost(model, max_tokens, concurrency, spec.trials)
                            raw.append((cost, params))

    # Sort by cost, then by a stable rendering of the params so ties never depend
    # on dict ordering or interpreter version.
    raw.sort(key=lambda item: (item[0], json.dumps(item[1].to_dict(), sort_keys=True)))
    return [
        Cell(cell_id=_cell_id(i), params=params, cost_rank=i) for i, (_, params) in enumerate(raw)
    ]


def stage1_ladder(seed: int, *, trials: int = 32) -> list[Cell]:
    """Stage 1: the divergence hunt, cheapest first, invariance off."""
    return build_matrix(MatrixSpec(stage=1, seed=seed, trials=trials))


def stage2_matrix(
    seed: int,
    *,
    model: str,
    max_tokens: int,
    concurrency: Sequence[int],
    heterogeneity: str,
    trials: int,
) -> list[Cell]:
    """Stage 2: the measured sweep at the configuration Stage 1 selected.

    Takes the chosen configuration as arguments rather than rediscovering it,
    because that choice is a **human decision point** (requirements §7.1) — its
    outcome changes what the project claims, and that is not a judgement to
    automate.
    """
    return build_matrix(
        MatrixSpec(
            stage=2,
            seed=seed,
            models=(model,),
            max_tokens=(max_tokens,),
            concurrency=tuple(concurrency),
            heterogeneity=(heterogeneity,),
            trials=trials,
        )
    )
