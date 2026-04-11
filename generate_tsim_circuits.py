#!/usr/bin/env python3
"""
Generate 5-qubit magic state distillation circuits for tsim benchmarks.

Produces .circuit files (tsim text format, NOT .stim) parameterized by
noise rate. These circuits contain T, T_DAG, and R_X gates which are
non-Clifford and require tsim's ZX stabilizer-rank simulator.

The circuit is the 5-qubit distillation protocol from tsim's own demo
(docs/demos/magic_state_distillation.ipynb), annotated with DETECTOR
and OBSERVABLE_INCLUDE so sinter can run it.

Usage:
    python generate_tsim_circuits.py
    python generate_tsim_circuits.py --output-dir my_circuits/
    python generate_tsim_circuits.py --noise-rates 0.001 0.01 0.05

Requires: pip install bloqade-tsim
"""

import argparse
import math
import os


def build_distillation_circuit_text(p: float = 0.02) -> str:
    """Build the 5-qubit magic state distillation circuit as tsim text.

    The circuit has tcount=12, 4 detectors, 1 observable. It exercises
    tsim's non-Clifford ZX stabilizer-rank sampler -- exactly the code
    path the GPU benchmark needs.

    Args:
        p: Depolarizing noise rate applied to each qubit after the
           initial magic state preparation.
    """
    theta = -math.acos(math.sqrt(1 / 3)) / math.pi
    return "\n".join(line for line in f"""
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
""".strip().split("\n"))


def main():
    parser = argparse.ArgumentParser(
        description="Generate 5-qubit magic state distillation circuits for tsim"
    )
    parser.add_argument("--output-dir", default="circuits_tsim")
    parser.add_argument(
        "--noise-rates", nargs="+", type=float,
        default=[0.001, 0.005, 0.01, 0.02, 0.05],
        help="Physical error rates for DEPOLARIZE1",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    count = 0
    for p in args.noise_rates:
        circuit_text = build_distillation_circuit_text(p)
        filename = f"distillation_p={p}.circuit"
        filepath = os.path.join(args.output_dir, filename)

        with open(filepath, "w") as f:
            f.write(circuit_text)

        count += 1

    print(f"Generated {count} distillation circuit files in {args.output_dir}/")
    print(f"  Noise rates: {args.noise_rates}")
    print(f"  Circuit: 5-qubit magic state distillation (tcount=12)")
    print(f"\nThese require tsim (not Stim) for simulation.")


if __name__ == "__main__":
    main()
