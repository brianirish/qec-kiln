"""
T2b: multi-seed check on stim/tsim equivalence.

T2 passed but showed a 3.29-sigma disagreement on the global event count
(expected sigma=311, observed diff=1024, 1.9% deviation). This is borderline:
either a statistical fluke or a systematic bias.

If it's a fluke, running with multiple independent seeds should show the
disagreements distributed around zero. If it's a bias, the disagreements
will consistently lean one direction.

Run with:
    uv run --with bloqade-tsim --with stim python test_t2b_multiseed_check.py
"""
import math
import numpy as np
import stim
import tsim


def _build_surface_code_d3():
    return stim.Circuit.generated(
        "surface_code:rotated_memory_x",
        distance=3,
        rounds=3,
        after_clifford_depolarization=0.01,
        after_reset_flip_probability=0.01,
        before_measure_flip_probability=0.01,
        before_round_data_depolarization=0.01,
    )


def _sample_stim(c, shots, seed):
    return c.compile_detector_sampler(seed=seed).sample(shots=shots)


def _sample_tsim(c, shots, seed):
    return tsim.Circuit.from_stim_program(c).compile_detector_sampler(seed=seed).sample(
        shots=shots, use_detector_reference_sample=True,
    )


def main():
    circuit = _build_surface_code_d3()
    shots = 20_000
    n_dets = circuit.num_detectors

    print(f"Circuit: rotated_memory_x d=3 r=3 p=0.01, {n_dets} detectors")
    print(f"Shots per trial: {shots}")
    print(f"Total Bernoulli trials per simulator per run: {shots * n_dets:,}")
    print()
    print(f"{'seed':>6} {'stim_total':>11} {'tsim_total':>11} {'diff':>8} {'sigma':>7} {'rel_dev':>8}")
    print("-" * 60)

    diffs = []
    for seed in [1, 7, 13, 42, 99, 123, 256, 1024, 9999, 31415]:
        s = _sample_stim(circuit, shots, seed).sum()
        t = _sample_tsim(circuit, shots, seed).sum()
        diff = int(s) - int(t)
        # Sigma of the difference under independence:
        p = (s + t) / (2 * shots * n_dets)
        sigma_diff = math.sqrt(2 * shots * n_dets * p * (1 - p))
        n_sigma = diff / sigma_diff if sigma_diff > 0 else 0
        rel = diff / s if s > 0 else 0
        diffs.append((seed, int(s), int(t), diff, n_sigma, rel))
        print(f"{seed:>6} {int(s):>11} {int(t):>11} {diff:>+8} {n_sigma:>+7.2f} {rel:>+8.2%}")

    # Aggregate diagnostics
    print("-" * 60)
    n_sigmas = [d[4] for d in diffs]
    rel_devs = [d[5] for d in diffs]
    print(f"  mean n_sigma: {np.mean(n_sigmas):+.2f}  std: {np.std(n_sigmas):.2f}")
    print(f"  mean rel_dev: {np.mean(rel_devs):+.2%}")
    print()

    # If the differences are statistical, mean should be ~0 and std ~1
    # If there's a systematic bias, mean will be non-zero (e.g., +2 or -2)
    if abs(np.mean(n_sigmas)) > 1.5:
        print(f"  WARNING: mean disagreement is {np.mean(n_sigmas):+.2f} sigma -- looks systematic")
        print(f"  Sign: stim {'>' if np.mean(n_sigmas) > 0 else '<'} tsim consistently")
        print(f"  Magnitude: {np.mean(rel_devs):.1%} bias")
        print()
        print("  This is NOT a deal-breaker for the spike but is a finding worth")
        print("  investigating. Possible causes:")
        print("    1. Different noise channel sampling order between stim and tsim")
        print("    2. Different definition of 'detector flip' under reference subtraction")
        print("    3. The use_detector_reference_sample flag not doing exactly what I think")
        print("    4. Independent RNG streams happening to drift this run")
    else:
        print(f"  Mean disagreement {np.mean(n_sigmas):+.2f} sigma is consistent with statistical noise.")
        print(f"  Per-trial std {np.std(n_sigmas):.2f} (expected ~1 if pure stat noise).")


if __name__ == "__main__":
    main()
