# Benchmark Plan

Collect wall-time and cost data for the arXiv paper.
Budget: $5-20. Expected cost: $3-8.

---

## Prerequisites (do these first)

```bash
# 1. Check SkyPilot version — upgrade to v0.12.0 if needed
sky --version
pip install -U "skypilot[aws,gcp,kubernetes]"

# 2. Verify at least one cloud backend passes
sky check

# 3. Create S3 buckets (skip if they already exist)
aws s3 mb s3://qec-kiln-circuits
aws s3 mb s3://qec-kiln-results

# 4. Generate the 42 test circuits
mkdir -p circuits
python generate_surface_codes.py
ls circuits/*.stim | wc -l
# Expected: 42 (6 distances x 7 noise rates)

# 5. Record your machine specs for the paper
sysctl -n machdep.cpu.brand_string
sysctl -n hw.ncpu
```

---

## Phase 1: Single-node baseline

Run ALL 42 circuits on ONE spot instance (same instance type as distributed).
This is the control — same hardware, only variable is distribution.

```bash
# Upload all circuits as a single batch
aws s3 sync circuits/ s3://qec-kiln-circuits/batch_baseline/

# Launch single-node baseline
sky jobs launch sinter_job.yaml -y \
  --env BATCH_ID=baseline \
  --env DECODERS=pymatching \
  --env MAX_SHOTS=1000000 \
  --env MAX_ERRORS=1000

# Record the start time
sky jobs queue
```

**Wait for this to complete before starting Phase 2.**

Record from `sky jobs queue`:
- Instance type SkyPilot chose: _______________
- Job start time: _______________
- Job end time: _______________
- Wall time: _______________

---

## Phase 2: Distributed run

Same 42 circuits, split into 7 batches of 6 via qec-kiln.

```bash
# Dry run first
./launch.sh circuits/ \
  --decoders pymatching \
  --max-shots 1000000 \
  --max-errors 1000 \
  --circuits-per-job 6 \
  --dry-run

# Launch for real
./launch.sh circuits/ \
  --decoders pymatching \
  --max-shots 1000000 \
  --max-errors 1000 \
  --circuits-per-job 6
```

Monitor:
```bash
sky jobs queue          # check all jobs
sky jobs logs <id>      # stream a specific job
```

Record from `sky jobs queue` (after ALL jobs complete):
- Instance types chosen: _______________
- Earliest job start: _______________
- Latest job end: _______________
- Distributed wall time: _______________
- Fastest job duration: _______________
- Slowest job duration: _______________

---

## Phase 3: Collect results

```bash
# Download baseline results
aws s3 cp s3://qec-kiln-results/batch_baseline/stats.csv baseline.csv

# Merge distributed results
python merge.py --bucket s3://qec-kiln-results --out distributed.csv

# Quick sanity check
wc -l baseline.csv distributed.csv
```

---

## Phase 4: Verify correctness

The baseline and distributed runs use independent random seeds, so error
rates won't be identical — but they should be statistically consistent.

```python
import sinter

baseline = sinter.read_stats_from_csv_files("baseline.csv")
distributed = sinter.read_stats_from_csv_files("distributed.csv")

# Check same set of strong_ids
b_ids = {s.strong_id for s in baseline}
d_ids = {s.strong_id for s in distributed}
print(f"Baseline strong_ids: {len(b_ids)}")
print(f"Distributed strong_ids: {len(d_ids)}")
print(f"Match: {b_ids == d_ids}")

# Compare error rates per circuit
for bs in sorted(baseline, key=lambda s: s.json_metadata.get('d', 0)):
    ds = next((s for s in distributed if s.strong_id == bs.strong_id), None)
    if ds:
        b_rate = bs.errors / bs.shots if bs.shots > 0 else 0
        d_rate = ds.errors / ds.shots if ds.shots > 0 else 0
        meta = bs.json_metadata
        print(f"d={meta.get('d'):2d} p={meta.get('p'):.4f}  "
              f"baseline={b_rate:.6f} distributed={d_rate:.6f}  "
              f"ratio={d_rate/b_rate:.3f}" if b_rate > 0 else
              f"d={meta.get('d'):2d} p={meta.get('p'):.4f}  both ~0")
```

All ratios should be near 1.0 (within statistical noise).

---

## Phase 5: Record cost

```bash
# Check cloud billing or use:
sky cost-report
```

---

## Phase 6: Fill in the paper

Open `paper/qec_kiln.tex`, go to the "Preliminary Results" section (~line 110).
Uncomment the table and prose. Replace every `[X]` with your numbers:

| Field | Where to get it |
|-------|----------------|
| Instance type | `sky jobs queue` output |
| Single-node wall time | Phase 1 timestamps |
| Distributed wall time | Phase 2 (latest end - earliest start) |
| Compute-hours (single) | Same as wall time |
| Compute-hours (distributed) | Sum of all 7 job durations |
| Speedup | Single wall time / distributed wall time |
| Single-node cost | `sky cost-report` or billing |
| Distributed cost | `sky cost-report` or billing |
| Fastest job | Phase 2 recordings |
| Slowest job | Phase 2 recordings |

Then recompile:
```bash
cd paper && pdflatex qec_kiln.tex && pdflatex qec_kiln.tex
```

---

## Fallback: if budget is tight

Reduce shots to stay under $5:
```bash
--max-shots 100000    # 10x fewer shots
--circuits-per-job 10 # fewer jobs (5 instead of 7)
```
The speedup ratio will be similar — that's what matters for the paper.

## Fallback: if a job fails

SkyPilot and Sinter's resume mechanism handle most failures automatically.
If a job fails and does not restart:
```bash
# Check logs
sky jobs logs <failed_job_id>

# Relaunch just that batch manually
sky jobs launch sinter_job.yaml -y \
  --env BATCH_ID=<N> \
  --env DECODERS=pymatching \
  --env MAX_SHOTS=1000000 \
  --env MAX_ERRORS=1000
```
