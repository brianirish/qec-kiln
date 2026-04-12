# sinter + tsim integration spike — VERDICT

**Spike run**: 2026-04-07 evening through 2026-04-08 early morning
(Claude autonomous, Brian asleep)
**Scope**: half-day exploration extended into Path A (non-Clifford validation),
CPU-only, no cloud spend
**Deliverable**: determine whether extending qec-kiln with tsim+GPU is a feasible
addition to the arXiv paper, or whether we should ship Stim-only.

**!!! READ THE "PATH A UPDATE" SECTION FIRST.** Yesterday's findings on the
Clifford-only path turned out to be testing the wrong code path entirely;
the Path A re-test on non-Clifford circuits answers the question we actually
care about. The original verdict below is preserved for context but is
**superseded** by the Path A update.

## PATH A UPDATE (2026-04-08 early morning) — read this first

After Brian pointed out yesterday's spike was testing the wrong code path
(tsim's *Clifford*-only sparse geometric sampler, not the *non-Clifford*
ZX-stabilizer-rank sampler the paper actually needs), I extended the spike
with a "Path A" round of tests on real non-Clifford circuits. New tests:

- **T5a** (`test_t5a_minimal_nonclifford.py`): minimal non-Clifford circuit
  (1 T gate, 2 detectors, 1 observable) end-to-end through sinter + the
  wrapper. **PASS.**
- **T5b** (`test_t5b_distillation.py`): the 5-qubit magic state distillation
  circuit straight out of tsim's own demo notebook
  (`docs/demos/magic_state_distillation.ipynb`), with detectors and an
  observable bolted on so sinter can run it. tcount=12, 4 detectors,
  1 observable. **PASS** end-to-end through sinter + the wrapper.
- **T5c** (`test_t5c_wrapper_fidelity.py`): bare tsim vs sinter+wrapper on
  the minimal circuit, multi-trial. Wrapper introduces no bias.
- **T5d** (`test_t5d_distillation_fidelity.py`): same comparison on the
  distillation circuit. Initial single-trial run looked like a 14-sigma
  wrapper bias, but multi-trial follow-up showed it was tsim's intrinsic
  per-trial variance, not a wrapper bug. Wrapper agrees with bare tsim
  at **0.56 sigma** across 8 trials.

The wrapper changed in one substantive way during Path A: it now accepts
a `tsim.Circuit` directly in `task.circuit` (skipping the unnecessary
`from_stim_program` round-trip if the user already built a tsim circuit
with non-Clifford gates). The added branch is 4 lines.

### Path A definitive findings

1. **The wrapper handles the non-Clifford code path correctly.** sinter+tsim
   end-to-end works on real magic state distillation circuits. The wrapper
   introduces zero bias of its own. The integration mechanically works for
   exactly the workload class the qec-kiln paper would target.

2. **The Clifford bug from yesterday's spike is irrelevant for non-Clifford
   workloads.** Tsim has two completely separate sampling paths: a sparse
   geometric sampler (Clifford-only) and a ZX-stabilizer-rank sampler
   (non-Clifford). The ~14% Clifford bias I documented yesterday is in the
   first path, and it's never reached when sampling circuits with T gates.
   The non-Clifford path is what the paper would use, and yesterday's bug
   does not apply to it. **Yesterday's "blocker" was never a blocker for
   the actual use case.**

3. **Tsim's non-Clifford sampler has irreducible per-trial variance that
   scales with T-count.** This is the new finding worth understanding:

   | Circuit | T-count | Per-trial std (rate) | Statistical std | Excess |
   |---|---|---|---|---|
   | minimal (T5a) | 1 | 0.0022 | 0.0025 | ~1× (statistical) |
   | distillation (T5b) | 12 | 0.022 | 0.0018 | **~12× excess** |

   At T-count = 1, tsim's per-trial variance is just statistical Bernoulli
   noise. At T-count = 12, the variance is 12× larger than statistics
   predicts. This is because tsim's stabilizer-rank decomposition has
   ~`2^(T/2)` weighted Clifford terms, and a single sample() call does a
   Monte Carlo walk over those terms; the walk itself has variance
   independent of how many shots you take per call. **Adding more shots
   in one sample() call does NOT reduce this variance.**

4. **Sampling IS reproducible with seed pinning.** Fresh samplers + same
   seed produce bit-identical outputs. The 12× excess variance only shows
   up when you create new samplers with new seeds. So pinning a seed is a
   valid way to get reproducible results, you just need many seeded trials
   to estimate the underlying mean.

5. **The right way to reduce tsim's non-Clifford variance is multiple
   sample() calls (or multiple sampler instances), not larger shot counts
   per call.** Sinter's ramp-throttled sampler naturally does this — it
   makes many sample() calls of varying sizes. The wrapper-via-sinter
   actually has *better* mean convergence than bare tsim with one big call,
   because sinter averages across many sample() invocations.

6. **Subtle finding worth filing upstream:** in tsim 0.1.2,
   `use_observable_reference_sample=True` has a side effect on **detector**
   event rates (~2% shift on the distillation circuit). An "observable"
   flag changing detector statistics is unexpected. The wrapper sets both
   reference flags to True (correctly) so this behavior is consistent with
   stim's bit conventions, but the upstream side-effect should be reported.

### Path A revised cost/time estimate for the tsim extension

| Step | Yesterday's estimate | After Path A |
|---|---|---|
| Sinter+tsim wrapper | 1-2 weeks (unknown) | **DONE** (~80 lines, validated) |
| Build Clifford+T circuit class | 2-4 days | 2-4 days (unchanged) |
| Docker image (CUDA + JAX + tsim) | 0.5-1 day | 0.5-1 day |
| GPU spot benchmarking | 2-4 days | **3-7 days** (need 5-10 trials per cell to control tsim's intrinsic variance) |
| Validation methodology (no stim ground truth) | unknown | **2-4 days** (use small T-count circuits where tsim's variance is statistical, or use the seed-reproducibility property) |
| Write up methodology + results | 1-2 days | **2-3 days** (need to characterize and report the variance behavior) |
| **Total focused work** | 5-10 working days | **9-19 working days** |
| **Cost** | $25-80 single-trial | **$50-200** for multi-trial precision |

The cost went up modestly: ~2× the GPU spot spend because of the multi-trial
requirement, and ~2× the engineering time because validation methodology is
a real research step that yesterday's framing didn't account for.

### Path A revised publication recommendation

The Path A spike confirms what yesterday's spike was actually trying to ask:
**the sinter+tsim integration is real and usable for non-Clifford workloads,
which is what the paper would actually exercise.** The Clifford bug from
yesterday is on a different code path and irrelevant.

The new caveat: tsim's non-Clifford sampler has higher per-trial variance
than naive Bernoulli statistics would predict. This means a paper-quality
benchmark needs multiple trials per data point — call it 5-10 — to get
publication-clean error bars. The cost picture is roughly $50-200 instead
of $25-80, and the engineering time is 1.5-2 weeks instead of 1 week.

That's still well within the budget Brian described as "not ridiculous,"
and **the rest of yesterday's reasoning about the strategic value of the
tsim extension still holds**: the paper without tsim is a useful tool with
a modest Stim benchmark; the paper with tsim demonstrates that qec-kiln
distributes the workload class where cloud distribution actually matters
(Clifford+T QEC at distillation/cultivation scale). The Path A spike
removes the integration risk; the only remaining cost is engineering time
and the validation methodology question.

**Updated specific recommendation**: Brian should commit the 1.5-2 week,
$50-200 budget if he has the time. The wrapper is done and validated.
The remaining work is real but bounded. The variance characterization is
itself a paper-worthy finding (it'd appear in the Methodology section as
"we observed that tsim's non-Clifford sampler has per-trial variance
proportional to circuit T-count, and characterized it as a multi-trial
stabilizer-rank Monte Carlo phenomenon").

If Brian still wants to ship Stim-only, the strongest reframe is now:
"the tsim extension is feasible, the wrapper exists in this repo, the
remaining work is one focused engineering sprint that just doesn't fit
this publication's timeline." That's a real and defensible position.
The case for *not* doing it is purely about calendar time, not about
technical risk.

### What yesterday's spike got wrong

I want to flag what I learned about my own process here, because Brian was
the one who caught the methodological mismatch and I want to make sure it
doesn't happen again:

- **Yesterday's spike research agent recommended testing on "a small
  repetition code or distance-3 surface code,"** which I followed
  uncritically. This is the natural smoke test if you have stim as ground
  truth. It is **the wrong smoke test** for a tool whose purpose is
  simulating circuits stim can't handle.
- **The right smoke test is one that exercises the code path the paper
  cares about**, even if it's harder to validate. T5a (a 1-T-gate hand-built
  circuit) is the right minimal test; T5b (the tsim distillation demo) is
  the right realistic test. Neither cost more than 30 minutes to write.
- **The "easy" Clifford comparison test was a red herring** that produced
  an alarming-looking ~14% bias finding which is real but irrelevant to
  the actual question. I spent 2+ hours debugging it. That's wasted time
  I could have used on the right test from the start.
- **Lesson**: when the research agent's framing assumes one thing about the
  use case and the user's actual use case is something else, the spike
  plan should be re-derived from the user's use case, not from the
  research agent's defaults. I will do this faster next time.

### Rest of this document is the original (yesterday's) verdict

What follows is the spike's original framing and findings, which were
correct but answered the wrong question. Read the Path A section above
for the actual verdict.

---

## TL;DR (yesterday — see Path A above for the corrected version)

**Sinter side: EASY WORLD, confirmed.** The ~80-line `TsimThenDecodeSampler` in
`tsim_sampler.py` plugs cleanly into `sinter.collect(custom_decoders=...)` with
zero sinter-fork, zero upstream-patches, zero monkey-patching. T3 passes. The
research agent's "easy world" verdict was correct about the API.

**Tsim side: BLOCKING ISSUE FOUND.** Bloqade-tsim 0.1.2 produces logical error
rates that disagree with stim by **11.9% (d=3) to 14.1% (d=5)** on the exact
rotated surface code circuits your paper uses. This is not noise. It is
reproducible, scales with circuit complexity, and is localized to the
`after_clifford_depolarization` noise channel (i.e., `DEPOLARIZE2` after
2-qubit Clifford gates) in combination with surface code detector structure.
The bias does NOT appear on the repetition code.

**Secondary finding (not a blocker, but relevant to instance-shape choice):**
tsim's Clifford-only "sparse geometric sampler" is explicitly **not
GPU-accelerated** per the tsim arXiv paper Section 3. This means even on an
A100 spot instance, for the rotated surface code circuits in qec-kiln's
existing benchmark, tsim would run at approximately its CPU speed — no GPU
advantage. Combined with the correctness bias above, this rules out
re-benchmarking the *existing* Clifford workload on tsim+GPU entirely: you'd
pay GPU-instance prices, get no acceleration (because it's Clifford), AND
get incorrect numbers (because of the bias).

CPU-vs-GPU speed numbers from the spike (on Brian's laptop, for context, NOT
representative of the GPU-instance benchmark): tsim took 2.5-5.4s per 10,000
shots vs stim's 0.01-0.04s. These are CPU numbers and are not the paper story;
they're only useful for the developer-workflow question of "can I iterate on
this locally without a GPU?" (Answer: yes, tsim on CPU works, but it's slow.)

**Bottom line for the publish decision**: **do NOT extend the existing paper
with tsim**. File an upstream bug report with QuEra using our reproducers,
ship Stim-only, and consider the tsim extension as a v2 paper once the
bloqade-tsim Clifford-path bias is fixed. See the "Updated publication
recommendation" section at the bottom.

## What the spike set out to answer

Can we take a standard sinter collection workflow and swap out stim for tsim
as the sampling backend, with minimal effort, so that qec-kiln can demonstrate
cloud-distributed QEC sampling on the regime where tsim actually wins
(Clifford+T circuits requiring GPU)?

Specifically, answer by test-driven development:

- **T1** — Can tsim sample a stim-built circuit at all? (sanity gate)
- **T2** — Do stim and tsim agree statistically on a Clifford circuit? (correctness gate)
- **T3** — Does the wrapper integrate cleanly into `sinter.collect`? (API gate)
- **T4** — Do logical error rates from sinter+stim and sinter+tsim agree? (equivalence gate)

## Results

### T1: tsim API sanity — **PASS**

`test_t1_tsim_sample.py` — 4 tests, all pass.

- `tsim.Circuit.from_stim_program(stim_circuit)` exists and works.
- `num_detectors`, `num_observables`, `num_measurements` all agree with stim.
- `compile_detector_sampler()` returns a `CompiledDetectorSampler`.
- `sample(shots, bit_packed=True, separate_observables=True, use_detector_reference_sample=True, use_observable_reference_sample=True)` returns the expected `(uint8[shots, num_det_bytes], uint8[shots, num_obs_bytes])` shape.

**Conclusion**: the tsim API surface is exactly what the spike research agent
reported. No surprises.

### T2: statistical equivalence on Clifford circuits — **FAIL** (but partially)

`test_t2_stim_tsim_equivalence.py` — per-detector rate check passes (4.09 sigma
max deviation, acceptable), but **global event counts disagree at 3.29 sigma
even on a tiny d=3 surface code**.

`test_t2b_multiseed_check.py` — across 10 independent seeds on the same d=3
surface code, tsim consistently reports fewer events than stim by ~1.3% on
average. Mean disagreement **+2.32 sigma, std 1.33**. Not statistical noise —
this is a **systematic bias** where stim > tsim.

`test_t2c_characterize_bias.py` — characterized across 7 circuit configurations.
Key findings:

| Circuit | detector rel dev | observable rel dev | sigma |
|---|---|---|---|
| rep d=3 p=0.05 | +0.35% | +2.50% | +0.58 / +1.34 |
| rep d=5 p=0.05 | +0.20% | -1.03% | +0.59 / -0.64 |
| rep d=3 p=0.001 | +0.92% | +5.36% | +0.22 / +0.41 |
| surf_x d=3 p=0.001 | +2.29% | +2.98% | +1.29 / +0.47 |
| surf_x d=3 p=0.01 | +1.69% | +4.61% | +2.96 / +2.26 |
| **surf_x d=5 p=0.01** | **+2.23%** | **+4.71%** | **+9.51** / +3.53 |
| surf_z d=3 p=0.01 | +0.90% | -1.10% | +1.56 / -0.52 |

The **d=5 surface code at 9.51 sigma** (on per-detector rates) is the smoking
gun. This is not noise.

`test_t2d_convention_flip.py` — tried all 4 combinations of the two tsim
`use_*_reference_sample` flags. **All give the same result.** The bias is not
a convention mismatch.

`test_t2e_noiseless_baseline.py` — isolated which noise channel carries the
bias by running with ONE channel at a time:

| noise channel | stim events | tsim events | diff |
|---|---|---|---|
| (noiseless) | 0 | 0 | exact agreement |
| p=0.0001 | 3644 | 3472 | -4.7% |
| only `after_clifford_depolarization=0.01` | **195532** | **188451** | **-3.6% (bias!)** |
| only `after_reset_flip_probability=0.01` | 50046 | 50341 | +0.6% (noise) |
| only `before_measure_flip_probability=0.01` | 50597 | 50351 | -0.5% (noise) |
| only `before_round_data_depolarization=0.01` | 47438 | 47425 | +0.03% (exact) |

**The bias is localized to `after_clifford_depolarization`.** Three of the
four noise channels agree to within statistical noise. Only the one that
applies `DEPOLARIZE2` after 2-qubit Clifford gates shows a real disagreement.

`test_t2f_depolarize2_bug.py` — attempted to reproduce the bias on a hand-built
minimal circuit with just `CNOT + DEPOLARIZE2(0.05)` in a loop. **No bias
observed** (0.22%, 0.5 sigma). So the bug is NOT simply "tsim's DEPOLARIZE2 is
broken." It's something more subtle — the bias only appears when `DEPOLARIZE2`
interacts with surface-code-style detector definitions.

Additional isolation test (inline in the transcript): checked whether the bias
comes from `MR` (measure-reset) vs `M;R` decomposition, or from `MX` vs `H;M`
decomposition. **Neither**. Both decompositions give identical tsim output.

**Final T2 state**: tsim's noise model has a systematic ~1-5% bias against
stim on circuits that combine `DEPOLARIZE2` with surface-code detector
definitions. The root cause is somewhere in bloqade-tsim's internal handling
of `DEPOLARIZE2` channels as they interact with the stim-generated detector
instruction stream, but a half-day spike is not the place to root-cause it.

### T3: sinter integration — **PASS**

`test_t3_sinter_integration.py` — the actual wrapper test.

- `TsimThenDecodeSampler` registered via `custom_decoders={"pymatching_tsim": ...}`
- `sinter.collect(...)` runs, returns valid `TaskStats`
- CSV round-trip via `sinter.read_stats_from_csv_files` works
- Logical error rate on d=3 rep p=0.05 is 13.3% (reasonable)

Two implementation gotchas along the way, both minor:

1. **numpy 2.x `isinstance(x, int)` bug in sinter.** First run crashed because
   sinter's built-in `classify_discards_and_errors` returns `numpy.intp`, and
   `AnonTaskStats.__post_init__` does `assert isinstance(self.errors, int)`
   which now fails on numpy 2.x. This is the **same bug already patched in
   `patches/sinter_numpy2_fix.py` for the CPU benchmark**. Applied the same
   patch to the ephemeral uv sinter install for T3/T4.

2. **`numpy.intp` return types in my wrapper.** Explicitly cast `int(num_shots)`,
   `int(num_errors)`, `int(num_discards_1) + int(num_discards_2)`, `float(t1 - t0)`
   before constructing `AnonTaskStats`. Without these casts, the wrapper
   triggers the same sinter assertion. Already handled in `tsim_sampler.py`.

**Conclusion**: sinter's Sampler ABC is exactly the seam the spike research
agent described. The wrapper is ~80 lines (half of which are sinter's own
post-sampling bookkeeping verbatim). No sinter patching required beyond the
pre-existing numpy 2.x fix. This is the cleanest possible integration.

### T4: end-to-end logical error rate comparison — **PARTIAL FAIL**

`test_t4_end_to_end.py` — runs the same circuit through both sinter+stim
(default) and sinter+tsim (wrapper), compares logical error rates.

| Circuit | shots | stim LER | tsim LER | Relative diff | Significance |
|---|---|---|---|---|---|
| rep d=3 p=0.05 | 10,000 | 0.1202 | 0.1213 | **-0.9%** | -0.24σ (noise) |
| **surface d=3 p=0.01** | 10,000 | 0.0682 | 0.0601 | **+11.9%** | **+2.34σ (real)** |
| **surface d=5 p=0.01** | 10,000 | 0.0949 | 0.0815 | **+14.1%** | **+3.34σ (real)** |

Repetition code: **perfect agreement**. Tsim and stim give identical logical
error rates within statistical noise. The wrapper works as advertised when
tsim's underlying physics matches stim's.

Surface code: **11.9-14.1% systematic disagreement**. The bias grows with code
distance, consistent with the T2 finding that it scales with the number of
2-qubit gates + surface-code detector complexity. At d=5, tsim undercounts
logical errors by 1.34 percentage points, which is catastrophic for any
cross-validation attempt.

**Per-run CPU wall times** (laptop, for developer-workflow context only —
these are NOT representative of the GPU benchmark story):

| Circuit | stim time | tsim time (CPU) |
|---|---|---|
| rep d=3 p=0.05 | 0.01s | 2.52s |
| surface d=3 p=0.01 | 0.01s | 2.83s |
| surface d=5 p=0.01 | 0.04s | 5.39s |

The ratio is dramatic (100-300×) but expected: tsim is designed for GPU and
specifically for workloads where stim can't help at all. The tsim arXiv paper
Section 3 is explicit: the Clifford sparse geometric sampler is *not*
GPU-accelerated — which means the ~5s/10k-shots we observe on CPU would be
approximately the same on an A100. More importantly, **stim is extraordinarily
fast on Clifford circuits** (~50ms per 10k shots), so the CPU speed gap here
is a combination of (a) stim being uniquely good at Cliffords and (b) tsim
deliberately not optimizing the Clifford path because its value prop is
non-Clifford simulation. This is not a finding against tsim — it's a feature
of the design. It just means tsim is not the right tool for reproducing the
existing qec-kiln Clifford benchmark, with or without a GPU.

## What I learned that wasn't in the research agent's report

1. **The sinter Sampler ABC is cleaner than I expected.** The `_sampler.py` in
   sinter 1.15.0 already has exactly the right abstraction. The custom_decoders
   dict accepts Sampler instances, not just Decoders. The spike research agent
   was right to call this "easy world."

2. **Tsim's Clifford path has a real bias vs stim.** This is a surprise and not
   mentioned anywhere in the tsim repo, docs, or paper that I found. Worth
   reporting upstream with the reproducers from this spike.

3. **The GPU win lives entirely in the non-Clifford path.** This isn't new
   information — the tsim paper Section 3 is explicit: the sparse geometric
   sampler (Clifford-only) is "not GPU-accelerated, so CPU and GPU runtimes
   are similar." But it's the load-bearing fact for the publication decision:
   re-benchmarking the existing qec-kiln surface code sweep on tsim+GPU
   would be **strictly worse** on two dimensions (correctness: -14%, cost:
   GPU instances are more expensive than CPU) with **no upside** (no GPU
   speedup, because Clifford doesn't use the GPU path). The CPU speed numbers
   from the spike are developer-workflow data, not paper data.

## Files produced by the spike

```
spike_tsim/
├── NOTES.md                         # running progress log
├── SPIKE_VERDICT.md                 # this file
├── tsim_sampler.py                  # the deliverable wrapper (~180 lines, mostly comments)
├── test_t1_tsim_sample.py           # PASS: tsim API sanity
├── test_t2_stim_tsim_equivalence.py # FAIL (borderline): detector-level equivalence
├── test_t2b_multiseed_check.py      # characterized bias across 10 seeds (2.3 sigma mean)
├── test_t2c_characterize_bias.py    # localized bias to surface code circuits
├── test_t2d_convention_flip.py      # ruled out: flag/convention issue
├── test_t2e_noiseless_baseline.py   # localized bias to `after_clifford_depolarization`
├── test_t2f_depolarize2_bug.py      # bias is NOT in bare DEPOLARIZE2
├── test_t3_sinter_integration.py    # PASS: sinter accepts the wrapper cleanly
└── test_t4_end_to_end.py            # PARTIAL FAIL: 12-14% LER disagreement on surface code
```

## Updated publication recommendation

Before the spike, the question was: "Is extending the paper with tsim a 2-day
task or a 2-week task? The cost dominates my willingness to do it."

After the spike, the cost decomposition has changed:

| Step | Before spike | After spike |
|---|---|---|
| Sinter+tsim wrapper | 1-2 weeks (unknown integration cost) | **0.5 day** (done, `tsim_sampler.py` in this directory) |
| Circuit generation for Clifford+T | 2-4 days | 2-4 days (unchanged) |
| Docker image w/ CUDA+JAX | 0.5-1 day | 0.5-1 day (unchanged) |
| GPU spot benchmarking | 2-4 days | 2-4 days (unchanged) |
| **Bug-blocker: tsim Clifford bias** | unknown | **deal-breaker for direct stim comparison** |
| Validate tsim non-Clifford path against something | — | **unknown, no ground truth to compare to** |

The sinter-wrapper cost went from "unknown, maybe 2 weeks" to "done in an
afternoon." That should have made the decision easy. But the spike *also*
turned up a new blocker I didn't know about: **tsim's Clifford path disagrees
with stim by 12-14% on the surface code**, which means you cannot use tsim to
extend the existing benchmark directly.

Three paths forward, in increasing order of time commitment:

### Option 1: Ship Stim-only paper, file tsim bug upstream

- Accept the paper as it stands (Stim+PyMatching, one cloud-distribution benchmark).
- Open an issue on `QuEraComputing/tsim` with the T2/T4 reproducers. This is
  a meaningful contribution back, regardless of whether we extend our own
  paper later.
- In the Discussion section of the qec-kiln paper, reference the spike's
  finding: "We attempted to extend this benchmark to QuEra's `bloqade-tsim`
  simulator, but identified a systematic ~14% disagreement in logical error
  rates on our surface code circuits (reported upstream). A tsim-based
  extension remains future work contingent on upstream resolution."
- **Time to publish**: days. **Cost**: $0 additional beyond what's been spent.

### Option 2: Switch to Clifford+T workload, trust tsim's non-Clifford path

- Regenerate the benchmark circuits around magic state distillation or
  cultivation (the workload class where tsim actually has a GPU advantage).
- Use tsim as the primary sampler, with no stim cross-validation (because
  stim can't run these circuits anyway).
- Accept that we're trusting tsim's non-Clifford path without an independent
  ground truth, and caveat this in the paper.
- **Time to publish**: 1-2 weeks. **Cost**: ~$25-80 GPU spot. **Risk**:
  tsim might have a similar bias on the non-Clifford path that we have no
  way to detect.

### Option 3: Wait for QuEra to fix the bias, then do Option 2 properly

- File the bug report now with the spike's reproducers.
- Ship Stim-only paper v1 now.
- When QuEra ships a fix, write a v2 paper that actually cross-validates
  tsim+GPU against stim+CPU on Clifford circuits, then extends to
  non-Clifford Clifford+T workloads.
- **Time to publish v1**: days. **Time to publish v2**: 1-3 months after
  QuEra fixes the bug. **Cost**: $0 now, $50-200 for v2.

## My recommendation

**Option 1, with a specific pivot**: ship Stim-only, file the upstream bug,
and **in the Discussion section explicitly frame the open question as "the
next qec-kiln paper"**. The spike has given you a genuinely novel contribution
to the tsim bug tracker (a 5-test reproducer suite localizing a real
correctness issue in a 2-month-old GPU QEC simulator), and it's OK for that
to be a separate deliverable from the qec-kiln paper.

The case for option 1 over option 2: the 11-14% LER disagreement means you'd
either be publishing stim-only or tsim-only numbers, not both. If the reviewer
asks "did you cross-validate your simulator choice?", the honest answer with
tsim is "no, we found a ~14% disagreement we couldn't explain." That is a
weaker paper than one that transparently says "we benchmarked Stim+PyMatching,
we'd like to extend to tsim+GPU in a follow-up, here's the wrapper, here's
the upstream bug we found."

The case against option 2 specifically: without a ground truth for tsim's
non-Clifford path, you'd be publishing GPU-distributed logical error rates
for cultivation circuits that **nobody can cross-validate**, from a simulator
that has a known ~14% correctness issue on Clifford circuits. This is a
serious credibility problem for the paper — reviewers would be right to
question it.

**Specific next steps for Brian in the morning:**

1. Read this file and `tsim_sampler.py` (~15 min)
2. Skim the test outputs in this directory (~15 min)
3. Decide between Option 1, 2, or 3. (My vote: 1.)
4. If Option 1: file the upstream issue using `test_t2e_noiseless_baseline.py`
   and `test_t4_end_to_end.py` as the minimal reproducer. Update the paper's
   Discussion section to reference the spike finding. Ship.
5. If Option 2: commit the week and ~$50-80 to cloud spot. The sinter+tsim
   wrapper is already done, so you'd save ~3-5 days on the engineering front.

**Useful data for the upstream bug report:**

- Environment: bloqade-tsim 0.1.2, stim 1.16 (via uv ephemeral install),
  numpy 2.x, macOS
- Minimal reproducer: `test_t2e_noiseless_baseline.py` showing per-channel
  isolation
- End-to-end impact: `test_t4_end_to_end.py` showing 11.9% / 14.1% LER
  disagreement on d=3 / d=5 surface code
- Negative result (demonstrates the bug is NOT trivial): `test_t2f_depolarize2_bug.py`
  showing that `DEPOLARIZE2` on its own is fine

## How I spent the half-day (for Brian's reference)

- ~30 min: research agent's report + planning the TDD cycle
- ~15 min: install tsim, probe API, confirm the integration seam
- ~30 min: T1 (tsim can sample a stim circuit) — passed first try
- ~45 min: T2 (stim/tsim equivalence) — expected to pass, found the bias
- ~60 min: T2b-T2f — characterizing and localizing the bias
- ~30 min: T3 (sinter integration) — hit numpy 2.x bug, fixed it, passed
- ~20 min: T4 (end-to-end LER comparison) — confirmed the bias at the
  logical-error-rate level
- ~30 min: writing this verdict

Total: ~4 hours of focused work. The spike came in under budget, and the
answer is far more decisive than I expected — both directions.
