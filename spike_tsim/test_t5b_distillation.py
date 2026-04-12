"""
T5b: realistic non-Clifford circuit via sinter+tsim.

Uses the 5-qubit magic state distillation protocol from tsim's own demo
(docs/demos/magic_state_distillation.ipynb). The circuit has:
- R_X(theta) non-Clifford rotations (theta = -arccos(sqrt(1/3))/pi)
- T and T_DAG gates
- Depolarizing noise
- 5 qubits, 5 measurements, canonical distillation syndrome pattern [1, 0, 1, 1]

Adapted for sinter by adding explicit DETECTOR and OBSERVABLE_INCLUDE
annotations. This is NOT a post-selected distillation measurement; it's
a best-effort "run this real non-Clifford QEC circuit through sinter+tsim
and see if the wrapper handles it at all" test.

The key success criterion: sinter.collect() returns valid TaskStats
without crashing, and the DEM / decoder / wrapper integration all work
on a circuit with 5 T-related non-Clifford gates.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching --with numpy python test_t5b_distillation.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import sinter
import tsim

sys.path.insert(0, str(Path(__file__).parent))
from tsim_sampler import TsimThenDecodeSampler


def _build_distillation_circuit(p: float = 0.02) -> tsim.Circuit:
    """The 5-qubit magic state distillation circuit from the tsim demo,
    annotated with detectors and an observable so sinter can run it."""
    theta = -math.acos(math.sqrt(1 / 3)) / math.pi
    return tsim.Circuit(f"""
        # initial state: prepare 5 noisy magic states
        R 0 1 2 3 4
        R_X({theta}) 0 1 2 3 4
        T_DAG 0 1 2 3 4
        DEPOLARIZE1({p}) 0 1 2 3 4

        # distillation
        SQRT_X 0 1 4
        CZ 0 1 2 3
        SQRT_Y 0 3
        CZ 0 2 3 4
        TICK
        SQRT_X_DAG 0
        CZ 0 4 1 3
        TICK
        SQRT_X_DAG 0 1 2 3 4

        # undo magic state preparation on qubit 0 (the distilled output)
        T 0
        R_X({-theta}) 0

        M 0 1 2 3 4

        # rec layout after 5 measurements (most recent last):
        # rec[-5] = M0 (distilled)
        # rec[-4] = M1 (syndrome 1)
        # rec[-3] = M2 (syndrome 2)
        # rec[-2] = M3 (syndrome 3)
        # rec[-1] = M4 (syndrome 4)
        #
        # The tsim notebook's success condition is syndrome == [1, 0, 1, 1]
        # meaning M1=1, M2=0, M3=1, M4=1.
        # We define detectors that fire when the syndrome DEVIATES from the
        # noiseless-successful pattern, so "detector fires" means "distillation
        # had an unexpected outcome on that syndrome bit".
        #
        # For M1 and M4 (noiseless=1), detector XORs against a constant 1
        # (via a two-measurement reference) is awkward. Simpler: just define
        # detectors as direct reads of each syndrome bit, and let the decoder
        # use them as raw data.
        DETECTOR rec[-4]
        DETECTOR rec[-3]
        DETECTOR rec[-2]
        DETECTOR rec[-1]

        # The distilled bit (M0) is our logical observable.
        # Noiseless successful distillation gives M0=0, so the observable
        # tracks the "distilled state failed" rate.
        OBSERVABLE_INCLUDE(0) rec[-5]
    """)


def test_distillation_circuit_is_non_clifford():
    c = _build_distillation_circuit()
    print(f"  num_qubits = {c.num_qubits}")
    print(f"  num_detectors = {c.num_detectors}")
    print(f"  num_observables = {c.num_observables}")
    print(f"  tcount = {c.tcount()}")
    print(f"  is_clifford = {c.is_clifford}")
    assert c.num_qubits == 5
    assert c.tcount() >= 1, "distillation circuit must have at least one T gate"
    assert not c.is_clifford


def test_bare_tsim_samples_distillation():
    """Sanity: tsim samples the distillation circuit directly."""
    c = _build_distillation_circuit()
    sampler = c.compile_detector_sampler(seed=42)
    dets = sampler.sample(
        shots=2_000,
        use_detector_reference_sample=True,
    )
    print(f"  dets shape: {dets.shape}")
    print(f"  per-detector rates: {dets.mean(axis=0)}")
    print(f"  global rate: {dets.mean():.4f}")
    assert dets.shape == (2_000, c.num_detectors)


def test_sinter_collect_runs_distillation():
    """THE KEY TEST: sinter.collect() + wrapper handles the real distillation circuit."""
    c = _build_distillation_circuit()
    task = sinter.Task(
        circuit=c,
        decoder="pymatching_tsim",
        skip_validation=True,
    )

    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=2_000,
        max_errors=2_000,
        custom_decoders={
            "pymatching_tsim": TsimThenDecodeSampler(
                decoder_name="pymatching",
                count_detection_events=True,
            )
        },
        print_progress=False,
    )

    assert len(results) == 1
    stat = results[0]
    print(f"  sinter+tsim+distillation result:")
    print(f"    shots = {stat.shots}")
    print(f"    errors = {stat.errors}")
    print(f"    discards = {stat.discards}")
    print(f"    logical error rate = {stat.errors/stat.shots:.4f}")
    print(f"    time = {stat.seconds:.2f}s")
    print(f"    detectors_checked = {stat.custom_counts.get('detectors_checked', 0)}")
    print(f"    detection_events = {stat.custom_counts.get('detection_events', 0)}")
    print(f"    strong_id = {stat.strong_id[:16]}...")

    assert stat.shots == 2_000
    # logical error rate depends on the circuit and decoder, but should be in range
    error_rate = stat.errors / stat.shots
    assert 0.0 <= error_rate <= 0.8, f"error rate {error_rate:.4f} looks wrong"


if __name__ == "__main__":
    print("=== T5b: realistic non-Clifford (magic state distillation) ===\n")
    tests = [
        ("test_distillation_circuit_is_non_clifford", test_distillation_circuit_is_non_clifford),
        ("test_bare_tsim_samples_distillation", test_bare_tsim_samples_distillation),
        ("test_sinter_collect_runs_distillation", test_sinter_collect_runs_distillation),
    ]
    failed = []
    for name, fn in tests:
        print(f"{name}:")
        try:
            fn()
            print("  PASS\n")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  FAIL: {type(e).__name__}: {e}\n")
            failed.append(name)

    if failed:
        print(f"T5b: {len(failed)}/{len(tests)} tests failed: {failed}")
        sys.exit(1)
    else:
        print("T5b ALL GREEN")
