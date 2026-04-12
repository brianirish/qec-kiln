"""
T4: end-to-end logical error rate comparison, sinter+stim vs sinter+tsim.

Runs the same circuit through sinter with:
  (a) the default stim sampler
  (b) our TsimThenDecodeSampler wrapper
and compares logical error rates. Given T2's finding that tsim has a small
systematic disagreement with stim on surface code circuits, we expect some
disagreement here. The question is how much, and whether it's within a
reviewer's tolerance for using both interchangeably.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching python test_t4_end_to_end.py
"""
import math
import sys
from pathlib import Path

import sinter
import stim

sys.path.insert(0, str(Path(__file__).parent))
from tsim_sampler import TsimThenDecodeSampler


def _compare(label: str, circuit: stim.Circuit, shots: int):
    """Run circuit through sinter+stim and sinter+tsim, compare results."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"  num_detectors: {circuit.num_detectors}, num_observables: {circuit.num_observables}, shots: {shots}")

    # Run 1: sinter + stim default
    task_stim = sinter.Task(circuit=circuit, decoder="pymatching")
    stim_results = sinter.collect(
        num_workers=1,
        tasks=[task_stim],
        max_shots=shots,
        max_errors=shots,  # don't early-stop
        decoders=["pymatching"],
        print_progress=False,
    )
    assert len(stim_results) == 1
    s = stim_results[0]
    stim_rate = s.errors / s.shots
    stim_std = math.sqrt(stim_rate * (1 - stim_rate) / s.shots)
    print(f"  sinter+stim: {s.errors}/{s.shots} = {stim_rate:.4f} +/- {stim_std:.4f} "
          f"(time: {s.seconds:.2f}s)")

    # Run 2: sinter + tsim wrapper
    task_tsim = sinter.Task(circuit=circuit, decoder="pymatching_tsim")
    tsim_results = sinter.collect(
        num_workers=1,
        tasks=[task_tsim],
        max_shots=shots,
        max_errors=shots,
        custom_decoders={"pymatching_tsim": TsimThenDecodeSampler(decoder_name="pymatching")},
        print_progress=False,
    )
    assert len(tsim_results) == 1
    t = tsim_results[0]
    tsim_rate = t.errors / t.shots
    tsim_std = math.sqrt(tsim_rate * (1 - tsim_rate) / t.shots)
    print(f"  sinter+tsim: {t.errors}/{t.shots} = {tsim_rate:.4f} +/- {tsim_std:.4f} "
          f"(time: {t.seconds:.2f}s)")

    # Compare
    diff = stim_rate - tsim_rate
    combined_std = math.sqrt(stim_std**2 + tsim_std**2)
    n_sigma = diff / combined_std if combined_std > 0 else 0
    rel_diff = diff / stim_rate if stim_rate > 0 else 0
    print(f"  delta: {diff:+.4f} ({rel_diff:+.1%}, {n_sigma:+.2f} sigma)")

    return {
        "label": label,
        "stim_rate": stim_rate,
        "tsim_rate": tsim_rate,
        "stim_time": s.seconds,
        "tsim_time": t.seconds,
        "n_sigma": n_sigma,
        "rel_diff": rel_diff,
    }


def main():
    results = []

    # Case 1: repetition code — T2 showed rep code agrees
    rep_d3 = stim.Circuit.generated(
        "repetition_code:memory", distance=3, rounds=3,
        after_clifford_depolarization=0.05,
        after_reset_flip_probability=0.05,
        before_measure_flip_probability=0.05,
        before_round_data_depolarization=0.05,
    )
    results.append(_compare("repetition_code d=3 p=0.05", rep_d3, shots=10_000))

    # Case 2: surface code d=3 — T2 showed small disagreement
    surf_d3 = stim.Circuit.generated(
        "surface_code:rotated_memory_x", distance=3, rounds=3,
        after_clifford_depolarization=0.01,
        after_reset_flip_probability=0.01,
        before_measure_flip_probability=0.01,
        before_round_data_depolarization=0.01,
    )
    results.append(_compare("surface_code d=3 p=0.01", surf_d3, shots=10_000))

    # Case 3: surface code d=5 — T2 showed larger disagreement
    surf_d5 = stim.Circuit.generated(
        "surface_code:rotated_memory_x", distance=5, rounds=5,
        after_clifford_depolarization=0.01,
        after_reset_flip_probability=0.01,
        before_measure_flip_probability=0.01,
        before_round_data_depolarization=0.01,
    )
    results.append(_compare("surface_code d=5 p=0.01", surf_d5, shots=10_000))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY (logical error rates, sinter+stim vs sinter+tsim)")
    print("="*60)
    print(f"{'case':<30} {'stim':>8} {'tsim':>8} {'rel':>8} {'n_sigma':>8}")
    print("-" * 60)
    for r in results:
        print(f"{r['label']:<30} {r['stim_rate']:>8.4f} {r['tsim_rate']:>8.4f} "
              f"{r['rel_diff']:>+8.1%} {r['n_sigma']:>+8.2f}")

    worst_sigma = max(abs(r["n_sigma"]) for r in results)
    worst_rel = max(abs(r["rel_diff"]) for r in results)
    print()
    print(f"Worst case: {worst_sigma:.2f} sigma, {worst_rel:.1%} relative deviation")

    # Final verdict line
    if worst_sigma < 3:
        print()
        print("VERDICT: sinter+stim and sinter+tsim agree within ~3 sigma across all cases.")
        print("The integration is usable as a drop-in for the existing qec-kiln benchmark.")
    elif worst_rel < 0.08:
        print()
        print("VERDICT: sinter+stim and sinter+tsim disagree statistically but by <8% relative.")
        print("The integration works MECHANICALLY but NOT as a quantitative drop-in replacement.")
        print("Use tsim for circuits where stim can't run (non-Clifford), not to validate Clifford runs.")
    else:
        print()
        print("VERDICT: Significant disagreement (>8% relative). Integration unusable without root-cause fix.")


if __name__ == "__main__":
    main()
