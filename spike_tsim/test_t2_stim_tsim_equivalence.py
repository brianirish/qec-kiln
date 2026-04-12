"""
T2: stim and tsim agree statistically on a Clifford circuit.

The single most important correctness gate of this spike. If stim and
tsim disagree on per-detector flip rates beyond Poisson noise on a pure
Clifford circuit, the wrapper-via-sinter integration is meaningless --
we'd be measuring noise from a wrong simulator.

Methodology:
- Build a small surface code memory circuit (Clifford only, so both
  simulators MUST agree exactly modulo RNG seed)
- Sample N=20000 shots through each
- Compute per-detector flip rate
- Assert per-detector |stim_rate - tsim_rate| < 5 sigma where
  sigma = sqrt(p*(1-p)/N), using max(stim_p, tsim_p) for the std

Run with:
    uv run --with bloqade-tsim --with stim python test_t2_stim_tsim_equivalence.py
"""
import math
import sys

import numpy as np
import stim
import tsim


def _build_surface_code_d3():
    """Pure Clifford rotated surface code memory experiment.
    Same circuit family as the qec-kiln Stim benchmark."""
    return stim.Circuit.generated(
        "surface_code:rotated_memory_x",
        distance=3,
        rounds=3,
        after_clifford_depolarization=0.01,
        after_reset_flip_probability=0.01,
        before_measure_flip_probability=0.01,
        before_round_data_depolarization=0.01,
    )


def _sample_stim(circuit: stim.Circuit, shots: int, seed: int) -> np.ndarray:
    sampler = circuit.compile_detector_sampler(seed=seed)
    return sampler.sample(shots=shots)  # bool array (shots, num_detectors)


def _sample_tsim(circuit: stim.Circuit, shots: int, seed: int) -> np.ndarray:
    tcirc = tsim.Circuit.from_stim_program(circuit)
    sampler = tcirc.compile_detector_sampler(seed=seed)
    return sampler.sample(
        shots=shots,
        use_detector_reference_sample=True,  # match stim's flip-XOR convention
    )


def _per_detector_rates(samples: np.ndarray) -> np.ndarray:
    """Returns the fraction of shots in which each detector fired (1.0 = always)."""
    return samples.mean(axis=0)


def test_per_detector_rates_agree_within_5_sigma():
    circuit = _build_surface_code_d3()
    n_dets = circuit.num_detectors
    print(f"  circuit: rotated surface code d=3 r=3 p=0.01, {n_dets} detectors")

    shots = 20_000
    print(f"  sampling stim ({shots} shots)...")
    stim_samples = _sample_stim(circuit, shots=shots, seed=12345)
    print(f"  sampling tsim ({shots} shots)...")
    tsim_samples = _sample_tsim(circuit, shots=shots, seed=12345)

    assert stim_samples.shape == tsim_samples.shape, \
        f"shape mismatch: stim {stim_samples.shape} vs tsim {tsim_samples.shape}"

    stim_rates = _per_detector_rates(stim_samples)
    tsim_rates = _per_detector_rates(tsim_samples)

    print(f"  stim rate range: [{stim_rates.min():.4f}, {stim_rates.max():.4f}]")
    print(f"  tsim rate range: [{tsim_rates.min():.4f}, {tsim_rates.max():.4f}]")

    # Per-detector 5-sigma test using the larger of the two estimates for sigma
    failures = []
    for i in range(n_dets):
        sp, tp = stim_rates[i], tsim_rates[i]
        p_max = max(sp, tp, 1e-6)
        sigma = math.sqrt(p_max * (1 - p_max) / shots)
        diff = abs(sp - tp)
        n_sigma = diff / sigma if sigma > 0 else 0
        if n_sigma > 5.0:
            failures.append((i, sp, tp, diff, n_sigma))

    if failures:
        print(f"\n  FAIL: {len(failures)} detectors disagree beyond 5 sigma:")
        for i, sp, tp, diff, ns in failures[:10]:
            print(f"    det[{i:3d}]: stim={sp:.4f} tsim={tp:.4f} diff={diff:.4f} ({ns:.1f} sigma)")
        raise AssertionError(
            f"{len(failures)}/{n_dets} detector rates disagree between stim and tsim "
            f"beyond 5 sigma at N={shots}"
        )

    max_n_sigma = max(
        abs(stim_rates[i] - tsim_rates[i]) /
        max(math.sqrt(max(stim_rates[i], tsim_rates[i], 1e-6) *
                      (1 - max(stim_rates[i], tsim_rates[i], 1e-6)) / shots), 1e-12)
        for i in range(n_dets)
    )
    print(f"  PASS: max per-detector deviation = {max_n_sigma:.2f} sigma")


def test_global_detector_event_total_agrees():
    """Cross-check: total number of detection events across all shots and detectors should agree."""
    circuit = _build_surface_code_d3()
    shots = 20_000
    stim_samples = _sample_stim(circuit, shots=shots, seed=99)
    tsim_samples = _sample_tsim(circuit, shots=shots, seed=99)

    stim_total = int(stim_samples.sum())
    tsim_total = int(tsim_samples.sum())
    n_dets = circuit.num_detectors

    # Expected std on the difference (treating each shot/detector as independent Bernoulli):
    p_est = stim_total / (shots * n_dets)
    sigma = math.sqrt(2 * shots * n_dets * p_est * (1 - p_est))
    diff = abs(stim_total - tsim_total)
    n_sigma = diff / sigma if sigma > 0 else 0

    print(f"  stim total events: {stim_total}, tsim total events: {tsim_total}")
    print(f"  diff = {diff}, expected sigma = {sigma:.1f}, n_sigma = {n_sigma:.2f}")

    assert n_sigma < 5.0, \
        f"Total detection event counts differ by {n_sigma:.1f} sigma (>5)"
    print(f"  PASS: total event counts agree within {n_sigma:.2f} sigma")


if __name__ == "__main__":
    print("=== T2: stim/tsim statistical equivalence on Clifford circuit ===\n")
    print("test_per_detector_rates_agree_within_5_sigma:")
    try:
        test_per_detector_rates_agree_within_5_sigma()
    except AssertionError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)
    print()
    print("test_global_detector_event_total_agrees:")
    try:
        test_global_detector_event_total_agrees()
    except AssertionError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)
    print()
    print("T2 ALL GREEN")
