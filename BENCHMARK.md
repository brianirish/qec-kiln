# Benchmark Plan

Collect wall-time and cost data for the arXiv paper.
Budget: $5-20. **Final actual cost: $9.95**.

---

## Status (as of 2026-04-07, ALL PHASES DONE)

All six table cells are filled. Paper `paper/qec_kiln.tex` updated:
- `tab:benchmark` filled with long-config numbers
- Long-configuration and Reliability paragraphs added to §III.B
- New §IV "Discussion and Open Questions" added, framing seven findings
  as hypotheses + proposed experiments (straggler crossover, docker
  non-improvement in long regime, crossover point, runtime-aware
  partitioning, SkyPilot autostop root cause, scaling beyond N=7,
  multi-trial robustness)
- Abstract updated with concrete 2.53× speedup claim
- Conclusion rewritten to reference Discussion section
- PDF recompiled, now 15 pages (was 12)

**Summary table (long config):**

| Configuration            | Instances | Wall time  | Compute-h | Spot cost |
|--------------------------|-----------|------------|-----------|-----------|
| Single-node baseline     | 1         | 1h 50m 51s | 1.85 h    | $0.37     |
| qec-kiln, cold start     | 7         | 43m 48s    | 1.84 h    | $0.66*    |
| qec-kiln, pre-built image| 7         | 49m 34s    | 1.88 h    | $0.75*    |

*Normalized cost assuming a correctly functioning `-i 5 --down` autostop
window. See the Reliability paragraph in the paper for the actual bills
($3.38 cold, $1.69 docker) and the SkyPilot autostop gotcha that caused
the inflation.

**Headline findings:**

1. Long cold-start delivers a **2.53× wall-time speedup** over single-node
   baseline, confirming the hypothesis that distribution wins when per-cluster
   sampling time exceeds provisioning overhead.
2. Docker is NOT meaningfully faster than cold-start in the long regime (and
   is actually slightly slower in our run, 49m 34s vs 43m 48s — within
   spot-capacity-search variance). The 28% improvement docker gave in the
   short regime is lost in noise at 10× larger workloads.
3. Both long distributed runs correctly reproduce the baseline statistics:
   42/42 strong\_ids match across baseline + cold + docker; worst error-rate
   ratio between cold and docker for cells with ≥50 errors is 1.084 (Poisson).
4. Load imbalance is the dominant remaining inefficiency: the slowest batch
   (batch\_2, p=0.002) takes 41m 30s of sinter time — within 2 min of the
   whole end-to-end wall time. Runtime-aware partitioning would close most
   of the remaining gap to the $7\times$ ideal.

---

**Phase 1 (short baseline, 10M shots / 1K errors): DONE**
- `sinter-batch-baseline-10m`, m6i.4xlarge spot, pymatching decoder
- Job duration: **3m 34s** (214s)
- Output: `baseline_10m.csv` (1615 lines, 42 unique strong_ids after `sinter combine`)

**Phase 2a (short distributed, COLD START, 7 batches × 6 circuits): DONE**
- 7× sky launch in parallel, m6i.4xlarge spot, no docker (pip install at every cluster)
- End-to-end wall time: **7m 41s** (461s) — launch script start to last S3 write
- Max single-job duration: 1m 7s (batch_3)
- Total cost: $0.43 (clusters $0.33 + previous controller $0.10)
- Spread across 6 AWS regions (capacity routing)
- 2 of 7 clusters spot-preempted *after* job completed (data preserved via S3 cp)
- **Speedup vs single-node**: 0.46× (slowdown — provisioning overhead dominates)
- Correctness: 42/42 strong_ids match baseline ✓
- Output: `distributed_csvs/batch_*.csv`, merged `distributed_10m.csv`

**Phase 2b (short distributed, WITH DOCKER): DONE (this evening)**
- Pre-built `ghcr.io/brianirish/qec-kiln-worker:latest` (Dockerfile + patches/)
- Same 7 batches, same params
- End-to-end wall time: **5m 33s** (333s) — **1.39× faster than cold-start**
- Total cost: $0.20 (used `-i 2 --down` instead of `-i 10 --down`)
- Correctness: 42/42 strong_ids match baseline ✓
- Output: `distributed_csvs_short_docker/batch_*.csv`, merged `distributed_short_docker.csv`
- See `logs/cell_c_summary.txt` for full timing data

**Phase 3 (long baseline, 500M shots / 10K errors): DONE**
- Ran as managed job overnight. SUCCEEDED, 0 recoveries.
- **Job duration: 1h 50m 51s** (6651s) — total wall time 1h 52m 28s
- Output: `baseline_500m.csv` (42/42 unique strong_ids ✓, 5.89B total shots, 344K total errors)
- Per-circuit: min 45K shots (high-noise, hit `MAX_ERRORS=10000`),
  max 500M shots (low-noise, hit `MAX_SHOTS=500M`)

**Phase 3a (long distributed, NO DOCKER): FAILED then RE-RUNNING**
- First attempt at 16:16 UTC: 7× `sky launch -d -i 5 --down`. Five batches
  completed and uploaded (batch_0,3,4,5,6, slowest 28:45 wall time), but at
  16:59:52 UTC SkyPilot's autostop sweep simultaneously terminated **all 7
  worker clusters** — including batch_1 and batch_2, which were still running
  their `sinter collect` jobs and never wrote to S3.
- Apparent trigger: a `sky status --refresh` call ~16:59 UTC, which forced
  SkyPilot to evaluate autostop on all clusters. The `-i 5` window was short
  enough that the still-running clusters were caught in the same sweep.
- The 5 completed batches were saved to `distributed_csvs_cold_long_partial/`
  (with `per_cluster_timings.txt`) for use in the paper's Reliability paragraph.
- **Re-running** at 17:42 UTC (approx): 7× `sky launch -d -i 30 --down`,
  identical params otherwise. Polling S3 only — no `sky status --refresh` or
  any `sky jobs *` calls during the run.

**Phase 3b (long distributed, WITH DOCKER): NOT STARTED**
- Will run **sequentially after** Phase 3a re-run, not in parallel.
- **Reason:** the headline metric for the paper is end-to-end wall time, and the
  short-config runs were sequential (clean isolation). Running 14 spot clusters in
  parallel would risk capacity contention skewing both wall-time numbers, and would
  make per-cell monitoring (sky status, S3 polling) much harder. Sequential adds
  ~1h to total wallclock at zero data-quality risk. Documented for the paper as well.

## Lessons learned (cumulative)

1. **S3 FUSE mounts do not support `flush=True`** which Sinter uses for
   `--save_resume_filepath`. Fixed by writing to `/tmp/` locally and copying
   to S3 on completion (sacrifices intra-job spot resume; for short jobs OK).

2. **`${BATCH_ID}` does not expand in YAML `name:` field.** Must pass
   `--name` on the command line.

3. **`sky jobs launch` in a loop serializes onto one worker instance.** For
   actual parallelism use `sky launch` (per-cluster) with `&`. Use `sky jobs
   launch` only when you specifically want managed-job preemption recovery
   for long unattended runs.

4. **`launch.sh` originally referenced `configs/` and `scripts/` subdirs**
   that don't exist — fixed to use root-level paths.

5. **For short benchmarks, distribution is a NET LOSS.** With a 3.5-min
   single-node baseline, the 7-cluster distributed run took 7m 41s end-to-end
   because cloud provisioning overhead (~5-6 min for capacity search + pip
   install) dominates per-job runtime (≤1m 7s). Job-level speedup is real
   (3.2× max-job vs baseline) but masked by setup cost.

6. **Docker pre-built image with deps baked in saves ~28%** even at the
   short config (5m 33s vs 7m 41s). Should help proportionally more as
   per-job runtime stays roughly the same.

7. **numpy 2.x breaks sinter's strict `isinstance(x, int)` assertions.**
   Root cause: `sinter._decoding._stim_then_decode_sampler.classify_discards_and_errors`
   returns `np.count_nonzero()` results, which are `numpy.intp` (no longer
   subclass of `int` in numpy 2.x). Patched in `patches/sinter_numpy2_fix.py`
   and baked into the docker image. **Should be submitted upstream as a PR
   to quantumlib/Stim.**

8. **Use `-i 2 --down` for tight autostop** when cluster runtime is
   predictable. Saved ~$0.30 vs `-i 10 --down`. Risk: if you miss the
   2-min window after job completion, the cluster terminates before you
   can `sky logs`. Mitigation: capture logs immediately on completion.

9. **Spot capacity is not always available where SkyPilot first tries.**
   Cold-start run saw 3-4 capacity-search attempts per cluster (us-east-2a/b/c
   → eu-north-1b → us-west-2b). Adds ~30-90 sec to provisioning per attempt.
   This is unpredictable variance that affects wall-time measurements.

10. **Managed-jobs controller idle cost is non-trivial and easy to miss.**
    `sky-jobs-controller-0a8cc3d5` (m6i.xlarge, $0.19/hr) accumulated **$2.70**
    of idle cost (~14 h uptime) after the long baseline finished. Its 10-min
    autostop *should* have triggered, but `sky jobs queue --refresh` resets the
    idle timer — so any morning sanity check restarts the meter. SkyPilot blocks
    `sky stop` and `sky autostop` on jobs controllers explicitly. Mitigations:
    (a) avoid `sky jobs *` commands when not actively using managed jobs;
    (b) factor controller idle into cost reporting (we missed this in BENCHMARK
    until the morning `sky cost-report --all` showed it).

11. **`sky status --refresh` can kill running `sky launch` jobs.** During the
    first cold-long Cell B attempt, polling progress with `sky status --refresh`
    triggered an autostop sweep that simultaneously terminated all 7 worker
    clusters at 16:59:52 UTC, even though 2 of them (batch_1, batch_2) had
    `sinter collect` processes still running. SkyPilot's idleness check
    apparently re-evaluates autostop on `--refresh` and does not correctly
    detect that the per-cluster job is still active. With `-i 5 --down`, the
    margin between "job started" and "autostop fires on --refresh" was zero.
    **Mitigations:** (a) never run `sky status --refresh` while `sky launch`
    jobs are in flight; (b) use `-i 20` or higher for any long-running job;
    (c) poll S3 directly for completion, not SkyPilot APIs.

---

## TOMORROW MORNING: Pick up here

### 0. Restore environment

```bash
export AWS_PROFILE=experiments
aws sso login --profile experiments  # token expires every ~12h
```

### 1. Verify the long baseline finished overnight

```bash
sky jobs queue
# Look for: sinter-batch-baseline-500m, status SUCCEEDED
# If still RUNNING: it just needs more time, leave it. Check sky jobs logs 1.
# If FAILED: check sky jobs logs 1, may need to relaunch.
# If RECOVERED N>0: spot was preempted N times, but SkyPilot restarted it. Fine.

aws s3 ls s3://qec-kiln-results/batch_baseline_500m/stats.csv --profile experiments
# Should show a recent timestamp (after baseline completion).

aws s3 cp s3://qec-kiln-results/batch_baseline_500m/stats.csv baseline_500m.csv --profile experiments
wc -l baseline_500m.csv
```

The managed jobs controller will auto-stop within 10 min of job completion.
If it's still up after baseline finishes, it'll cost ~$0.04/hr until autostop.

### 2. Launch Cell B: long distributed, NO docker

```bash
mkdir -p logs/cold_long
date -u +"%Y-%m-%dT%H:%M:%SZ" > logs/cold_long/start.txt
for i in $(seq 0 6); do
  sky launch sinter_job.yaml -y -d \
    --name "sinter-cold-l-${i}" \
    --env BATCH_ID="${i}" \
    --env DECODERS=pymatching \
    --env MAX_SHOTS=500000000 \
    --env MAX_ERRORS=10000 \
    -i 5 --down \
    > "logs/cold_long/launch_${i}.log" 2>&1 &
done
wait
date -u +"All submissions returned: %Y-%m-%dT%H:%M:%SZ"
```

Why `-i 5 --down`: longer jobs (~30-60 min) → 5 min idle window gives time to
grab logs after completion before auto-teardown. Tighter than `-i 10` to save
on idle cost.

Expected: ~30-60 min wall time, ~$1-3 cost.

### 3. Launch Cell B+C: long distributed, WITH docker

Run after Cell B completes (or in parallel — they're independent, but parallel
makes monitoring harder):

```bash
mkdir -p logs/docker_long
date -u +"%Y-%m-%dT%H:%M:%SZ" > logs/docker_long/start.txt
for i in $(seq 0 6); do
  sky launch sinter_job_docker.yaml -y -d \
    --name "sinter-doc-l-${i}" \
    --env BATCH_ID="${i}" \
    --env DECODERS=pymatching \
    --env MAX_SHOTS=500000000 \
    --env MAX_ERRORS=10000 \
    -i 5 --down \
    > "logs/docker_long/launch_${i}.log" 2>&1 &
done
wait
```

### 4. Monitor and collect

```bash
sky status                     # see clusters
sky queue                      # job durations
sky cost-report --all          # cost breakdown

# Wait for completion. S3 timestamp = end-of-job for each batch.
aws s3 ls s3://qec-kiln-results/ --recursive --profile experiments | grep stats.csv
```

Save results to dedicated dirs so they don't collide:
```bash
mkdir -p distributed_csvs_cold_long distributed_csvs_docker_long
for i in 0 1 2 3 4 5 6; do
  aws s3 cp s3://qec-kiln-results/batch_${i}/stats.csv distributed_csvs_cold_long/batch_${i}.csv --profile experiments
done
# Then re-launch the docker variant, which will overwrite s3://qec-kiln-results/batch_*/stats.csv
# Then save those to distributed_csvs_docker_long/
```

**IMPORTANT**: Cells B and B+C BOTH write to `s3://qec-kiln-results/batch_<i>/stats.csv`,
so you must download Cell B's results to `distributed_csvs_cold_long/` BEFORE
launching Cell B+C, or the docker run will clobber them.

### 5. Verify and merge each cell

```python
import sinter
for label, dir_ in [('cold_long', 'distributed_csvs_cold_long'),
                    ('docker_long', 'distributed_csvs_docker_long')]:
    stats = []
    for i in range(7):
        stats.extend(sinter.read_stats_from_csv_files(f'{dir_}/batch_{i}.csv'))
    by_id = {}
    for s in stats:
        by_id[s.strong_id] = by_id[s.strong_id] + s if s.strong_id in by_id else s
    print(f"{label}: {len(by_id)} unique circuits")
    with open(f'distributed_{label}.csv', 'w') as f:
        f.write(sinter.CSV_HEADER + '\n')
        for sid in sorted(by_id):
            f.write(by_id[sid].to_csv_line() + '\n')
```

Then verify all 4 result sets agree on per-circuit error rates (within statistical noise).

### 6. Fill in the 2x2 table in `paper/qec_kiln.tex`

Find the commented-out table near the "Preliminary Results" section.
Uncomment and fill with the actual numbers:

|             | Short (10M shots, 1K errors)                          | Long (500M shots, 10K errors)                           |
|-------------|-------------------------------------------------------|---------------------------------------------------------|
| Single-node | 3m 34s, $0.01                                         | (from `baseline_500m.csv` + `sky jobs queue` for time)  |
| Cold start  | 7m 41s, $0.43, 0.46× speedup                          | (from Cell B run)                                       |
| Docker      | 5m 33s, $0.20, 0.64× speedup, 1.39× over cold-start   | (from Cell B+C run)                                     |

Then recompile:
```bash
cd paper && pdflatex qec_kiln.tex && pdflatex qec_kiln.tex
```

### 7. Tear down anything that's still running

```bash
sky status
sky down -a -y         # tears down regular clusters (not the jobs controller)
sky jobs cancel -a     # if any managed jobs still running
```

The jobs controller auto-stops 10 min after the last managed job completes.

---

## Reference: what the original phases looked like

Phase 1 (baseline) and Phase 2 (distributed) are kept above in the Status and
Tomorrow sections. Everything below is the original plan, kept as reference.

---

## Phase 3: Collect results (reference)

```bash
# Download baseline results (already done — saved as baseline_10m.csv)
aws s3 cp s3://qec-kiln-results/batch_baseline/stats.csv baseline_10m.csv

# Merge distributed results
uv run --with "sinter stim" python merge.py --bucket s3://qec-kiln-results --out distributed.csv
```

---

## Phase 5: Record cost (reference)

```bash
# Check cloud billing or use:
sky cost-report
```

Also check AWS Cost Explorer under the experiments account.

---

## Fallback: if budget is tight

Reduce shots:
```bash
MAX_SHOTS=1000000   # 10x fewer shots
# Or fewer parallel clusters:
for i in $(seq 0 4); do ... --circuits-per-job 9 ...
```

## Fallback: if a cluster fails

```bash
# Check logs
sky logs sinter-batch-<N>

# Re-launch just that batch
sky launch sinter_job.yaml -y \
  --name "sinter-batch-<N>" \
  --env BATCH_ID=<N> \
  --env DECODERS=pymatching \
  --env MAX_SHOTS=10000000 \
  --env MAX_ERRORS=1000
```
