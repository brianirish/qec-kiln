#!/usr/bin/env python3
"""
Generate K-round 5-qubit magic state distillation circuits for tsim benchmarks.

Produces .circuit files (tsim text format, NOT .stim) parameterized by
both T-count (via K independent distillation rounds) and noise rate.
These circuits contain T, T_DAG, and R_X gates which are non-Clifford
and require tsim's ZX stabilizer-rank simulator.

The base distillation protocol is the 5-qubit Reichardt-style magic state
distillation from tsim's own demo (docs/demos/magic_state_distillation.ipynb).
For K > 1, we compose K independent rounds on disjoint sets of 5 qubits,
giving total T-count = 12K. Disjoint placement avoids the basis-bookkeeping
subtleties of iterative composition while exercising the same stabilizer-rank
growth in tsim, since tsim's cost is driven by total T-count regardless of
which qubits the T gates act on.

Usage:
    python generate_tsim_circuits.py
    python generate_tsim_circuits.py --output-dir my_circuits/
    python generate_tsim_circuits.py --rounds 1 2 3 4 5 --noise-rates 0.001 0.01

Requires: pip install bloqade-tsim
"""

import argparse
import math
import os


THETA = -math.acos(math.sqrt(1 / 3)) / math.pi


def _round_block(qubits: tuple[int, int, int, int, int], p: float) -> list[str]:
    """Emit one round of 5-qubit distillation on the given disjoint qubit indices.

    The block prepares 5 noisy magic states, runs the distillation gates, and
    measures all 5 qubits. The caller is responsible for emitting DETECTOR and
    OBSERVABLE_INCLUDE annotations against the resulting measurement records.
    """
    q0, q1, q2, q3, q4 = qubits
    qall = f"{q0} {q1} {q2} {q3} {q4}"
    return [
        f"R {qall}",
        f"R_X({THETA}) {qall}",
        f"T_DAG {qall}",
        f"DEPOLARIZE1({p}) {qall}",
        f"SQRT_X {q0} {q1} {q4}",
        f"CZ {q0} {q1} {q2} {q3}",
        f"SQRT_Y {q0} {q3}",
        f"CZ {q0} {q2} {q3} {q4}",
        "TICK",
        f"SQRT_X_DAG {q0}",
        f"CZ {q0} {q4} {q1} {q3}",
        "TICK",
        f"SQRT_X_DAG {qall}",
        f"T {q0}",
        f"R_X({-THETA}) {q0}",
        f"M {qall}",
    ]


def build_distillation_circuit_text(K: int, p: float) -> str:
    """Build K independent rounds of 5-qubit distillation in one circuit.

    Each round occupies 5 disjoint qubits. Total qubits = 5K, total
    T-count = 12K. After all measurements, we emit 4 syndrome detectors
    and 1 observable per round, using rec[] indices counted from the end.

    Args:
        K: Number of independent distillation rounds (T-count = 12*K).
        p: Depolarizing noise rate applied after magic state preparation.
    """
    if K < 1:
        raise ValueError(f"K must be >= 1, got {K}")

    lines: list[str] = []
    for k in range(K):
        base = 5 * k
        qubits = (base, base + 1, base + 2, base + 3, base + 4)
        lines.extend(_round_block(qubits, p))

    # All measurements are now appended to the rec stack. Round k contributed
    # 5 measurements in order [q0, q1, q2, q3, q4]. Round K-1 is most recent.
    # rec[-1] is the last measurement (q4 of round K-1), rec[-5] is q0 of K-1,
    # rec[-6] is q4 of K-2, etc.
    for k in range(K):
        rounds_after_this = K - 1 - k
        offset = 5 * rounds_after_this
        # qubits in measurement order: q0, q1, q2, q3, q4
        # rec offsets from end: -(offset+5), -(offset+4), -(offset+3), -(offset+2), -(offset+1)
        rec_q0 = -(offset + 5)
        rec_q1 = -(offset + 4)
        rec_q2 = -(offset + 3)
        rec_q3 = -(offset + 2)
        rec_q4 = -(offset + 1)
        lines.append(f"DETECTOR rec[{rec_q1}]")
        lines.append(f"DETECTOR rec[{rec_q2}]")
        lines.append(f"DETECTOR rec[{rec_q3}]")
        lines.append(f"DETECTOR rec[{rec_q4}]")
        lines.append(f"OBSERVABLE_INCLUDE({k}) rec[{rec_q0}]")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate K-round 5-qubit magic state distillation circuits for tsim"
    )
    parser.add_argument("--output-dir", default="circuits_tsim")
    parser.add_argument(
        "--rounds", nargs="+", type=int,
        default=[1, 2, 3, 4, 5],
        help="K values: number of independent distillation rounds (T-count = 12K)",
    )
    parser.add_argument(
        "--noise-rates", nargs="+", type=float,
        default=[0.001, 0.003, 0.01, 0.03, 0.05],
        help="Physical error rates for DEPOLARIZE1",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    count = 0
    for K in args.rounds:
        for p in args.noise_rates:
            circuit_text = build_distillation_circuit_text(K, p)
            filename = f"distillation_K={K}_p={p}.circuit"
            filepath = os.path.join(args.output_dir, filename)
            with open(filepath, "w") as f:
                f.write(circuit_text)
            count += 1

    print(f"Generated {count} distillation circuit files in {args.output_dir}/")
    print(f"  K (rounds): {args.rounds}  -> T-counts: {[12*k for k in args.rounds]}")
    print(f"  Noise rates: {args.noise_rates}")
    print(f"  Total circuits: {len(args.rounds)} * {len(args.noise_rates)} = {count}")
    print(f"\nThese require tsim (not Stim) for simulation.")


if __name__ == "__main__":
    main()
