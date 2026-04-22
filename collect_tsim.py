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
    parser.add_argument(
        "--save-resume-filepath", type=Path, default=None,
        help="Path for sinter's incremental progress CSV. If the file exists, "
             "sinter resumes from it. Enables spot-preempt durability when paired "
             "with an out-of-band sync loop.",
    )
    parser.add_argument(
        "--no-reference-samples", action="store_true",
        help="Disable tsim's use_detector_reference_sample / use_observable_reference_sample. "
             "Required for circuits that encode expected syndrome values via ancillas "
             "(non-Clifford workloads with explicit post-selection).",
    )
    parser.add_argument(
        "--postselect-all-detectors", action="store_true",
        help="Set task.postselection_mask to cover every detector. Sinter discards any "
             "shot where any detector fires. Use with ancilla-encoded syndrome circuits.",
    )
    return parser.parse_args()


def load_tasks(circuits_dir: Path, decoder_key: str, postselect_all_detectors: bool):
    """Load .circuit files as sinter Tasks with tsim.Circuit objects.

    tsim is imported lazily here for spawn-safety -- worker processes
    shouldn't pay the JAX import cost at module load time.
    """
    import numpy as np
    import tsim
    import sinter

    circuit_files = sorted(circuits_dir.glob("*.circuit"))
    if not circuit_files:
        print(f"ERROR: No .circuit files found in {circuits_dir}", file=sys.stderr)
        sys.exit(1)

    tasks = []
    for f in circuit_files:
        c = tsim.Circuit(f.read_text())
        task_kwargs = dict(
            circuit=c,
            decoder=decoder_key,
            skip_validation=True,
        )
        if postselect_all_detectors:
            # Bit-packed boolean mask, one bit per detector, all ones.
            n_det = c.num_detectors
            mask = np.ones(n_det, dtype=bool)
            task_kwargs["postselection_mask"] = np.packbits(mask, bitorder="little")
        tasks.append(sinter.Task(**task_kwargs))

    return tasks, circuit_files


def main():
    args = parse_args()

    decoder_key = f"{args.decoder}_tsim"
    num_workers = 1 if args.num_workers == "auto" else int(args.num_workers)

    tasks, circuit_files = load_tasks(
        args.circuits_dir, decoder_key, args.postselect_all_detectors
    )
    print(f"Loaded {len(tasks)} circuit(s) from {args.circuits_dir}")

    # Import here (after load_tasks) to keep top-level imports minimal
    import sinter
    from tsim_sampler import TsimThenDecodeSampler

    sampler = TsimThenDecodeSampler(
        decoder_name=args.decoder,
        use_reference_samples=not args.no_reference_samples,
    )

    print(f"Collecting: max_shots={args.max_shots}, max_errors={args.max_errors}, "
          f"num_workers={num_workers}, decoder={decoder_key}, "
          f"reference_samples={not args.no_reference_samples}, "
          f"postselect_all_detectors={args.postselect_all_detectors}")

    collect_kwargs = dict(
        num_workers=num_workers,
        tasks=tasks,
        max_shots=args.max_shots,
        max_errors=args.max_errors,
        custom_decoders={decoder_key: sampler},
    )
    if args.save_resume_filepath is not None:
        args.save_resume_filepath.parent.mkdir(parents=True, exist_ok=True)
        collect_kwargs["save_resume_filepath"] = str(args.save_resume_filepath)

    results = sinter.collect(**collect_kwargs)

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
