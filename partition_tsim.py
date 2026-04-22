#!/usr/bin/env python3
"""
Partition tsim .circuit files across N batches using LPT bin-packing by
measured per-circuit seconds (from tsim_grid_merged.csv).

Circuits are expected at <circuits-dir>/distillation_K=<K>_p=<p>.circuit
where (K, p) matches a row in the timing CSV.

Writes each batch to <output-dir>/batch_<id>/, one file per circuit.
The batch_id format is configurable via --batch-prefix (default: "mcb_",
matching the plan's Config B layout).

Usage:
    python partition_tsim.py \
        --circuits-dir circuits_tsim/ \
        --timing-csv tsim_grid_merged.csv \
        --num-batches 5 \
        --output-dir /tmp/tsim_batches \
        --batch-prefix mcb_
"""
import argparse
import csv
import heapq
import shutil
import sys
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--circuits-dir", type=Path, required=True)
    p.add_argument("--timing-csv", type=Path, required=True)
    p.add_argument("--num-batches", type=int, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--batch-prefix", default="mcb_",
                   help="Prefix for batch dir names (default: 'mcb_')")
    return p.parse_args()


def load_timings(csv_path: Path) -> dict[tuple[int, float], float]:
    """Return {(K, p): seconds} from the merged tsim grid CSV."""
    timings = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            K = int(row["K"])
            p = float(row["p"])
            seconds = float(row["seconds"])
            timings[(K, p)] = seconds
    return timings


def circuit_key(path: Path) -> tuple[int, float]:
    """Extract (K, p) from distillation_K=<K>_p=<p>.circuit filename."""
    stem = path.stem  # distillation_K=3_p=0.01
    try:
        parts = dict(kv.split("=", 1) for kv in stem.split("_")[1:])
        return int(parts["K"]), float(parts["p"])
    except (KeyError, ValueError) as e:
        print(f"ERROR: cannot parse K/p from {path.name}: {e}", file=sys.stderr)
        sys.exit(1)


def lpt_pack(items: list[tuple[float, Path]], n_batches: int) -> list[list[Path]]:
    """Longest-Processing-Time-first greedy bin packing.

    Items are (weight, payload). Returns n_batches lists of payloads;
    assigns each item (heaviest first) to the currently lightest bin.
    """
    bins: list[tuple[float, int, list[Path]]] = [(0.0, i, []) for i in range(n_batches)]
    heapq.heapify(bins)
    for weight, payload in sorted(items, key=lambda x: -x[0]):
        load, idx, members = heapq.heappop(bins)
        members.append(payload)
        heapq.heappush(bins, (load + weight, idx, members))
    ordered = sorted(bins, key=lambda b: b[1])
    return [b[2] for b in ordered]


def main():
    args = parse_args()

    circuits = sorted(args.circuits_dir.glob("*.circuit"))
    if not circuits:
        print(f"ERROR: no .circuit files in {args.circuits_dir}", file=sys.stderr)
        sys.exit(1)

    timings = load_timings(args.timing_csv)

    items: list[tuple[float, Path]] = []
    missing = []
    for c in circuits:
        key = circuit_key(c)
        if key not in timings:
            missing.append((c.name, key))
            continue
        items.append((timings[key], c))

    if missing:
        print("ERROR: no timing data for these circuits:", file=sys.stderr)
        for name, key in missing:
            print(f"  {name} (K={key[0]}, p={key[1]})", file=sys.stderr)
        sys.exit(1)

    batches = lpt_pack(items, args.num_batches)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Partitioned {len(circuits)} circuits into {args.num_batches} batches:")
    for i, batch in enumerate(batches):
        batch_dir = args.output_dir / f"batch_{args.batch_prefix}{i}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        total_sec = 0.0
        for c in batch:
            shutil.copy2(c, batch_dir / c.name)
            total_sec += timings[circuit_key(c)]
        names = ", ".join(sorted(c.name.replace("distillation_", "").replace(".circuit", "") for c in batch))
        print(f"  batch_{args.batch_prefix}{i}: {len(batch):2d} circuits, {total_sec:7.1f}s total | {names}")

    loads = [sum(timings[circuit_key(c)] for c in batch) for batch in batches]
    print(f"\nLoad balance: min={min(loads):.1f}s max={max(loads):.1f}s "
          f"ratio={max(loads) / min(loads):.2f}x")


if __name__ == "__main__":
    main()
