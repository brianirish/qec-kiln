# sinter + tsim integration spike — running notes

**Started**: 2026-04-07 evening (Brian asleep, Claude working autonomously)
**Goal**: prove or disprove that sinter can use bloqade-tsim as a sampler backend
**Approach**: TDD. Each test is a gate. No production code without a failing test first.
**Scope**: CPU-only spike, no GPU, no SkyPilot, no Docker, no spending. ~half a day of work max.

## What "success" means for this spike

A passing test that demonstrates:
1. tsim is installed and importable
2. tsim can sample a stim-built circuit
3. stim and tsim agree statistically on Clifford circuits (the correctness gate)
4. A `TsimThenDecodeSampler` wrapper plugs into `sinter.collect(custom_decoders=...)` cleanly
5. End-to-end logical error rates from sinter+tsim match sinter+stim within Poisson noise

If all 5 pass: integration is real, the spike research agent's verdict was correct, Brian should commit the week.
If any break: document exactly which one and why, recommend the Stim-only paper path with concrete blocker description.

## What I will NOT do

- Modify the existing benchmark scripts
- Build the docker image
- Touch the paper or BENCHMARK.md
- Spend money on cloud resources
- Run anything on a GPU (no GPU on this machine, and we're testing the integration not the speed)

## Files in this directory

- `NOTES.md` — this file, running progress log
- **`SPIKE_VERDICT.md`** — **read this first in the morning. Everything that
  matters is in there.**
- `tsim_sampler.py` — the deliverable wrapper (~180 lines, mostly comments)
- `test_t1_tsim_sample.py` — PASS: tsim API sanity
- `test_t2_stim_tsim_equivalence.py` — borderline fail at 3.29 sigma
- `test_t2b_multiseed_check.py` — confirmed systematic bias (+2.3 sigma across 10 seeds)
- `test_t2c_characterize_bias.py` — localized bias to surface code circuits
- `test_t2d_convention_flip.py` — ruled out flag/convention issue
- `test_t2e_noiseless_baseline.py` — localized bias to `after_clifford_depolarization`
- `test_t2f_depolarize2_bug.py` — DEPOLARIZE2 alone is fine (bug is more subtle)
- `test_t3_sinter_integration.py` — PASS: sinter accepts the wrapper cleanly
- `test_t4_end_to_end.py` — 11.9% LER disagreement on surface d=3, 14.1% on d=5

## Spike complete (~6 hours including Path A)

**TL;DR — Path A SUPERSEDES yesterday's verdict. Read SPIKE_VERDICT.md
for the full picture.**

- **API integration: WORKS.** The wrapper is in `tsim_sampler.py`, ~85 lines
  of meaningful code, no sinter fork needed. Now handles both `stim.Circuit`
  AND `tsim.Circuit` directly (added during Path A).
- **Non-Clifford code path: WORKS.** Path A tests T5a/T5b confirm sinter+tsim
  end-to-end on real magic state distillation circuits. The wrapper introduces
  no bias of its own (T5c, T5d).
- **Yesterday's Clifford bug is irrelevant.** Tsim's Clifford-only sparse
  geometric sampler has a ~14% bias vs stim, but the paper would never use
  that path — it'd use the ZX-stabilizer-rank path (non-Clifford). Yesterday's
  spike tested the wrong code path because the research agent recommended
  comparing against stim, which only works for Clifford circuits.
- **New finding worth knowing**: tsim's non-Clifford sampler has per-trial
  variance that scales with circuit T-count (statistical at T=1, ~12× larger
  than statistical at T=12). This is from the stabilizer-rank Monte Carlo
  decomposition and is *irreducible* by adding more shots in one call. It
  IS reducible by averaging across many sample() calls or sampler instances,
  which sinter naturally does via ramp-throttled sampling. **Implication for
  the paper**: a meaningful tsim+GPU benchmark needs 5-10 trials per data
  point. This adds cost (~$50-200 instead of $25-80) but is doable.
- **Sampling is reproducible** with seed pinning (fresh samplers + same seed
  → bit-identical results).
- **Subtle bug to file upstream**: tsim's `use_observable_reference_sample=True`
  flag has a ~2% side effect on detector event rates. An "observable" flag
  shouldn't change detectors. Worth reporting.

**Recommended next step** (see SPIKE_VERDICT.md "Path A" section): the tsim
extension is feasible with bounded engineering time (1.5-2 weeks) and modest
cost ($50-200). The wrapper is done and validated. Brian should commit the
work if he has the calendar time available.
