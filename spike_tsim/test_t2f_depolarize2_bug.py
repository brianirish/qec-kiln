"""
T2f: confirm tsim DEPOLARIZE2 differs from stim.

T2e localized the systematic bias to `after_clifford_depolarization` (which
applies DEPOLARIZE2 after 2-qubit gates). This test reproduces the bias on
a minimal hand-built circuit using ONLY DEPOLARIZE2, isolating tsim's bug.

Run with:
    uv run --with bloqade-tsim --with stim python test_t2f_depolarize2_bug.py
"""
import math
import stim, tsim


def main():
    print("=== T2f: targeted DEPOLARIZE2 test ===\n")

    # Build a minimal circuit: prep |0+>, CNOT, measure, with DEPOLARIZE2 after CNOT.
    # In the absence of noise, M0 should be 0 (|0> in Z basis), M1 should be 0 (|+> in Z basis... random).
    # Actually let's just build something with detectors.

    # Simplest: 2 qubit Bell pair preparation with detectors that flag DEPOLARIZE2 events.
    # Cleaner: take a stim-generated circuit and strip everything except the data depolarization.
    # Best: write our own. Two qubits, prepare |00>, apply CNOT 5 times (each with DEPOLARIZE2(p)),
    # measure both. Detectors are the parity of consecutive measurements.

    # Even simpler: a stim DEPOLARIZE2-only test.
    p = 0.05  # large noise so we get clear stats fast
    n_pairs = 100  # how many CNOT-and-DEPOLARIZE2 pairs to apply
    shots = 50_000

    c = stim.Circuit()
    c.append("R", [0, 1])
    for _ in range(n_pairs):
        c.append("CNOT", [0, 1])
        c.append("DEPOLARIZE2", [0, 1], p)
    c.append("M", [0, 1])
    # Detector: just compare M0 to its expected value (0)
    c.append("DETECTOR", [stim.target_rec(-2)])
    c.append("DETECTOR", [stim.target_rec(-1)])

    print(f"Circuit: |00> -> ({n_pairs}x CNOT + DEPOLARIZE2({p}))-> M0,M1, 2 detectors")
    print(f"Shots: {shots}")
    print()

    s_dets = c.compile_detector_sampler(seed=42).sample(shots=shots)
    s_total = int(s_dets.sum())
    s_rate = s_total / (shots * 2)
    print(f"  stim: total events = {s_total:>7d}  rate per detector per shot = {s_rate:.4f}")

    tcirc = tsim.Circuit.from_stim_program(c)
    t_dets = tcirc.compile_detector_sampler(seed=42).sample(
        shots=shots, use_detector_reference_sample=True,
    )
    t_total = int(t_dets.sum())
    t_rate = t_total / (shots * 2)
    print(f"  tsim: total events = {t_total:>7d}  rate per detector per shot = {t_rate:.4f}")

    diff = s_total - t_total
    p_avg = (s_total + t_total) / (2 * shots * 2)
    sigma = math.sqrt(2 * shots * 2 * p_avg * (1 - p_avg))
    n_sigma = diff / sigma
    rel = diff / s_total
    print()
    print(f"  diff:   {diff:+d}  ({rel:+.2%}, {n_sigma:+.1f} sigma)")

    if abs(n_sigma) > 5:
        print()
        print(f"  → CONFIRMED: tsim's DEPOLARIZE2 implementation differs from stim's at >{abs(n_sigma):.0f}-sigma level.")
        print(f"    Direction: {'stim > tsim' if diff > 0 else 'tsim > stim'} (bias of {abs(rel):.1%}).")
        print()
        print(f"  Implication: tsim's `after_clifford_depolarization` noise channel does NOT")
        print(f"  faithfully reproduce stim's. This is a REAL DIFFERENCE in the simulators,")
        print(f"  not a flag/convention issue. It propagates to logical error rates on any")
        print(f"  circuit that uses 2-qubit gates with depolarization (which is essentially")
        print(f"  all standard QEC threshold experiments).")
    elif abs(n_sigma) > 3:
        print(f"  → Likely confirmed but not at 5-sigma. Try larger shot count.")
    else:
        print(f"  → No significant disagreement. Surprising given the surface code result.")
        print(f"    May indicate the bias is only in interaction with detector circuits.")


if __name__ == "__main__":
    main()
