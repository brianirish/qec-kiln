#!/usr/bin/env python3
"""
Python runner for sinter collection with tsim circuits.

Replaces the `sinter collect` CLI for GPU jobs that need the
TsimThenDecodeSampler wrapper registered as a custom decoder.
Runs on GPU worker nodes inside Docker.

Usage:
    python collect_tsim.py \
        --circuits-dir circuits_tsim/ \
        --output-csv results.csv \
        --max-shots 1000000 \
        --max-errors 10000

Requires: bloqade-tsim, stim, sinter, pymatching, numpy
"""
import argparse
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run sinter.collect() with TsimThenDecodeSampler on .circuit files"
    )
    parser.add_argument(
        "--circuits-dir", type=Path, required=True,
        help="Directory containing .circuit files (tsim text format)",
    )
    parser.add_argument(
        "--output-csv", type=Path, required=True,
        help="Output CSV path (parent dirs created if needed)",
    )
    parser.add_argument(
        "--max-shots", type=int, default=1_000_000,
        help="Maximum shots per task (default: 1000000)",
    )
    parser.add_argument(
        "--max-errors", type=int, default=10_000,
        help="Maximum errors per task (default: 10000)",
    )
    parser.add_argument(
        "--decoder", type=str, default="pymatching",
        help="Decoder name (default: pymatching)",
    )
    parser.add_argument(
        "--num-workers", type=str, default="auto",
        help="Number of sinter workers (default: auto, which uses 1 for GPU jobs)",
    )
    return parser.parse_args()


def load_tasks(circuits_dir: Path, decoder_key: str):
    """Load .circuit files as sinter Tasks with tsim.Circuit objects.

    tsim is imported lazily here for spawn-safety -- worker processes
    shouldn't pay the JAX import cost at module load time.
    """
    import tsim
    import sinter

    circuit_files = sorted(circuits_dir.glob("*.circuit"))
    if not circuit_files:
        print(f"ERROR: No .circuit files found in {circuits_dir}", file=sys.stderr)
        sys.exit(1)

    tasks = []
    for f in circuit_files:
        c = tsim.Circuit(f.read_text())
        tasks.append(sinter.Task(
            circuit=c,
            decoder=decoder_key,
            skip_validation=True,
        ))

    return tasks, circuit_files


def main():
    args = parse_args()

    decoder_key = f"{args.decoder}_tsim"
    num_workers = 1 if args.num_workers == "auto" else int(args.num_workers)

    tasks, circuit_files = load_tasks(args.circuits_dir, decoder_key)
    print(f"Loaded {len(tasks)} circuit(s) from {args.circuits_dir}")

    # Import here (after load_tasks) to keep top-level imports minimal
    import sinter
    from tsim_sampler import TsimThenDecodeSampler

    sampler = TsimThenDecodeSampler(decoder_name=args.decoder)

    print(f"Collecting: max_shots={args.max_shots}, max_errors={args.max_errors}, "
          f"num_workers={num_workers}, decoder={decoder_key}")

    results = sinter.collect(
        num_workers=num_workers,
        tasks=tasks,
        max_shots=args.max_shots,
        max_errors=args.max_errors,
        custom_decoders={decoder_key: sampler},
    )

    # Write CSV output
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_csv, "w") as f:
        f.write(sinter.CSV_HEADER + "\n")
        for stat in results:
            f.write(stat.to_csv_line() + "\n")

    # Summary
    total_shots = sum(s.shots for s in results)
    total_errors = sum(s.errors for s in results)
    print(f"\nDone: {len(results)} circuit(s), {total_shots} total shots, {total_errors} total errors")
    print(f"Output: {args.output_csv}")


if __name__ == "__main__":
    main()
