"""
T5c: sanity cross-check, bare tsim vs sinter+tsim.

T5a proved the wrapper returns TaskStats without crashing. This test goes
further: it samples the SAME non-Clifford circuit through two paths:
  (a) bare tsim (no sinter involvement)
  (b) sinter.collect() + our wrapper with count_detection_events=True

and verifies they produce statistically equivalent detection event rates.

This is important because:
- T2 found a bias in tsim's Clifford sparse geometric sampler. We want to
  confirm the NON-Clifford path doesn't have a similar bias at the sampling
  level, independently of the decoder stage.
- Any discrepancy between bare tsim and sinter+tsim on the same circuit
  would indicate a bug in OUR wrapper, not in tsim.

Run with:
    uv run --with bloqade-tsim --with stim --with sinter --with pymatching python test_t5c_wrapper_fidelity.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import sinter
import tsim

sys.path.insert(0, str(Path(__file__).parent))
from tsim_sampler import TsimThenDecodeSampler


def _build_circuit():
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


def _bare_tsim_rates(circuit, shots):
    """Sample circuit directly with tsim, return per-detector flip rate."""
    sampler = circuit.compile_detector_sampler(seed=None)
    dets = sampler.sample(
        shots=shots,
        use_detector_reference_sample=True,
    )
    # dets shape: (shots, num_detectors), dtype bool
    return dets.mean(axis=0), int(dets.sum())


def _sinter_wrapped_rates(circuit, shots):
    """Sample the same circuit via sinter.collect() with count_detection_events."""
    task = sinter.Task(
        circuit=circuit,
        decoder="pymatching_tsim",
        skip_validation=True,
    )
    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=shots,
        max_errors=shots,  # don't early-stop
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
    # custom_counts has 'detectors_checked' (total dets * shots) and 'detection_events'
    total_checks = stat.custom_counts.get('detectors_checked', 0)
    total_events = stat.custom_counts.get('detection_events', 0)
    global_rate = total_events / total_checks if total_checks > 0 else 0
    return global_rate, total_events, stat.shots, stat.errors


def main():
    circuit = _build_circuit()
    shots = 10_000
    n_det = circuit.num_detectors

    print(f"Circuit: minimal non-Clifford (tcount={circuit.tcount()}), {n_det} detectors")
    print(f"Shots: {shots}")
    print()

    # Run bare tsim
    print("bare tsim:")
    bare_rates, bare_total = _bare_tsim_rates(circuit, shots)
    for i, r in enumerate(bare_rates):
        print(f"  det[{i}] rate = {r:.4f}")
    bare_global = bare_total / (shots * n_det)
    print(f"  global rate = {bare_global:.4f}  ({bare_total} events / {shots * n_det} checks)")
    print()

    # Run sinter + tsim wrapper
    print("sinter + tsim wrapper:")
    sinter_global, sinter_events, sinter_shots, sinter_errs = _sinter_wrapped_rates(circuit, shots)
    print(f"  global rate = {sinter_global:.4f}  ({sinter_events} events / {sinter_shots * n_det} checks)")
    print(f"  logical errors = {sinter_errs}/{sinter_shots}")
    print()

    # Compare
    diff = bare_global - sinter_global
    sigma = math.sqrt(2 * bare_global * (1 - bare_global) / (shots * n_det))
    n_sigma = diff / sigma if sigma > 0 else 0
    rel = diff / bare_global if bare_global > 0 else 0

    print(f"Wrapper fidelity check:")
    print(f"  bare tsim rate:         {bare_global:.4f}")
    print(f"  sinter+tsim rate:       {sinter_global:.4f}")
    print(f"  diff:                   {diff:+.4f}")
    print(f"  relative deviation:     {rel:+.2%}")
    print(f"  n_sigma:                {n_sigma:+.2f}")
    print()

    if abs(n_sigma) < 3:
        print("PASS: wrapper produces statistically equivalent detection rates to bare tsim")
        print("  → the wrapper adds no bias of its own")
        return 0
    else:
        print(f"FAIL: wrapper deviates from bare tsim at {abs(n_sigma):.1f} sigma")
        print("  → our wrapper may be doing something wrong")
        return 1


if __name__ == "__main__":
    sys.exit(main())
