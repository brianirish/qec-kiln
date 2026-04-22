# Bug report draft: Clifford sparse geometric sampler disagrees with stim on `DEPOLARIZE2` in rotated surface codes

**Target repo:** https://github.com/QuEraComputing/tsim

## Links

- Reproducers: `spike_tsim/test_t2c_characterize_bias.py`, `spike_tsim/test_t2e_noiseless_baseline.py`, `spike_tsim/test_t2f_depolarize2_bug.py`, `spike_tsim/test_t4_end_to_end.py` in https://github.com/brianirish/qec-kiln (if published; otherwise the reproducers are checked into the `spike_tsim/` directory of the qec-kiln working tree).
- Finding discovered during the qec-kiln tsim integration spike (Brian Irish, solo researcher).

---

## Title (for the issue)

Clifford sparse geometric sampler: systematic detector/observable rate bias vs stim on `DEPOLARIZE2` in rotated surface code circuits

## Summary

On rotated surface code memory experiments compiled with `stim.Circuit.generated(... after_clifford_depolarization=p ...)` and then converted via `tsim.Circuit.from_stim_program`, tsim's Clifford sparse geometric sampler produces per-detector rates ~2.2% lower than stim's (9.5σ at d=5 / r=5 / p=0.01 / 20k shots) and logical-error-rate estimates 11.9–14.1% lower than stim's (at 10k shots through sinter+pymatching).

The bias is isolated to the interaction of `DEPOLARIZE2` (two-qubit depolarizing noise, as emitted by `after_clifford_depolarization`) with surface-code-style detector annotations. Other noise channels agree with stim to within statistical noise, and `DEPOLARIZE2` on a hand-built detectorless circuit also agrees with stim.

Non-Clifford workloads that go through tsim's ZX-stabilizer-rank sampler are a different code path and are **not** affected by this bug; only the Clifford sparse geometric sampler is affected.

## Minimal reproducer

Self-contained, depends only on `tsim`, `stim`, and `numpy`:

```python
import numpy as np
import stim
import tsim

circuit = stim.Circuit.generated(
    "surface_code:rotated_memory_x",
    distance=5, rounds=5,
    after_clifford_depolarization=0.01,
    after_reset_flip_probability=0.0,
    before_measure_flip_probability=0.0,
    before_round_data_depolarization=0.0,
)

shots = 20_000
seed = 42

stim_dets, stim_obs = circuit.compile_detector_sampler(seed=seed).sample(
    shots=shots, separate_observables=True,
)

tsim_circuit = tsim.Circuit.from_stim_program(circuit)
tsim_dets, tsim_obs = tsim_circuit.compile_detector_sampler(seed=seed).sample(
    shots=shots,
    separate_observables=True,
    use_detector_reference_sample=True,
    use_observable_reference_sample=True,
)

stim_det_total = int(stim_dets.sum())
tsim_det_total = int(tsim_dets.sum())
print(f"stim detector events: {stim_det_total}")
print(f"tsim detector events: {tsim_det_total}")
print(f"relative deviation (stim - tsim)/stim: "
      f"{(stim_det_total - tsim_det_total) / stim_det_total:+.2%}")
```

## Observed

At d=5, rounds=5, `after_clifford_depolarization=0.01`, other channels off, 20k shots, seed=42:

```
stim detector events: ~195,500
tsim detector events: ~188,500
relative deviation (stim - tsim) / stim: +3.6%
```

With all four noise channels at p=0.01 (20k shots, seed=42, from `test_t2c_characterize_bias.py`):

| circuit                | det rel dev (stim − tsim)/stim | det sigma | obs rel dev | obs sigma |
|------------------------|-------------------------------:|----------:|------------:|----------:|
| rep d=3 p=0.05         | +0.35% | +0.58 | +2.50% | +1.34 |
| rep d=5 p=0.05         | +0.20% | +0.59 | −1.03% | −0.64 |
| rep d=3 p=0.001        | +0.92% | +0.22 | +5.36% | +0.41 |
| surf_x d=3 p=0.001     | +2.29% | +1.29 | +2.98% | +0.47 |
| surf_x d=3 p=0.01      | +1.69% | +2.96 | +4.61% | +2.26 |
| **surf_x d=5 p=0.01**  | **+2.23%** | **+9.51** | **+4.71%** | **+3.53** |
| surf_z d=3 p=0.01      | +0.90% | +1.56 | −1.10% | −0.52 |

The d=5 p=0.01 surface-code row is the clearest signal (+9.5σ per-detector bias).

End-to-end through sinter+pymatching at 10k shots (`test_t4_end_to_end.py`):

| circuit                        | stim LER | tsim LER | relative diff | significance |
|--------------------------------|---------:|---------:|--------------:|-------------:|
| repetition_code d=3 p=0.05     | 0.1202   | 0.1213   | −0.9%         | −0.24σ (noise) |
| surface_code d=3 p=0.01        | 0.0682   | 0.0601   | +11.9%        | +2.34σ       |
| surface_code d=5 p=0.01        | 0.0949   | 0.0815   | +14.1%        | +3.34σ       |

The repetition code agrees; the rotated surface codes do not.

## Expected

Per-detector and per-observable rates should agree between tsim and stim on circuits that only use Clifford gates and stim's standard noise channels, to within statistical noise. (They do for `after_reset_flip_probability`, `before_measure_flip_probability`, `before_round_data_depolarization`, and for a hand-built `CNOT` + `DEPOLARIZE2(p)` loop without surface-code detectors.)

## Localization

From `test_t2e_noiseless_baseline.py` (single-channel isolation, d=5 / r=5 rotated surface code, 20k shots, seed=42):

| isolated noise channel            | stim events | tsim events | relative |
|-----------------------------------|------------:|------------:|---------:|
| (noiseless)                       | 0           | 0           | exact    |
| all four at p=0.0001              | 3,644       | 3,472       | −4.7%    |
| only `after_clifford_depolarization=0.01` | 195,532 | 188,451 | **−3.6%** |
| only `after_reset_flip_probability=0.01`  | 50,046  | 50,341  | +0.6% (noise) |
| only `before_measure_flip_probability=0.01` | 50,597 | 50,351 | −0.5% (noise) |
| only `before_round_data_depolarization=0.01` | 47,438 | 47,425 | +0.03% |

Only `after_clifford_depolarization` shows a real disagreement.

From `test_t2f_depolarize2_bug.py`: a hand-built minimal circuit of `R 0 1; (CNOT 0 1; DEPOLARIZE2(0.05) 0 1) × 100; M 0 1` with two bare detectors reproduces **no** bias (0.22% relative, 0.5σ at 50k shots). So the bug is not "`DEPOLARIZE2` is broken"; it only appears when `DEPOLARIZE2` is emitted by the `after_clifford_depolarization` hook of a surface-code circuit with its detector structure in place.

Additional negative results from the spike:

- `test_t2d_convention_flip.py` — toggling `use_detector_reference_sample` and `use_observable_reference_sample` (all four combinations) does not change the bias.
- Rewriting the circuit's `MR` as `M; R`, or `MX` as `H; M`, leaves the bias unchanged.

This is a hypothesis, not a verified root cause: the bug most likely lives in how the Clifford sparse geometric sampler handles `DEPOLARIZE2` events whose Pauli frame must propagate through subsequent `MR`/`MX` measurements that feed surface-code detector annotations. A maintainer who knows the sampler internals will confirm or refute this quickly.

## Impact

- Users running Clifford-only QEC benchmarks via tsim's sparse sampler on rotated surface codes will under-report logical error rates by ~12–14% relative (d=3 and d=5 at p=0.01 respectively).
- Non-Clifford workloads that exercise tsim's ZX-stabilizer-rank sampler (magic-state distillation, cultivation) are on a **different code path** and are not affected. Users who rely on tsim specifically for non-Clifford simulation are not impacted by this bug.
- Cross-validation of Clifford-path tsim results against stim on rotated surface codes is currently not possible at the quantitative level.

## Environment

```
tsim==0.1.2
stim==1.15.0
numpy==2.x
python==3.12
platform=darwin (CPU; no GPU required)
```

CPU-only reproducer. The bug does not require the JAX GPU backend — it reproduces on the default CPU path.

## Ready for submission

**Proposed title:**

> Clifford sparse geometric sampler: ~2% per-detector and ~12–14% logical-error-rate bias vs stim on `DEPOLARIZE2` in rotated surface codes

**Proposed labels:** `category: bug`, `area: emulator`, `area: QEC`

**`gh issue create` command:**

```bash
gh issue create \
  --repo QuEraComputing/tsim \
  --title "Clifford sparse geometric sampler: ~2% per-detector and ~12-14% logical-error-rate bias vs stim on DEPOLARIZE2 in rotated surface codes" \
  --label "category: bug" \
  --label "area: emulator" \
  --label "area: QEC" \
  --body-file /Users/brian/Basement/qec-kiln/upstream/tsim_clifford_bias.md
```

Review before running; this will create a public issue under your github.com/brianirish account.
