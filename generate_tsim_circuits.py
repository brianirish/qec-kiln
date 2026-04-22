#!/usr/bin/env python3
"""
Generate K-round 5-qubit magic state distillation circuits for tsim benchmarks.

Produces .circuit files (tsim text format, NOT .stim) parameterized by
both T-count (via K independent distillation rounds) and noise rate.
These circuits contain T, T_DAG, and R_X gates which are non-Clifford
and require tsim's ZX stabilizer-rank simulator.

The base distillation protocol is the 5-qubit Reichardt-style magic state
distillation from tsim's own demo (docs/demos/magic_state_distillation.ipynb).
For K > 1, we compose K independent rounds on disjoint sets of 5 qubits.

## Observable and post-selection

The Reichardt protocol is *post-selected on the success syndrome*
[M1, M2, M3, M4] == [1, 0, 1, 1]. Only on that branch does the inverse
magic-state preparation (T; R_X(-theta)) on q0 map the distilled |T> back
to |0>, making M0 a meaningful fidelity indicator (M0 = 0 on success).

We encode the success syndrome as deterministic ancilla measurements:
for each round k we allocate 4 ancilla qubits (one per syndrome bit), prep
them to the expected [1, 0, 1, 1] via R + selective X, then M. Each
DETECTOR XORs one data-syndrome measurement against its ancilla expectation,
so the detector fires exactly when the syndrome bit deviates from success.
Sinter discards shots where any detector fires; on the surviving shots,
OBSERVABLE_INCLUDE(k) rec[...] = raw M0_k fires when q0 is measured as |1>
(distillation error).

This circuit family requires the tsim wrapper to be invoked with
use_reference_samples=False, because XOR-against-noiseless-reference
would subtract a random-syndrome-branch reference from every shot and
make post-selection meaningless. See `collect_tsim.py --no-reference-samples`.

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


def _round_gates(qubits: tuple[int, int, int, int, int], p: float) -> list[str]:
    """Emit the distillation gates for one round, ending with M on the 5 data qubits."""
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


# Success syndrome for Reichardt 5-to-1 distillation on [M1, M2, M3, M4].
SUCCESS_SYNDROME = (1, 0, 1, 1)


def build_distillation_circuit_text(K: int, p: float) -> str:
    """Build K independent rounds of 5-qubit distillation with ancilla-encoded post-selection.

    Qubit layout:
        Data qubits: 0 .. 5K-1  (5 per round, disjoint blocks)
        Ancillas:    5K .. 9K-1 (4 per round, encode success syndrome [1,0,1,1])

    Measurement order: all data measurements first (5K, in round-order q0..q4 per
    round), then all ancilla measurements (4K, in round-order a1..a4 per round).

    Detectors: 4K total, each XOR-ing one data syndrome bit against its ancilla.
    Observables: K total, each = raw M0 for that round (error = |1> on success branch).
    """
    if K < 1:
        raise ValueError(f"K must be >= 1, got {K}")

    data_qubit_count = 5 * K
    total_meas = 9 * K  # 5K data + 4K ancilla

    lines: list[str] = []

    # K distillation blocks on disjoint 5-qubit data registers.
    for k in range(K):
        base = 5 * k
        lines.extend(_round_gates((base, base + 1, base + 2, base + 3, base + 4), p))

    # Ancillas: prep deterministic [1, 0, 1, 1] per round, then measure.
    all_ancillas = list(range(data_qubit_count, data_qubit_count + 4 * K))
    lines.append("R " + " ".join(str(a) for a in all_ancillas))
    flipped = []
    for k in range(K):
        a1 = data_qubit_count + 4 * k + 0
        a2 = data_qubit_count + 4 * k + 1
        a3 = data_qubit_count + 4 * k + 2
        a4 = data_qubit_count + 4 * k + 3
        if SUCCESS_SYNDROME[0] == 1:
            flipped.append(a1)
        if SUCCESS_SYNDROME[1] == 1:
            flipped.append(a2)
        if SUCCESS_SYNDROME[2] == 1:
            flipped.append(a3)
        if SUCCESS_SYNDROME[3] == 1:
            flipped.append(a4)
    if flipped:
        lines.append("X " + " ".join(str(a) for a in flipped))
    lines.append("M " + " ".join(str(a) for a in all_ancillas))

    # rec index helpers (relative to final measurement list of length total_meas).
    def data_rec(k: int, i: int) -> int:
        # Data measurement q_i in round k. Position from start: 5k + i. Negative from end:
        return -(total_meas - (5 * k + i))

    def ancilla_rec(k: int, j: int) -> int:
        # Ancilla a_j in round k. Position from start: 5K + 4k + j.
        return -(total_meas - (5 * K + 4 * k + j))

    # Detectors: one per syndrome bit per round. Fires when M_{i+1} XOR a_i == 1,
    # i.e. when the syndrome bit deviates from the success pattern encoded in a_i.
    for k in range(K):
        for j in range(4):
            # data syndrome bit is M_{j+1} of this round.
            lines.append(f"DETECTOR rec[{data_rec(k, j + 1)}] rec[{ancilla_rec(k, j)}]")

    # Observables: raw M0 per round. On the post-selected success branch, noiseless
    # M0 = 0, so observable = 1 is a logical error.
    for k in range(K):
        lines.append(f"OBSERVABLE_INCLUDE({k}) rec[{data_rec(k, 0)}]")

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
    print(f"\nThese circuits REQUIRE --no-reference-samples on collect_tsim.py")
    print(f"and postselection_mask covering all detectors (sinter discards on syndrome deviation).")


if __name__ == "__main__":
    main()
