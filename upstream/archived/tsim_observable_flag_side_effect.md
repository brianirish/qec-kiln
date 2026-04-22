# Bug report draft: `use_observable_reference_sample` has a side effect on detector event rates

**Target repo:** https://github.com/QuEraComputing/tsim

## Links

- Reproducer adapted from `spike_tsim/test_t5d_distillation_fidelity.py` in https://github.com/brianirish/qec-kiln (if published; otherwise the reproducer lives in the `spike_tsim/` directory of the qec-kiln working tree).
- Wrapper that prompted the discovery: `spike_tsim/tsim_sampler.py` in the same repo. The wrapper sets both `use_detector_reference_sample=True` and `use_observable_reference_sample=True` to align with stim's bit conventions (XOR against a noiseless reference); toggling just the observable flag independently exposed the side effect.
- Finding discovered during the qec-kiln tsim integration spike (Brian Irish, solo researcher).

---

## Title (for the issue)

`use_observable_reference_sample` changes detector event rates (a flag named for observables should not affect detectors)

## Summary

On `CompiledDetectorSampler.sample(...)`, toggling `use_observable_reference_sample` while holding `use_detector_reference_sample=True` fixed changes the **detector** event rate on a magic-state-distillation circuit. A flag whose name and documented purpose is scoped to observable bits should not mutate detector statistics.

The testable claim is the behavioral one: **`use_observable_reference_sample` is not supposed to be able to change detector bits.** The exact shift magnitude depends on the circuit, shot count, and RNG state; on the reproducer below we observed a ~2% global detector-rate shift, but the bug report is the existence of the dependency, not the specific number.

## Minimal reproducer

Self-contained, depends only on `tsim` and `numpy`:

```python
import math
import numpy as np
import tsim

theta = -math.acos(math.sqrt(1 / 3)) / math.pi
circuit = tsim.Circuit(f"""
    R 0 1 2 3 4
    R_X({theta}) 0 1 2 3 4
    T_DAG 0 1 2 3 4
    DEPOLARIZE1(0.02) 0 1 2 3 4

    SQRT_X 0 1 4
    CZ 0 1 2 3
    SQRT_Y 0 3
    CZ 0 2 3 4
    TICK
    SQRT_X_DAG 0
    CZ 0 4 1 3
    TICK
    SQRT_X_DAG 0 1 2 3 4

    T 0
    R_X({-theta}) 0

    M 0 1 2 3 4
    DETECTOR rec[-4]
    DETECTOR rec[-3]
    DETECTOR rec[-2]
    DETECTOR rec[-1]
    OBSERVABLE_INCLUDE(0) rec[-5]
""")

shots = 200_000
n_det = circuit.num_detectors

configs = [
    dict(use_detector_reference_sample=True,
         use_observable_reference_sample=False),
    dict(use_detector_reference_sample=True,
         use_observable_reference_sample=True),
    dict(use_detector_reference_sample=True,
         use_observable_reference_sample=True,
         separate_observables=True),
    dict(use_detector_reference_sample=True,
         use_observable_reference_sample=True,
         separate_observables=True,
         bit_packed=True),
]

for cfg in configs:
    sampler = circuit.compile_detector_sampler(seed=None)
    out = sampler.sample(shots=shots, **cfg)
    dets = out[0] if isinstance(out, tuple) else out
    if cfg.get("bit_packed"):
        dets = np.unpackbits(dets, axis=1, bitorder="little", count=n_det)
    rate = float(dets.mean())
    print(f"cfg={cfg} -> detector rate={rate:.4f}")
```

## Observed

Global detector rate (averaged over 200k shots) on the circuit above:

| flag combo                                                          | detector global rate |
|---------------------------------------------------------------------|---------------------:|
| `use_detector_reference_sample=True`                                | 0.4780               |
| `use_detector_reference_sample=True, use_observable_reference_sample=True` | 0.4993        |
| + `separate_observables=True`                                        | 0.5013              |
| + `bit_packed=True`                                                  | 0.5000              |

Rows 1 and 2 differ only in the value of `use_observable_reference_sample`, and the detector rate moves by roughly 2.1%. (The reproducer uses `seed=None`, so exact values will differ on rerun; the ~2% gap between rows 1 and 2 is reproducible in the sense that it is reliably much larger than the Bernoulli sampling noise on 200k × 4 detector draws.)

## Expected

`use_observable_reference_sample` should affect only how observable bits are reported (absolute values vs. XOR against a noiseless reference sample). Detector output should be independent of the value of this flag.

## Hypothesized root cause

The noiseless reference sample used to XOR observable bits likely shares RNG state with the detector path: computing the observable reference may consume additional RNG draws that desynchronize the subsequent detector sampling from the `use_observable_reference_sample=False` path. Alternatively, both reference-sample flags may gate entry into a shared "reference mode" whose per-bit bookkeeping differs depending on whether observables are included. A maintainer who knows the sampler internals will confirm or refute these faster than a black-box spike can.

## Impact

Low for callers who set both `use_detector_reference_sample` and `use_observable_reference_sample` to the same value (as stim-compatible wrappers do) and never vary one flag independently — the pairing is self-consistent and aligns with stim's XOR-against-reference convention.

Higher for any user who compares detector statistics across runs that differ only in `use_observable_reference_sample`, or who assumes the flag is scoped to observable bits only. It is also a latent pitfall for anyone debugging a wrapper: detector rates should not be perturbed by a flag named for observables.

## Environment

```
tsim==0.1.2
numpy==2.x
python==3.12
platform=darwin (CPU)
```

## Ready for submission

**Proposed title:**

> `use_observable_reference_sample` changes detector event rates (flag named for observables affects detector bits)

**Proposed labels:** `category: bug`, `area: emulator`

**`gh issue create` command:**

```bash
gh issue create \
  --repo QuEraComputing/tsim \
  --title "use_observable_reference_sample changes detector event rates (flag named for observables affects detector bits)" \
  --label "category: bug" \
  --label "area: emulator" \
  --body-file /Users/brian/Basement/qec-kiln/upstream/tsim_observable_flag_side_effect.md
```

Review before running; this will create a public issue under your github.com/brianirish account.
