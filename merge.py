#!/usr/bin/env python3
"""
Merge Sinter CSV fragments from cloud storage into a single dataset.

Uses `sinter combine` under the hood, which aggregates rows by strong_id
(a cryptographic hash of the circuit + decoder), so duplicate or partial
data from spot preemption retries is handled correctly.

Usage:
    python scripts/merge.py --bucket s3://qec-kiln-results
    python scripts/merge.py --bucket s3://qec-kiln-results --out merged.csv
    python scripts/merge.py --local-dir ./results
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def sync_from_s3(bucket: str, local_dir: Path):
    """Download all CSV fragments from S3."""
    print(f"Syncing from {bucket}/ ...")
    subprocess.run(
        ["aws", "s3", "sync", f"{bucket}/", str(local_dir)],
        check=True,
    )


def find_csvs(base_dir: Path) -> list[Path]:
    """Find all stats.csv files in the results directory."""
    csvs = sorted(base_dir.rglob("stats.csv"))
    if not csvs:
        # Also look for any .csv files
        csvs = sorted(base_dir.rglob("*.csv"))
    return csvs


def merge_with_sinter(csv_files: list[Path], output: str):
    """
    Merge using sinter combine.

    sinter combine aggregates rows by strong_id, so if the same circuit
    was partially collected across multiple runs (e.g., due to spot
    preemption and retry), the statistics are correctly summed.
    """
    print(f"Merging {len(csv_files)} CSV fragments with sinter combine...")

    result = subprocess.run(
        ["sinter", "combine"] + [str(f) for f in csv_files],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"sinter combine failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    with open(output, "w") as f:
        f.write(result.stdout)

    # Count data lines (excluding header)
    lines = result.stdout.strip().split("\n")
    data_lines = len(lines) - 1 if len(lines) > 1 else 0

    print(f"Merged into {output}: {data_lines} data points")


def fallback_merge(csv_files: list[Path], output: str):
    """
    Simple concatenation fallback if sinter combine is unavailable.
    Preserves headers from the first file, skips headers from the rest.
    """
    print(f"Concatenating {len(csv_files)} CSV fragments (fallback)...")

    with open(output, "w") as out:
        for i, csv_file in enumerate(csv_files):
            with open(csv_file) as f:
                for j, line in enumerate(f):
                    # Write header only from first file
                    if j == 0 and i > 0:
                        continue
                    # Skip empty lines
                    if line.strip():
                        out.write(line)

    print(f"Concatenated into {output}")
    print("Note: use 'sinter combine' for proper deduplication by strong_id")


def main():
    parser = argparse.ArgumentParser(description="Merge Sinter CSV results")
    parser.add_argument("--bucket", type=str, help="S3/GCS bucket path")
    parser.add_argument("--local-dir", type=str, help="Local results directory")
    parser.add_argument("--out", type=str, default="merged.csv", help="Output CSV path")
    args = parser.parse_args()

    if not args.bucket and not args.local_dir:
        print("Error: Provide either --bucket or --local-dir")
        sys.exit(1)

    if args.bucket:
        local_dir = Path(tempfile.mkdtemp(prefix="sinter-merge-"))
        sync_from_s3(args.bucket, local_dir)
    else:
        local_dir = Path(args.local_dir)

    csv_files = find_csvs(local_dir)
    if not csv_files:
        print("No CSV files found.")
        sys.exit(1)

    print(f"Found {len(csv_files)} CSV fragments")

    # Try sinter combine first, fall back to simple concatenation
    try:
        merge_with_sinter(csv_files, args.out)
    except FileNotFoundError:
        print("'sinter' command not found, using fallback merge")
        fallback_merge(csv_files, args.out)

    print(f"\nNext steps:")
    print(f"  sinter plot --in {args.out} --group_func \"f'{{m.type}} d={{m.d}}'\" --x_func m.p \\")
    print(f"    --xaxis '[log]Physical Error Rate' --out threshold.png")


if __name__ == "__main__":
    main()
