# qec-kiln

[![DOI](https://zenodo.org/badge/1202285772.svg)](https://doi.org/10.5281/zenodo.19432340)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Stim](https://img.shields.io/badge/Stim-≥1.14-green.svg)](https://github.com/quantumlib/Stim)
[![SkyPilot](https://img.shields.io/badge/SkyPilot-≥0.10-green.svg)](https://github.com/skypilot-org/skypilot)
[![bloqade-tsim](https://img.shields.io/badge/bloqade--tsim-≥0.1-green.svg)](https://pypi.org/project/bloqade-tsim/)

Distribute [Sinter](https://github.com/quantumlib/Stim/tree/main/glue/sample) QEC simulation jobs across cloud spot instances using [SkyPilot](https://github.com/skypilot-org/skypilot).

Sinter handles Monte Carlo sampling of quantum error correction circuits on a single machine — multicore parallelism, adaptive batch sizing, decoder integration, and resumable CSV output. qec-kiln adds multi-node distribution by partitioning circuit files across spot instances, with each node running an unmodified `sinter collect` process.

---

## Motivation

From the Sinter documentation:

> *"Sinter doesn't support cloud compute, but it does scale well on a single machine."*

For many QEC studies, a single machine is sufficient. However, large parameter sweeps — many code distances, noise rates, decoder comparisons, and code families — can take days on a single workstation. Chatterjee et al. reported running 8,640 Stim experiments over the course of weeks using four parallel workers, with individual runs at distance 25 taking approximately 62 hours.

qec-kiln distributes circuit variants across cloud spot instances. Each instance runs a standard `sinter collect` process. SkyPilot handles provisioning, spot recovery, and cost optimization. qec-kiln handles circuit partitioning and CSV merging.

---

## How it works

The system has three layers:

- **Sinter** (inner loop): On each node, `sinter collect` manages multicore sampling, adaptive batch sizing, decoder invocation, and resumable CSV output. This code is unmodified.
- **SkyPilot** (outer loop): Provisions spot/preemptible instances across cloud providers and Kubernetes clusters, handles preemption recovery, and selects the lowest-cost available compute.
- **qec-kiln** (glue): Partitions circuit files across jobs, launches SkyPilot managed jobs, and merges the resulting CSV fragments via `sinter combine`.

```
┌─────────────────────────────────────────────────────────────┐
│  Researcher                                                 │
│                                                             │
│  1. Generate .stim circuit files (as you normally would)    │
│  2. ./scripts/launch.sh circuits/ --decoders pymatching     │
│  3. ./scripts/merge.py --bucket s3://sinter-results         │
│  4. sinter plot --in merged.csv ...                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  SkyPilot Managed Jobs Controller                           │
│  Routes each circuit batch to cheapest spot instance        │
└────────┬───────────┬───────────┬───────────┬────────────────┘
         ▼           ▼           ▼           ▼
   ┌──────────┐┌──────────┐┌──────────┐┌──────────┐
   │ Spot #1  ││ Spot #2  ││ Spot #3  ││ Spot #N  │
   │          ││          ││          ││          │
   │ sinter   ││ sinter   ││ sinter   ││ sinter   │
   │ collect  ││ collect  ││ collect  ││ collect  │
   │ d=3,5    ││ d=7,9    ││ d=11,13  ││ d=15,17  │
   │ ↓        ││ ↓        ││ ↓        ││ ↓        │
   │ stats.csv││ stats.csv││ stats.csv││ stats.csv│
   └────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
        └───────────┴───────────┴───────────┘
                         │
                         ▼
                ┌─────────────────┐
                │  Cloud Storage  │
                │  (S3/GCS/PVC)   │
                │                 │
                │  CSV fragments  │
                │  per job        │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │  sinter combine │
                │  → merged.csv   │
                │  → sinter plot  │
                └─────────────────┘
```

---

## When to use this

For small sweeps, `sinter collect` on a single machine is sufficient. qec-kiln is useful when:

- The sweep has many circuit variants (50+) and single-machine wall time becomes a constraint
- No high-core-count workstation is available and cloud spot instances are more cost-effective
- GPU-accelerated decoders or tsim (Clifford+T) circuits require GPU hardware not available locally
- Multiple decoder comparisons (PyMatching, fusion_blossom, Tesseract) can be run in parallel
- A shared lab cluster is oversubscribed and cloud compute can supplement it

---

## Why SkyPilot?

qec-kiln uses [SkyPilot](https://github.com/skypilot-org/skypilot) for cloud orchestration rather than cloud-specific SDKs or custom job scheduling infrastructure.

### General properties

- **Multi-cloud resource selection.** A single YAML specifies resource requirements (e.g., 16+ CPUs or 1x A100 GPU). SkyPilot selects the lowest-cost spot instance across configured backends (AWS, GCP, Azure, Kubernetes, and others). If one provider lacks capacity, it falls through to the next.
- **Spot preemption recovery.** When a spot instance is reclaimed, SkyPilot provisions a replacement and restarts the job. Combined with Sinter's `--save_resume_filepath`, no work is lost.
- **Managed job controller.** `sky jobs launch` submits jobs to a controller that manages lifecycle, log streaming, and failure recovery. A single controller handles 2,000+ concurrent jobs.
- **Slurm and Kubernetes support.** The same YAML can target HPC clusters via Slurm or Kubernetes deployments, in addition to cloud providers.

### Fit for QEC simulation

Sinter collection jobs have properties that align well with SkyPilot's execution model:

1. **Embarrassingly parallel.** Each batch of circuits runs independently with no inter-node communication. This maps directly to independent managed jobs.
2. **Spot-compatible by construction.** Sinter writes incremental CSV output and resumes from partial results. SkyPilot handles instance recovery; Sinter handles state recovery.
3. **Short-lived.** Typical batches complete in 30–120 minutes. Short jobs have low preemption probability, and SkyPilot terminates instances on completion.
4. **GPU access without ownership.** tsim circuits and GPU-accelerated decoders can run on spot A100 instances (e.g., ~$0.70–1.50/GPU-hour on current providers).
5. **Reproducible.** The YAML is a complete job specification. Anyone with a configured cloud account can run the same sweep.

---

## Quick start

### Prerequisites

- Python 3.9+
- SkyPilot: `pip install "skypilot[kubernetes,aws,gcp]"`
- At least one backend passing `sky check`
- Stim circuit files (`.stim`) with detectors and observables annotated

### 1. Generate your circuits

Use Stim's built-in generators or your own circuit construction code. qec-kiln does not modify this step.

```python
import stim

for p in [0.001, 0.003, 0.005, 0.008, 0.01]:
    for d in [3, 5, 7, 9, 11, 13]:
        circuit = stim.Circuit.generated(
            code_task="surface_code:rotated_memory_x",
            distance=d,
            rounds=d,
            after_clifford_depolarization=p,
            after_reset_flip_probability=p,
            before_measure_flip_probability=p,
            before_round_data_depolarization=p,
        )
        path = f"circuits/d={d},p={p},b=X,type=rotated_surface_memory.stim"
        with open(path, "w") as f:
            print(circuit, file=f)
```

### 2. Launch the sweep

```bash
# Distribute circuits across spot instances, 6 circuits per job
./scripts/launch.sh circuits/ \
  --decoders pymatching \
  --max-shots 1_000_000 \
  --max-errors 1000 \
  --circuits-per-job 6

# Or dry-run to see what would be launched
./scripts/launch.sh circuits/ --dry-run
```

### 3. Monitor

```bash
sky jobs queue                    # job status
sky jobs logs <job_id>            # stream sinter's progress output
```

### 4. Collect and plot

```bash
# Merge CSV fragments from all jobs
python scripts/merge.py --bucket s3://sinter-results --out merged.csv

# Plot using Sinter's built-in plotting (unchanged from normal workflow)
sinter plot \
  --in merged.csv \
  --group_func "f'Rotated Surface Code d={m.d}'" \
  --x_func m.p \
  --xaxis "[log]Physical Error Rate" \
  --fig_size 1024 1024 \
  --out threshold.png
```

---

## Project structure

```
qec-kiln/
├── README.md
├── LICENSE                      # Apache 2.0
├── SECURITY.md                  # Vulnerability reporting and security considerations
├── CONTRIBUTING.md              # How to contribute
├── CODE_OF_CONDUCT.md           # Community guidelines
├── CHANGELOG.md                 # Release history
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── configs/
│   ├── sinter_job.yaml          # SkyPilot task: runs sinter collect on one batch
│   └── sinter_job_gpu.yaml      # GPU variant (for tsim circuits or GPU decoders)
├── scripts/
│   ├── launch.sh                # Partition circuits and launch SkyPilot jobs
│   ├── merge.py                 # Merge CSV fragments using sinter combine
│   └── partition.py             # Split circuit files into balanced batches
├── examples/
│   ├── generate_surface_codes.py    # Generate example circuit files
│   └── generate_tsim_circuits.py    # Generate Clifford+T circuits for tsim
├── docker/
│   ├── Dockerfile.cpu           # Stim + Sinter + PyMatching (CPU)
│   └── Dockerfile.gpu           # + tsim + CUDA (GPU)
├── docs/
│   └── design.md                # Architecture decisions and trade-offs
└── .gitignore
```

---

## Design decisions

### Why partition circuits across jobs (not shots)?

Sinter already parallelizes shots across CPU cores within a single machine. Splitting shots for the same circuit across multiple machines would require external coordination to merge partial statistics correctly. Splitting *circuits* across machines is trivially parallel — each job gets a disjoint set of `.stim` files, runs `sinter collect` independently, and produces a self-contained CSV. Merging is just `sinter combine` (concatenation + deduplication by `strong_id`).

### Why not build a custom Sinter sampler?

Sinter has a `Sampler` API that allows custom sampling backends. We could theoretically build a `CloudSampler` that dispatches work to remote nodes. But this would mean reimplementing job scheduling, failure recovery, and cost optimization — all things SkyPilot already does. Keeping the integration at the job level (one SkyPilot job = one `sinter collect` process) is simpler, more robust, and easier to reason about.

### Why Sinter's CSV format?

Sinter's CSV format is the standard interchange for QEC benchmarking. Sinter's `combine` and `plot` commands operate on it, PyMatching's documentation uses it, and research papers publish threshold plots generated from it. A custom format would require reimplementing existing tooling.

### Spot instance compatibility

Sinter's `--save_resume_filepath` flag writes statistics incrementally. If a spot instance is preempted and SkyPilot restarts the job, Sinter reads the existing CSV and counts collected data toward its targets. No additional checkpointing is needed.

---

## Compatibility

qec-kiln works with any simulator or decoder that Sinter supports:

**Simulators**: Stim (Clifford, CPU), tsim (Clifford+T, CPU/GPU)

**Decoders**: PyMatching, fusion_blossom, Tesseract, chromobius, NVIDIA TensorRT decoder, or any custom `sinter.Decoder` subclass

**Infrastructure**: Any SkyPilot backend — Kubernetes, AWS, GCP, Azure, Lambda, RunPod, Nebius, and 15+ others

---

## Operational considerations

For groups running qec-kiln regularly, a platform engineer can manage:

- **Cluster configuration**: K8s node pools, NVIDIA device plugins, Kueue for GPU scheduling
- **Cost management**: Spot instance policies, multi-cloud fallback, autostop, per-user budgets
- **Container images**: Pinned Stim/Sinter/decoder versions, CI rebuilds on upstream releases
- **Monitoring**: Job completion rates, GPU utilization, cost tracking
- **Storage**: S3/GCS bucket or K8s PVC configuration with retention policies

---

## License

Apache-2.0

---

## References

- [Stim](https://github.com/quantumlib/Stim) — Craig Gidney, Google Quantum AI
- [Sinter](https://github.com/quantumlib/Stim/tree/main/glue/sample) — Statistical collection subproject of Stim
- [tsim](https://github.com/QuEraComputing/tsim) — Clifford+T simulator via ZX stabilizer rank decomposition
- [PyMatching](https://github.com/oscarhiggott/PyMatching) — MWPM decoder
- [Tesseract](https://github.com/quantumlib/tesseract-decoder) — Search-based QEC decoder
- [SkyPilot](https://github.com/skypilot-org/skypilot) — Multi-cloud job orchestration
