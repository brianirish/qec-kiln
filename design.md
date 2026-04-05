# Design: qec-kiln

## Core principle

Don't reinvent Sinter. Sinter is battle-tested, widely adopted, and handles the hard parts of QEC statistical collection (smart batching, decoder integration, resumable output, multicore parallelism). Our job is strictly the cloud distribution layer on top.

## Architecture

### Separation of concerns

| Layer | Tool | Responsibility |
|-------|------|----------------|
| Simulation + decoding | Sinter | Sampling, decoder invocation, batch sizing, CSV output |
| Cloud orchestration | SkyPilot | Provisioning, spot recovery, cost optimization, log streaming |
| Glue | qec-kiln | Circuit partitioning, job launch, CSV merging |

The glue layer is intentionally thin. It's ~300 lines of bash and Python.

### Partitioning strategy

We partition **circuits across jobs**, not shots within a circuit.

**Why not partition shots?** Sinter's internal parallelism already distributes shots across CPU cores on a single machine. Splitting shots for the same circuit across multiple machines would require:
1. External coordination to ensure disjoint random seeds
2. Custom merging logic to combine partial `TaskStats` correctly
3. Careful handling of Sinter's adaptive batch sizing (it starts small, ramps up)

None of this complexity is worth it when the natural parallelism unit — different circuits — is already embarrassingly parallel.

**Why not one circuit per job?** Launching a SkyPilot job has non-trivial overhead (VM provisioning, setup commands, pip install). Batching 4-10 circuits per job amortizes this overhead while still achieving good parallelism.

### Spot instance compatibility

Sinter's `--save_resume_filepath` flag writes incremental CSV data. If the process is killed and restarted, it reads existing data and continues where it left off. This makes it naturally compatible with spot preemptions — SkyPilot restarts the job on a new instance, Sinter resumes from the cloud-mounted CSV, and no work is lost.

There is one edge case: if the process is killed mid-write, the CSV may have a truncated last row. Sinter's documentation acknowledges this and suggests manually deleting the partial row. In practice, this is rare and can be handled by the merge script.

### CSV format and merging

Sinter writes CSV with columns: `shots, errors, discards, seconds, decoder, strong_id, json_metadata`

The `strong_id` is a cryptographic hash of the circuit + decoder configuration. This means:
- Two jobs collecting data for the same circuit will produce rows with the same `strong_id`
- `sinter combine` merges rows by `strong_id`, summing shots/errors/seconds
- Duplicate work from retries is automatically handled

This is why we use `sinter combine` for merging rather than writing custom aggregation logic.

## What we explicitly don't do

- **Custom Sinter samplers**: Sinter has a `Sampler` API for custom backends. We don't use it because keeping integration at the job level is simpler and more robust.
- **Custom result formats**: Sinter's CSV format is the community standard. PyMatching, Tesseract, and research papers all use it.
- **Decoder management**: Sinter handles decoder installation and invocation. We just pass `--decoders` through.
- **Circuit generation**: Researchers generate their own circuits. We provide examples but don't prescribe a workflow.

## Future possibilities

- **Smarter partitioning**: Estimate runtime per circuit (based on qubit count, round count, or a pilot run) and balance batches by expected wall-clock time rather than circuit count.
- **Live progress dashboard**: Aggregate Sinter's stderr progress output from all jobs into a single view.
- **Sinter custom Sampler for tsim**: If tsim gains a Sinter `Sampler` plugin, GPU jobs would benefit from Sinter's smart batching within each job.
- **Cost estimation**: Pre-launch estimation of total cost based on circuit count, expected shots, and spot pricing.
