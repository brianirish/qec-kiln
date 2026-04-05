# qec-kiln

Fire your [Sinter](https://github.com/quantumlib/Stim/tree/main/glue/sample) QEC jobs across cloud spot instances with [SkyPilot](https://github.com/skypilot-org/skypilot).

Sinter is the de facto standard for Monte Carlo sampling of quantum error correction circuits. It handles multicore parallelism, smart batching, decoder integration, and resumable CSV output — but it only runs on a single machine. This project adds the one thing it doesn't do: cloud-scale distribution across spot instances.

---

## The gap

Sinter's own documentation says it plainly:

> *"Sinter doesn't support cloud compute, but it does scale well on a single machine."*

For many QEC studies, a single 96-core machine is enough. But for large sweeps — many code distances × noise rates × decoder comparisons × code families — a single machine becomes a bottleneck. A threshold study with 50+ circuit variants, each needing 1M+ shots and 1000+ errors, can take days even on a big workstation.

qec-kiln distributes those circuit variants across cloud spot instances. Each instance runs a standard `sinter collect` job (which already handles everything well on a single node), and the platform handles provisioning, cost optimization, failure recovery, and CSV merging.

---

## How it works

**Sinter handles the inner loop.** On each node, `sinter collect` manages multicore sampling, dynamic batch sizing, decoder invocation (PyMatching, fusion_blossom, Tesseract, etc.), and writes resumable CSV output. This is battle-tested code written by Craig Gidney. We don't touch it.

**SkyPilot handles the outer loop.** It provisions spot/preemptible instances across 20+ clouds and Kubernetes clusters, auto-recovers from preemptions, and finds the cheapest available compute. Each SkyPilot managed job runs one `sinter collect` invocation against a subset of circuits.

**qec-kiln handles the glue.** It partitions circuit files across jobs, configures each Sinter invocation, collects the CSV fragments from cloud storage, and merges them into a single dataset compatible with `sinter plot`.

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

## Why not just run Sinter on a big machine?

You absolutely can, and for small sweeps you should. qec-kiln is for when:

- Your sweep has **50+ circuit files** and you want results in hours, not days
- You don't have access to a **96-core workstation** and cloud spot instances are cheaper than buying one
- You need **GPU-accelerated decoders** (e.g., NVIDIA's TensorRT decoder via CUDA-Q QEC) and don't own GPU hardware
- You're running **tsim circuits** (Clifford+T) that benefit from GPU acceleration during sampling
- You want to run **multiple decoder comparisons** (PyMatching vs. fusion_blossom vs. Tesseract) in parallel
- Your lab's shared cluster is **oversubscribed** and cloud overflow would unblock your research

For a quick 6-circuit threshold study, just run `sinter collect` locally. This project exists for when that stops being enough.

---

## Quick start

### Prerequisites

- Python 3.9+
- SkyPilot: `pip install "skypilot[kubernetes,aws,gcp]"`
- At least one backend passing `sky check`
- Stim circuit files (`.stim`) with detectors and observables annotated

### 1. Generate your circuits

Use Stim's built-in generators or your own circuit construction code. This is the step where the actual QEC research happens — qec-kiln doesn't change it at all.

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

Because the entire QEC ecosystem already speaks it. Sinter's `combine` and `plot` commands work on these CSVs. PyMatching's docs use them. Research papers publish threshold plots generated from them. Using a custom format would mean rebuilding all of that tooling for no benefit.

### Spot instance compatibility

Sinter's `--save_resume_filepath` flag makes it naturally spot-friendly. If a job is preempted and SkyPilot restarts it, Sinter picks up where it left off — it counts existing data in the CSV toward the collection targets. No custom checkpointing needed.

---

## Compatibility

qec-kiln works with any simulator or decoder that Sinter supports:

**Simulators**: Stim (Clifford, CPU), tsim (Clifford+T, CPU/GPU)

**Decoders**: PyMatching, fusion_blossom, Tesseract, chromobius, NVIDIA TensorRT decoder, or any custom `sinter.Decoder` subclass

**Infrastructure**: Any SkyPilot backend — Kubernetes, AWS, GCP, Azure, Lambda, RunPod, Nebius, and 15+ others

---

## How a platform / SRE engineer adds value

This project is designed to be co-owned by a platform engineer and a QEC research team:

- **Cluster management**: K8s node pools, NVIDIA device plugins, Kueue for fair-share GPU scheduling
- **Cost engineering**: Spot instances as default, multi-cloud fallback, autostop policies, per-researcher cost dashboards
- **Container pipeline**: Own the Docker images with pinned Stim/Sinter/decoder versions, CI to rebuild on releases
- **Observability**: Prometheus/Grafana for job completion rates, GPU utilization, cost tracking
- **Storage**: Configure S3/GCS buckets or K8s PVCs for CSV output with appropriate retention policies
- **Guardrails**: Resource quotas and GPU-hour budgets so researchers can launch freely

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
