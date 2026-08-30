from __future__ import annotations

import pytest

from attest.harness.matrix import (
    ESCALATION_MODELS,
    Cell,
    MatrixSpec,
    build_matrix,
    stage1_ladder,
    stage2_matrix,
)


def test_matrix_is_a_pure_function_of_the_spec() -> None:
    """NFR-03. Same spec in, same cells out — no clock, no global RNG, no env."""
    spec = MatrixSpec(stage=1, seed=7)
    assert build_matrix(spec) == build_matrix(spec)


def test_different_seeds_produce_different_specs_but_the_same_shape() -> None:
    a = build_matrix(MatrixSpec(stage=1, seed=1))
    b = build_matrix(MatrixSpec(stage=1, seed=2))
    assert len(a) == len(b)
    assert [c.cell_id for c in a] == [c.cell_id for c in b]
    assert a != b  # the seed is carried into every cell's params


def test_stage_one_runs_invariance_off_only() -> None:
    """Nothing to suppress until a divergence is found; GPU minutes are scarce."""
    assert {c.params.batch_invariant for c in stage1_ladder(seed=1)} == {False}


def test_stage_two_sweeps_both_invariance_settings() -> None:
    cells = stage2_matrix(
        seed=1,
        model="Qwen/Qwen2.5-0.5B-Instruct",
        max_tokens=256,
        concurrency=(1, 8),
        heterogeneity="mixed",
        trials=32,
    )
    assert {c.params.batch_invariant for c in cells} == {False, True}


def test_cells_are_ordered_cheapest_first() -> None:
    """Stage 1 must produce its cheapest evidence before spending on 7B."""
    cells = stage1_ladder(seed=1)
    assert cells[0].params.model == ESCALATION_MODELS[0]
    assert cells[0].params.max_tokens == min(c.params.max_tokens for c in cells)
    assert [c.cost_rank for c in cells] == list(range(len(cells)))


def test_the_most_expensive_cell_is_the_largest_model() -> None:
    assert stage1_ladder(seed=1)[-1].params.model == ESCALATION_MODELS[-1]


def test_batch_of_one_is_never_heterogeneous() -> None:
    """A batch of one cannot be mixed. Emitting those cells would pad the matrix
    with duplicates and inflate any 'we ran N cells' claim."""
    for cell in stage1_ladder(seed=1):
        if cell.params.concurrency == 1:
            assert cell.params.length_heterogeneity == "uniform"


def test_cell_ids_are_unique_and_sequential() -> None:
    ids = [c.cell_id for c in stage1_ladder(seed=1)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)
    assert ids[0] == "c0000"


def test_ledger_entries_are_well_formed() -> None:
    entry = stage1_ladder(seed=1)[0].to_ledger_entry()
    assert set(entry) == {"cell_id", "params"}
    assert entry["params"]["trials"] >= 2


def test_fingerprint_is_stable_and_discriminating() -> None:
    """Two runs with the same fingerprint ran the same experiment."""
    assert MatrixSpec(stage=1, seed=1).fingerprint() == MatrixSpec(stage=1, seed=1).fingerprint()
    assert MatrixSpec(stage=1, seed=1).fingerprint() != MatrixSpec(stage=1, seed=2).fingerprint()
    assert MatrixSpec(stage=1, seed=1).fingerprint() != MatrixSpec(stage=2, seed=1).fingerprint()


def test_ordering_does_not_depend_on_dict_iteration_order() -> None:
    """Ties are broken on a stable rendering, not on insertion order."""
    spec = MatrixSpec(stage=2, seed=3, models=("m",), max_tokens=(8,), concurrency=(4,))
    first = [c.params.to_dict() for c in build_matrix(spec)]
    second = [c.params.to_dict() for c in build_matrix(spec)]
    assert first == second


def test_too_few_trials_is_refused() -> None:
    """One trial cannot show divergence — it has nothing to differ from."""
    with pytest.raises(ValueError, match="at least 2"):
        build_matrix(MatrixSpec(stage=1, seed=1, trials=1))


def test_unknown_stage_is_refused() -> None:
    with pytest.raises(ValueError, match="stage"):
        build_matrix(MatrixSpec(stage=3, seed=1))  # type: ignore[arg-type]


def test_stage_two_is_a_focused_matrix_not_the_full_ladder() -> None:
    """Stage 2 spends the remaining GPU budget on one configuration, deeply."""
    ladder = stage1_ladder(seed=1)
    focused = stage2_matrix(
        seed=1,
        model="Qwen/Qwen2.5-0.5B-Instruct",
        max_tokens=256,
        concurrency=(1, 4, 16, 64),
        heterogeneity="mixed",
        trials=128,
    )
    assert len(focused) < len(ladder)
    assert {c.params.model for c in focused} == {"Qwen/Qwen2.5-0.5B-Instruct"}
    assert all(c.params.trials == 128 for c in focused)


def test_cells_are_hashable_and_comparable() -> None:
    cells = stage1_ladder(seed=1)
    assert isinstance(cells[0], Cell)
    assert len({(c.cell_id, c.params) for c in cells}) == len(cells)
