"""
T5a: minimal non-Clifford circuit through sinter+TsimThenDecodeSampler.

This is the test the spike SHOULD have started with. A non-Clifford circuit
forces tsim to use its ZX-stabilizer-rank sampling path (the GPU-accelerated
one, the one the qec-kiln paper would actually care about). If the wrapper
handles this end-to-end without crashing, the integration is real for the
paper's target workload.

Circuit: prepare |+>, apply T gate, CNOT to entangle with ancilla, measure
both in Z basis with depolarizing noise. Defines two detectors and one
observable. Uses tsim's extended text format (which supports T), not stim's.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching python test_t5a_minimal_nonclifford.py
"""
import sys
from pathlib import Path

import sinter
import tsim

sys.path.insert(0, str(Path(__file__).parent))
from tsim_sampler import TsimThenDecodeSampler


def _build_minimal_nonclifford():
    """A circuit that definitely exercises tsim's non-Clifford path.

    T gates can't be expressed in stim at all, so any circuit with them must
    use tsim's text format. The sparse geometric sampler (the biased code
    path we found earlier) should not apply here; this should go through
    the ZX-stabilizer-rank path.
    """
    return tsim.Circuit("""
        R 0 1
        H 0
        T 0
        DEPOLARIZE1(0.02) 0
        CX 0 1
        DEPOLARIZE2(0.02) 0 1
        T_DAG 0
        H 0
        M 0 1
        DETECTOR rec[-1]
        DETECTOR rec[-2]
        OBSERVABLE_INCLUDE(0) rec[-2]
    """)


def test_circuit_is_not_clifford():
    c = _build_minimal_nonclifford()
    print(f"  tcount: {c.tcount()}")
    print(f"  is_clifford: {c.is_clifford}")
    assert c.tcount() > 0, "circuit must have T gates to exercise the non-Clifford path"
    assert not c.is_clifford, "circuit must register as non-Clifford"


def test_tsim_can_sample_it_bare():
    """Sanity: tsim can sample this circuit without sinter at all."""
    c = _build_minimal_nonclifford()
    sampler = c.compile_detector_sampler(seed=42)
    dets = sampler.sample(
        shots=5_000,
        use_detector_reference_sample=True,
    )
    print(f"  bare tsim sampled shape: {dets.shape}")
    print(f"  bare tsim total events: {int(dets.sum())}")
    assert dets.shape[0] == 5_000
    assert dets.shape[1] == c.num_detectors


def test_sinter_task_accepts_tsim_circuit():
    """Sanity: sinter.Task duck-types the circuit type."""
    c = _build_minimal_nonclifford()
    task = sinter.Task(
        circuit=c,
        decoder="pymatching_tsim",
        skip_validation=True,  # skip stim-specific validation
    )
    assert task.circuit is c, "task should hold the tsim.Circuit by reference"
    # The DEM derivation is what sinter actually needs:
    dem = c.detector_error_model()
    print(f"  DEM has {dem.num_detectors} detectors, {dem.num_errors} error terms")
    assert dem.num_detectors == c.num_detectors


def test_sinter_collect_end_to_end_with_nonclifford():
    """THE KEY TEST: does sinter.collect() + our wrapper handle a non-Clifford circuit?"""
    c = _build_minimal_nonclifford()
    task = sinter.Task(
        circuit=c,
        decoder="pymatching_tsim",
        skip_validation=True,
    )

    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=3_000,
        max_errors=3_000,
        custom_decoders={"pymatching_tsim": TsimThenDecodeSampler(decoder_name="pymatching")},
        print_progress=False,
    )

    assert len(results) == 1
    stat = results[0]
    print(f"  sinter+tsim non-Clifford result:")
    print(f"    shots={stat.shots}, errors={stat.errors}, discards={stat.discards}")
    print(f"    logical error rate: {stat.errors/stat.shots:.4f}")
    print(f"    time: {stat.seconds:.2f}s")
    print(f"    strong_id: {stat.strong_id[:16]}...")

    assert stat.shots > 0
    assert stat.shots <= 3_000
    # With T gates and modest noise, we expect SOME logical error activity.
    # The absolute rate depends on details but should be in a sane range.
    error_rate = stat.errors / stat.shots
    assert 0.0 <= error_rate <= 0.6, f"error rate {error_rate:.4f} looks wrong"


if __name__ == "__main__":
    print("=== T5a: minimal non-Clifford circuit ===\n")

    tests = [
        ("test_circuit_is_not_clifford", test_circuit_is_not_clifford),
        ("test_tsim_can_sample_it_bare", test_tsim_can_sample_it_bare),
        ("test_sinter_task_accepts_tsim_circuit", test_sinter_task_accepts_tsim_circuit),
        ("test_sinter_collect_end_to_end_with_nonclifford", test_sinter_collect_end_to_end_with_nonclifford),
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
        print(f"T5a: {len(failed)}/{len(tests)} tests failed: {failed}")
        sys.exit(1)
    else:
        print("T5a ALL GREEN")
