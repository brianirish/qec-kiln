#!/usr/bin/env python3
"""
Partition .stim circuit files into balanced batches for distribution
across SkyPilot jobs.

Circuits are distributed round-robin by default. For smarter partitioning
(e.g., grouping by estimated runtime), use --strategy.

Usage:
    python scripts/partition.py circuits/ --circuits-per-job 6
    python scripts/partition.py circuits/ --num-jobs 10
    python scripts/partition.py circuits/ --circuits-per-job 6 --output-dir /tmp/batches
"""

import argparse
import math
import os
import shutil
import sys
from pathlib import Path


def find_circuits(input_dir: str) -> list[Path]:
    """Find all .stim files in the input directory."""
    circuits = sorted(Path(input_dir).glob("**/*.stim"))
    if not circuits:
        print(f"No .stim files found in {input_dir}")
        sys.exit(1)
    return circuits


def partition_round_robin(circuits: list[Path], num_jobs: int) -> list[list[Path]]:
    """Distribute circuits across jobs round-robin."""
    batches: list[list[Path]] = [[] for _ in range(num_jobs)]
    for i, circuit in enumerate(circuits):
        batches[i % num_jobs].append(circuit)
    return [b for b in batches if b]  # remove empty batches


def write_batches(batches: list[list[Path]], output_dir: str, copy_files: bool = True):
    """Write batches to output directories, optionally copying files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for i, batch in enumerate(batches):
        batch_dir = out / f"batch_{i}"
        batch_dir.mkdir(parents=True, exist_ok=True)

        for circuit in batch:
            if copy_files:
                shutil.copy2(circuit, batch_dir / circuit.name)
            else:
                # Create symlinks for local testing
                link = batch_dir / circuit.name
                if not link.exists():
                    link.symlink_to(circuit.resolve())

        print(f"  batch_{i}: {len(batch)} circuits")


def main():
    parser = argparse.ArgumentParser(description="Partition .stim circuits into batches")
    parser.add_argument("input_dir", help="Directory containing .stim files")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--circuits-per-job", type=int, help="Max circuits per SkyPilot job")
    group.add_argument("--num-jobs", type=int, help="Exact number of jobs to create")

    parser.add_argument("--output-dir", default="./batches", help="Where to write batch directories")
    parser.add_argument("--symlink", action="store_true", help="Use symlinks instead of copying files")
    args = parser.parse_args()

    circuits = find_circuits(args.input_dir)
    print(f"Found {len(circuits)} circuit files")

    if args.circuits_per_job:
        num_jobs = math.ceil(len(circuits) / args.circuits_per_job)
    else:
        num_jobs = min(args.num_jobs, len(circuits))

    print(f"Partitioning into {num_jobs} batches:")
    batches = partition_round_robin(circuits, num_jobs)
    write_batches(batches, args.output_dir, copy_files=not args.symlink)

    print(f"\nBatches written to {args.output_dir}/")
    print(f"Next: upload to cloud storage and launch jobs")


if __name__ == "__main__":
    main()
