"""
T2d: try the opposite reference-sample convention.

T2c found a real systematic bias on the surface code (worsens with distance).
Hypothesis: maybe my use_detector_reference_sample=True is wrong somehow.

Run with:
    uv run --with bloqade-tsim --with stim python test_t2d_convention_flip.py
"""
import math
import numpy as np
import stim
import tsim


def _build_surf_d5():
    return stim.Circuit.generated(
        "surface_code:rotated_memory_x",
        distance=5,
        rounds=5,
        after_clifford_depolarization=0.01,
        after_reset_flip_probability=0.01,
        before_measure_flip_probability=0.01,
        before_round_data_depolarization=0.01,
    )


def main():
    c = _build_surf_d5()
    shots = 20_000
    seed = 42

    print(f"Circuit: rotated_memory_x d=5 r=5 p=0.01, {c.num_detectors} detectors, {c.num_observables} observables")
    print(f"Shots: {shots}")
    print()

    # Stim baseline
    stim_dets, stim_obs = c.compile_detector_sampler(seed=seed).sample(
        shots=shots, separate_observables=True
    )
    stim_det_total = int(stim_dets.sum())
    stim_obs_total = int(stim_obs.sum())
    print(f"  stim:                            det={stim_det_total:>7d}  obs={stim_obs_total:>5d}")

    # Tsim with various flag combinations
    tcirc = tsim.Circuit.from_stim_program(c)

    configs = [
        ("ref_det=True, ref_obs=True", True, True),
        ("ref_det=False, ref_obs=False", False, False),
        ("ref_det=True, ref_obs=False", True, False),
        ("ref_det=False, ref_obs=True", False, True),
    ]

    for label, rd, ro in configs:
        sampler = tcirc.compile_detector_sampler(seed=seed)
        td, to = sampler.sample(
            shots=shots,
            separate_observables=True,
            use_detector_reference_sample=rd,
            use_observable_reference_sample=ro,
        )
        td_total = int(td.sum())
        to_total = int(to.sum())
        det_diff = stim_det_total - td_total
        obs_diff = stim_obs_total - to_total
        det_dev = det_diff / stim_det_total
        obs_dev = obs_diff / stim_obs_total if stim_obs_total > 0 else 0
        print(f"  tsim {label:<30}  det={td_total:>7d}  obs={to_total:>5d}  "
              f"(det dev {det_dev:+.2%}, obs dev {obs_dev:+.2%})")

    print()
    print("Whichever combination gives det dev close to 0% is the correct convention.")
    print("If NONE give close-to-zero, the bias is real and not a flag issue.")


if __name__ == "__main__":
    main()
