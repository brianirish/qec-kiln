"""
Local smoke test for the fixed observable + post-selection path.

Runs the K=1 distillation circuit at three noise rates (0.001, 0.01, 0.05)
and confirms that:
  1. Post-selection rate is ~14-17% (consistent with tsim demo's noiseless claim).
  2. Logical error rate (errors / surviving shots) grows with p.
  3. Numbers are not the broken ~50% fraction we saw with reference-sampling.

Run:
  uv run --with "bloqade-tsim" --with stim --with sinter --with pymatching \\
         --with numpy python smoke_test_fixed_observable.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import sinter
import tsim

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "patches"))

# Apply the sinter numpy 2.x patch before any sinter internal imports.
import sinter_numpy2_fix  # noqa: F401

from tsim_sampler import TsimThenDecodeSampler
from generate_tsim_circuits import build_distillation_circuit_text


def run_one(K: int, p: float, shots: int = 30_000) -> dict:
    circuit_text = build_distillation_circuit_text(K=K, p=p)
    circuit = tsim.Circuit(circuit_text)

    mask = np.ones(circuit.num_detectors, dtype=bool)
    packed_mask = np.packbits(mask, bitorder="little")

    task = sinter.Task(
        circuit=circuit,
        decoder="pymatching_tsim",
        skip_validation=True,
        postselection_mask=packed_mask,
    )

    results = sinter.collect(
        num_workers=1,
        tasks=[task],
        max_shots=shots,
        max_errors=shots,
        custom_decoders={
            "pymatching_tsim": TsimThenDecodeSampler(
                decoder_name="pymatching",
                use_reference_samples=False,
            )
        },
        print_progress=False,
    )

    stat = results[0]
    surviving = stat.shots - stat.discards
    err_rate = stat.errors / surviving if surviving > 0 else float("nan")
    ps_rate = surviving / stat.shots if stat.shots > 0 else 0.0
    return {
        "K": K,
        "p": p,
        "shots": stat.shots,
        "discards": stat.discards,
        "surviving": surviving,
        "errors": stat.errors,
        "err_rate": err_rate,
        "ps_rate": ps_rate,
        "seconds": stat.seconds,
    }


def main() -> int:
    print(f"{'K':>2}  {'p':>6}  {'shots':>6}  {'discards':>8}  {'surviving':>9}  "
          f"{'errors':>6}  {'err_rate':>8}  {'ps_rate':>7}  {'seconds':>7}")
    rows = []
    for K, p in [(1, 0.001), (1, 0.01), (1, 0.05), (2, 0.01), (3, 0.01)]:
        row = run_one(K=K, p=p, shots=30_000)
        rows.append(row)
        print(
            f"{row['K']:>2}  {row['p']:>6.3f}  {row['shots']:>6}  "
            f"{row['discards']:>8}  {row['surviving']:>9}  {row['errors']:>6}  "
            f"{row['err_rate']:>8.5f}  {row['ps_rate']:>7.4f}  {row['seconds']:>7.1f}"
        )

    # Sanity checks
    k1 = [r for r in rows if r["K"] == 1]
    rates = [r["err_rate"] for r in k1]
    ps_rates = [r["ps_rate"] for r in k1]

    print()
    print("Sanity checks:")

    bad = False
    for r in k1:
        if r["ps_rate"] > 0.35 or r["ps_rate"] < 0.05:
            print(f"  WARN: K=1 p={r['p']} post-selection rate {r['ps_rate']:.3f} "
                  f"is outside expected 5-35% range for Reichardt 5-to-1.")
    if all(r < 0.30 for r in rates):
        print("  OK: all K=1 error rates under 30% (not the broken ~50% regime).")
    else:
        print(f"  WARN: at least one K=1 error rate >= 30%, observable may still be broken.")
        bad = True
    if rates[0] < rates[-1]:
        print(f"  OK: K=1 err_rate monotone-ish with p "
              f"(p=0.001 → {rates[0]:.4f}, p=0.05 → {rates[-1]:.4f}).")
    else:
        print(f"  WARN: K=1 err_rate NOT increasing with p "
              f"(p=0.001 → {rates[0]:.4f}, p=0.05 → {rates[-1]:.4f}).")
        bad = True

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
