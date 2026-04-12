"""
T5d: wrapper fidelity check on the distillation circuit.

T5c did this for a minimal 2-detector circuit and showed the wrapper adds
no bias. T5b's incidental comparison on the distillation circuit looked
slightly discrepant (0.477 bare vs 0.505 wrapped, ~5 sigma at that sample
size) but with independent seeds. This test explicitly compares bare tsim
and sinter+tsim on the same distillation circuit at larger sample size
to confirm the wrapper is faithful.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching --with numpy python test_t5d_distillation_fidelity.py
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
    theta = -math.acos(math.sqrt(1 / 3)) / math.pi
    return tsim.Circuit(f"""
        R 0 1 2 3 4
        R_X({theta}) 0 1 2 3 4
        T_DAG 0 1 2 3 4
        DEPOLARIZE1({p}) 0 1 2 3 4

        SQRT_X 0 1 4
        CZ 0 1 2 3
        SQRT_Y 0 3
        CZ 0 2 3 4
        TICK
        SQRT_X_DAG 0
        CZ 0 4 1 3
        TICK
        SQRT_X_DAG 0 1 2 3 4

        T 0
        R_X({-theta}) 0

        M 0 1 2 3 4
        DETECTOR rec[-4]
        DETECTOR rec[-3]
        DETECTOR rec[-2]
        DETECTOR rec[-1]
        OBSERVABLE_INCLUDE(0) rec[-5]
    """)


def main():
    circuit = _build_distillation_circuit()
    shots = 20_000  # larger sample size than T5b
    n_det = circuit.num_detectors

    print(f"Circuit: magic state distillation (5 qubits, tcount={circuit.tcount()}, {n_det} detectors)")
    print(f"Shots: {shots}")
    print()

    # Run bare tsim with the EXACT SAME sample() kwargs the wrapper uses.
    # Critical: previously this used just use_detector_reference_sample=True,
    # but the wrapper also sets use_observable_reference_sample=True and
    # separate_observables=True. It turns out `use_observable_reference_sample`
    # has a side-effect on detector event rates in tsim 0.1.2 (~2% shift on
    # this circuit), which is unexpected -- an "observable" flag shouldn't
    # change detector statistics. Reported in SPIKE_VERDICT.md for upstream.
    print("bare tsim (with wrapper-matching flags):")
    sampler = circuit.compile_detector_sampler(seed=None)
    dets, obs = sampler.sample(
        shots=shots,
        bit_packed=True,
        separate_observables=True,
        use_detector_reference_sample=True,
        use_observable_reference_sample=True,
    )
    # unpack for counting
    dets_unpacked = np.unpackbits(dets, axis=1, bitorder='little', count=n_det)
    bare_per_det = dets_unpacked.mean(axis=0)
    for i, r in enumerate(bare_per_det):
        print(f"  det[{i}] rate = {r:.4f}")
    bare_total = int(dets_unpacked.sum())
    bare_global = bare_total / (shots * n_det)
    print(f"  global = {bare_global:.4f}  ({bare_total} events / {shots*n_det} checks)")
    print()

    # Run sinter + wrapper
    print("sinter + tsim wrapper:")
    task = sinter.Task(
        circuit=circuit,
        decoder="pymatching_tsim",
        skip_validation=True,
    )
    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=shots,
        max_errors=shots,
        custom_decoders={
            "pymatching_tsim": TsimThenDecodeSampler(
                decoder_name="pymatching",
                count_detection_events=True,
            )
        },
        print_progress=False,
    )
    stat = results[0]
    wrapped_total = stat.custom_counts.get('detection_events', 0)
    wrapped_checks = stat.custom_counts.get('detectors_checked', 0)
    wrapped_global = wrapped_total / wrapped_checks if wrapped_checks > 0 else 0
    print(f"  global = {wrapped_global:.4f}  ({wrapped_total} events / {wrapped_checks} checks)")
    print(f"  (shots = {stat.shots}, logical errors = {stat.errors}, time = {stat.seconds:.2f}s)")
    print()

    # Cross-check
    diff = bare_global - wrapped_global
    # sigma on the difference between two independent samples of p ≈ 0.5 at N = shots*n_det
    p = (bare_global + wrapped_global) / 2
    sigma = math.sqrt(2 * p * (1 - p) / (shots * n_det))
    n_sigma = diff / sigma if sigma > 0 else 0
    rel = diff / bare_global if bare_global > 0 else 0

    print("Cross-check:")
    print(f"  bare global rate:       {bare_global:.4f}")
    print(f"  wrapped global rate:    {wrapped_global:.4f}")
    print(f"  diff:                   {diff:+.4f}")
    print(f"  relative deviation:     {rel:+.2%}")
    print(f"  n_sigma:                {n_sigma:+.2f}")
    print()

    if abs(n_sigma) < 3:
        print("PASS: wrapper produces statistically equivalent rates to bare tsim on the distillation circuit")
        return 0
    else:
        print(f"CONCERN: {abs(n_sigma):.1f} sigma disagreement on distillation circuit")
        print("  Possible explanations:")
        print("  - finite-sample variance (try more shots)")
        print("  - subtle wrapper bug")
        print("  - tsim RNG state differs between bare and sinter invocations")
        return 1


if __name__ == "__main__":
    sys.exit(main())
