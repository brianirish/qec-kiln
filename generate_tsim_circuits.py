#!/usr/bin/env python3
"""
Generate Clifford+T circuit files for use with tsim.

These circuits include T gates, which Stim cannot simulate but tsim can.
The resulting .stim files use the same Sinter-compatible naming convention.

Note: When running these through qec-kiln, use --gpu since tsim
benefits from CUDA acceleration.

Usage:
    python examples/generate_tsim_circuits.py
    python examples/generate_tsim_circuits.py --output-dir tsim_circuits/

Requires: pip install bloqade-tsim
"""

import argparse
import os


def build_clifford_t_circuit(
    code_distance: int,
    noise_rate: float,
    t_fraction: float = 0.33,
) -> str:
    """
    Build a circuit string with T gates that exercises tsim's non-Clifford
    simulation. Compatible with both stim and tsim file formats.

    The circuit includes Clifford gates, T gates on a fraction of qubits,
    entangling operations, depolarizing noise, and detector annotations.
    """
    n_qubits = code_distance ** 2
    t_qubits = list(range(0, n_qubits, int(1 / t_fraction))) if t_fraction > 0 else []

    lines = []

    # Reset
    lines.append(f"R {' '.join(str(i) for i in range(n_qubits))}")

    # Hadamard on even qubits
    lines.append(f"H {' '.join(str(i) for i in range(0, n_qubits, 2))}")

    # T gates — the non-Clifford component
    if t_qubits:
        lines.append(f"T {' '.join(str(i) for i in t_qubits)}")

    # Entangling layer
    lines.append("TICK")
    for i in range(n_qubits - 1):
        lines.append(f"CNOT {i} {i + 1}")

    # Noise
    lines.append("TICK")
    lines.append(f"DEPOLARIZE1({noise_rate}) {' '.join(str(i) for i in range(n_qubits))}")

    # Measure
    lines.append(f"M {' '.join(str(i) for i in range(n_qubits))}")

    # Detectors
    for i in range(n_qubits):
        lines.append(f"DETECTOR rec[{-n_qubits + i}]")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Clifford+T circuits for tsim")
    parser.add_argument("--output-dir", default="circuits_tsim")
    parser.add_argument(
        "--distances", nargs="+", type=int, default=[3, 5, 7, 9],
        help="Code distances"
    )
    parser.add_argument(
        "--noise-rates", nargs="+", type=float,
        default=[0.001, 0.003, 0.005, 0.01],
        help="Physical error rates"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    count = 0
    for p in args.noise_rates:
        for d in args.distances:
            circuit_str = build_clifford_t_circuit(d, p)

            filename = f"d={d},p={p},type=clifford_t_benchmark.stim"
            filepath = os.path.join(args.output_dir, filename)

            with open(filepath, "w") as f:
                f.write(circuit_str)

            count += 1

    t_count_example = len(list(range(0, args.distances[-1] ** 2, 3)))
    print(f"Generated {count} Clifford+T circuit files in {args.output_dir}/")
    print(f"  Distances:   {args.distances}")
    print(f"  Noise rates: {args.noise_rates}")
    print(f"  T gates (d={args.distances[-1]}): ~{t_count_example}")
    print(f"\nThese require tsim (not Stim) for simulation.")
    print(f"Next: ./scripts/launch.sh {args.output_dir} --gpu --decoders pymatching")


if __name__ == "__main__":
    main()
