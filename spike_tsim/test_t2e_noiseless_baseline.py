"""
T2e: noiseless baseline.

A noiseless Clifford QEC circuit should give zero detection events from both
stim and tsim. If both give zero, the bias seen in T2c/T2d comes from how
they apply noise channels differently. If tsim gives non-zero on a noiseless
circuit, that's a deeper bug.

Then a very-low-noise test (p=1e-4) where any bias should be tiny in absolute
terms but a fractional bias would show up.

Run with:
    uv run --with bloqade-tsim --with stim python test_t2e_noiseless_baseline.py
"""
import stim, tsim


def measure(circuit, shots, seed, label):
    s = circuit.compile_detector_sampler(seed=seed).sample(shots=shots, separate_observables=True)
    s_dets, s_obs = s
    t = tsim.Circuit.from_stim_program(circuit).compile_detector_sampler(seed=seed).sample(
        shots=shots, separate_observables=True,
        use_detector_reference_sample=True, use_observable_reference_sample=True,
    )
    t_dets, t_obs = t
    print(f"  {label}")
    print(f"    stim: dets={int(s_dets.sum()):>6d}  obs={int(s_obs.sum()):>5d}")
    print(f"    tsim: dets={int(t_dets.sum()):>6d}  obs={int(t_obs.sum()):>5d}")
    if s_dets.sum() != t_dets.sum() or s_obs.sum() != t_obs.sum():
        print(f"    MISMATCH (dets diff: {int(s_dets.sum() - t_dets.sum())}, obs diff: {int(s_obs.sum() - t_obs.sum())})")
    else:
        print("    EXACT AGREEMENT")
    print()


def main():
    print("=== T2e: noiseless and very-low-noise baselines ===\n")

    # 1. Pure noiseless surface code -- BOTH should give exactly 0 events
    c1 = stim.Circuit.generated(
        "surface_code:rotated_memory_x", distance=5, rounds=5,
        after_clifford_depolarization=0.0,
        after_reset_flip_probability=0.0,
        before_measure_flip_probability=0.0,
        before_round_data_depolarization=0.0,
    )
    measure(c1, shots=1000, seed=42,
            label="surface_code d=5 r=5 NOISELESS (expect 0/0)")

    # 2. Very low noise -- tiny absolute counts, fractional bias visible
    c2 = stim.Circuit.generated(
        "surface_code:rotated_memory_x", distance=5, rounds=5,
        after_clifford_depolarization=0.0001,
        after_reset_flip_probability=0.0001,
        before_measure_flip_probability=0.0001,
        before_round_data_depolarization=0.0001,
    )
    measure(c2, shots=20_000, seed=42,
            label="surface_code d=5 r=5 p=0.0001 (very low noise)")

    # 3. Noise only at one channel at a time, to localize the bias
    print("=== Single-channel noise tests (d=5 surf, p=0.01 only on one channel) ===\n")
    for noise_type in [
        "after_clifford_depolarization",
        "after_reset_flip_probability",
        "before_measure_flip_probability",
        "before_round_data_depolarization",
    ]:
        kwargs = {
            "after_clifford_depolarization": 0.0,
            "after_reset_flip_probability": 0.0,
            "before_measure_flip_probability": 0.0,
            "before_round_data_depolarization": 0.0,
            noise_type: 0.01,
        }
        c = stim.Circuit.generated(
            "surface_code:rotated_memory_x", distance=5, rounds=5, **kwargs
        )
        measure(c, shots=20_000, seed=42, label=f"only {noise_type}=0.01")


if __name__ == "__main__":
    main()
