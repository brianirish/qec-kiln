#!/usr/bin/env python3
"""
Generate surface code circuit files for a threshold sweep.

This produces .stim files with Sinter-compatible filenames (key=value pairs
parsed by --metadata_func auto). These are standard Stim circuits — nothing
qec-kiln-specific about them.

Usage:
    python examples/generate_surface_codes.py
    python examples/generate_surface_codes.py --output-dir my_circuits/
    python examples/generate_surface_codes.py --distances 3 5 7 --noise-rates 0.001 0.01
"""

import argparse
import os

import stim


def main():
    parser = argparse.ArgumentParser(description="Generate surface code circuits")
    parser.add_argument("--output-dir", default="circuits", help="Output directory")
    parser.add_argument(
        "--distances", nargs="+", type=int, default=[3, 5, 7, 9, 11, 13],
        help="Code distances"
    )
    parser.add_argument(
        "--noise-rates", nargs="+", type=float,
        default=[0.0005, 0.001, 0.002, 0.003, 0.005, 0.008, 0.01],
        help="Physical error rates"
    )
    parser.add_argument(
        "--basis", choices=["X", "Z"], default="X",
        help="Memory basis"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    count = 0
    for p in args.noise_rates:
        for d in args.distances:
            circuit = stim.Circuit.generated(
                code_task=f"surface_code:rotated_memory_{'x' if args.basis == 'X' else 'z'}",
                distance=d,
                rounds=d,
                after_clifford_depolarization=p,
                after_reset_flip_probability=p,
                before_measure_flip_probability=p,
                before_round_data_depolarization=p,
            )

            # Sinter's --metadata_func auto parses this filename format
            filename = f"d={d},p={p},b={args.basis},type=rotated_surface_memory.stim"
            filepath = os.path.join(args.output_dir, filename)

            with open(filepath, "w") as f:
                print(circuit, file=f)

            count += 1

    total = len(args.distances) * len(args.noise_rates)
    print(f"Generated {count} circuit files in {args.output_dir}/")
    print(f"  Distances:   {args.distances}")
    print(f"  Noise rates: {args.noise_rates}")
    print(f"  Basis:       {args.basis}")
    print(f"\nNext: ./scripts/launch.sh {args.output_dir} --decoders pymatching")


if __name__ == "__main__":
    main()
