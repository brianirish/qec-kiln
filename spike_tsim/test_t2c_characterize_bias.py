"""
T2c: characterize the stim/tsim disagreement.

T2b found a ~1.3% systematic bias where stim reports more detection events
than tsim across many seeds. This script characterizes the bias to determine
if the integration is usable for the qec-kiln benchmark.

Specifically I want to know:
1. Does the bias appear on a simple repetition code, or only on the surface code?
2. Does it appear at lower noise rates?
3. Does it appear in the memory_z basis as well as memory_x?
4. **Most importantly**: do the logical observable rates agree, even if the
   detector rates don't? Logical error rate is what the benchmark actually
   measures.

Run with:
    uv run --with bloqade-tsim --with stim python test_t2c_characterize_bias.py
"""
import math
from dataclasses import dataclass

import numpy as np
import stim
import tsim


@dataclass
class Result:
    name: str
    n_dets: int
    n_obs: int
    shots: int
    stim_det_total: int
    tsim_det_total: int
    stim_obs_flips: int
    tsim_obs_flips: int

    @property
    def det_rel_dev(self) -> float:
        s = self.stim_det_total
        return (s - self.tsim_det_total) / s if s > 0 else 0

    @property
    def obs_rel_dev(self) -> float:
        s = self.stim_obs_flips
        if s == 0:
            return 0
        return (s - self.tsim_obs_flips) / s

    @property
    def det_n_sigma(self) -> float:
        n = self.shots * self.n_dets
        p = (self.stim_det_total + self.tsim_det_total) / (2 * n)
        sigma = math.sqrt(2 * n * p * (1 - p))
        return (self.stim_det_total - self.tsim_det_total) / sigma if sigma > 0 else 0

    @property
    def obs_n_sigma(self) -> float:
        n = self.shots * self.n_obs
        p = (self.stim_obs_flips + self.tsim_obs_flips) / (2 * n)
        if p <= 0:
            return 0
        sigma = math.sqrt(2 * n * p * (1 - p))
        return (self.stim_obs_flips - self.tsim_obs_flips) / sigma if sigma > 0 else 0


def _build(name: str, code: str, distance: int, rounds: int, p: float):
    return name, stim.Circuit.generated(
        code,
        distance=distance,
        rounds=rounds,
        after_clifford_depolarization=p,
        after_reset_flip_probability=p,
        before_measure_flip_probability=p,
        before_round_data_depolarization=p,
    )


def _measure(label: str, circuit: stim.Circuit, shots: int, seed: int) -> Result:
    # stim
    stim_dets, stim_obs = circuit.compile_detector_sampler(seed=seed).sample(
        shots=shots, separate_observables=True
    )
    # tsim
    tcirc = tsim.Circuit.from_stim_program(circuit)
    tsim_dets, tsim_obs = tcirc.compile_detector_sampler(seed=seed).sample(
        shots=shots,
        separate_observables=True,
        use_detector_reference_sample=True,
        use_observable_reference_sample=True,
    )
    return Result(
        name=label,
        n_dets=circuit.num_detectors,
        n_obs=circuit.num_observables,
        shots=shots,
        stim_det_total=int(stim_dets.sum()),
        tsim_det_total=int(tsim_dets.sum()),
        stim_obs_flips=int(stim_obs.sum()),
        tsim_obs_flips=int(tsim_obs.sum()),
    )


def main():
    shots = 20_000
    seed = 42

    cases = [
        _build("rep d=3 p=0.05", "repetition_code:memory", 3, 3, 0.05),
        _build("rep d=5 p=0.05", "repetition_code:memory", 5, 5, 0.05),
        _build("rep d=3 p=0.001", "repetition_code:memory", 3, 3, 0.001),
        _build("surf_x d=3 p=0.001", "surface_code:rotated_memory_x", 3, 3, 0.001),
        _build("surf_x d=3 p=0.01", "surface_code:rotated_memory_x", 3, 3, 0.01),
        _build("surf_x d=5 p=0.01", "surface_code:rotated_memory_x", 5, 5, 0.01),
        _build("surf_z d=3 p=0.01", "surface_code:rotated_memory_z", 3, 3, 0.01),
    ]

    results = []
    print(f"{'circuit':<22} {'n_det':>5} {'n_obs':>5} {'det_diff':>10} {'det_dev':>9} {'det_sig':>8} {'obs_stim':>9} {'obs_tsim':>9} {'obs_dev':>9} {'obs_sig':>8}")
    print("-" * 110)
    for name, circuit in cases:
        r = _measure(name, circuit, shots=shots, seed=seed)
        results.append(r)
        print(f"{r.name:<22} {r.n_dets:>5} {r.n_obs:>5} "
              f"{r.stim_det_total - r.tsim_det_total:>+10d} {r.det_rel_dev:>+9.2%} {r.det_n_sigma:>+8.2f} "
              f"{r.stim_obs_flips:>9d} {r.tsim_obs_flips:>9d} {r.obs_rel_dev:>+9.2%} {r.obs_n_sigma:>+8.2f}")

    print("-" * 110)
    print()

    # Diagnosis: is the obs disagreement smaller than the det disagreement?
    det_devs = [abs(r.det_rel_dev) for r in results]
    obs_devs = [abs(r.obs_rel_dev) for r in results if r.stim_obs_flips > 0]
    print(f"  Mean |det relative dev|: {np.mean(det_devs):.2%}")
    print(f"  Mean |obs relative dev|: {np.mean(obs_devs):.2%}" if obs_devs else "  No obs flips observed")
    print()

    if obs_devs and np.mean(obs_devs) < 0.05:
        print(f"  → Logical error rates agree within 5% on average across configurations.")
        print(f"  → This means the integration is usable for measuring logical")
        print(f"    error rates (the actual paper metric), even though detector")
        print(f"    rates show a small systematic bias.")
    elif obs_devs:
        print(f"  → Logical error rates disagree by {np.mean(obs_devs):.1%} on average.")
        print(f"  → INTEGRATION IS NOT USABLE without understanding this bias.")


if __name__ == "__main__":
    main()
