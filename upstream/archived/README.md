# Archived — not filed

These bug drafts were written against bloqade-tsim 0.1.2 but verified
against 0.1.3 on 2026-04-22 before filing. Both were pulled:

- **tsim_clifford_bias.md** — DEPOLARIZE2 bias reproduced exactly on
  0.1.2 (+3.62%, σ=+16 at d=5, r=5, p=0.01). On 0.1.3 the bias collapsed
  to +0.52%, σ=+2.3 — QuEra landed a fix between the two releases. Filing
  the 0.1.2 numbers against current tsim would look alarmist; residual
  0.5% is too small to be useful without a bigger characterization run.

- **tsim_observable_flag_side_effect.md** — Not reproducible. Fixed-seed
  toggling of `use_observable_reference_sample` produces identical detector
  rates; the ~2% swings reported in the draft were intra-config variance
  from `seed=None` (stddev 2.5% on 200k shots). There is a real artefact
  here — seed=None produces ~40× Bernoulli-expected variance — but that's
  a distinct bug and would need its own characterization before filing.

Paper implication: Config B ran on bloqade-tsim 0.1.2; we note this in
the paper's tsim reference. Wall-time and JIT-tax measurements are
unaffected by the logical-rate bias.
