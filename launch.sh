#!/usr/bin/env bash
#
# Partition .stim circuit files and launch Sinter collection jobs on SkyPilot.
#
# Usage:
#   ./scripts/launch.sh circuits/ --decoders pymatching --max-shots 1000000
#   ./scripts/launch.sh circuits/ --decoders "pymatching fusion_blossom" --max-errors 1000
#   ./scripts/launch.sh circuits/ --gpu --decoders pymatching
#   ./scripts/launch.sh circuits/ --dry-run
#
# Prerequisites:
#   - sky check passing for at least one backend
#   - S3 bucket "qec-kiln-circuits" and "qec-kiln-results" accessible
#     (or update the bucket names in configs/*.yaml)

set -euo pipefail

# --- Defaults ---
CIRCUITS_DIR=""
DECODERS="pymatching"
MAX_SHOTS="1000000"
MAX_ERRORS="1000"
CIRCUITS_PER_JOB="6"
GPU=false
DRY_RUN=false
BUCKET="s3://qec-kiln-circuits"

# --- Parse arguments ---
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <circuits_dir> [options]"
  echo ""
  echo "Options:"
  echo "  --decoders STR         Decoder(s) to use (default: pymatching)"
  echo "  --max-shots INT        Max shots per circuit (default: 1000000)"
  echo "  --max-errors INT       Max errors per circuit (default: 1000)"
  echo "  --circuits-per-job INT Circuits per SkyPilot job (default: 6)"
  echo "  --gpu                  Use GPU instances (for tsim circuits)"
  echo "  --dry-run              Show what would be launched"
  exit 1
fi

CIRCUITS_DIR="$1"
shift

while [[ $# -gt 0 ]]; do
  case $1 in
    --decoders)         DECODERS="$2"; shift 2 ;;
    --max-shots)        MAX_SHOTS="$2"; shift 2 ;;
    --max-errors)       MAX_ERRORS="$2"; shift 2 ;;
    --circuits-per-job) CIRCUITS_PER_JOB="$2"; shift 2 ;;
    --gpu)              GPU=true; shift ;;
    --dry-run)          DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# --- Validate ---
if [[ ! -d "$CIRCUITS_DIR" ]]; then
  echo "Error: Directory not found: ${CIRCUITS_DIR}"
  exit 1
fi

CIRCUIT_COUNT=$(find "$CIRCUITS_DIR" -name "*.stim" | wc -l)
if [[ "$CIRCUIT_COUNT" -eq 0 ]]; then
  echo "Error: No .stim files found in ${CIRCUITS_DIR}"
  exit 1
fi

# --- Select task YAML ---
if $GPU; then
  YAML="configs/sinter_job_gpu.yaml"
else
  YAML="configs/sinter_job.yaml"
fi

# --- Partition circuits ---
BATCH_DIR=$(mktemp -d)
echo "Partitioning ${CIRCUIT_COUNT} circuits into batches of ${CIRCUITS_PER_JOB}..."
python scripts/partition.py "$CIRCUITS_DIR" \
  --circuits-per-job "$CIRCUITS_PER_JOB" \
  --output-dir "$BATCH_DIR"

NUM_BATCHES=$(find "$BATCH_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)

echo ""
echo "============================================"
echo "  qec-kiln sweep"
echo "============================================"
echo "  Circuits:     ${CIRCUIT_COUNT}"
echo "  Batches:      ${NUM_BATCHES}"
echo "  Per batch:    ~${CIRCUITS_PER_JOB}"
echo "  Decoders:     ${DECODERS}"
echo "  Max shots:    ${MAX_SHOTS}"
echo "  Max errors:   ${MAX_ERRORS}"
echo "  GPU:          ${GPU}"
echo "  Task YAML:    ${YAML}"
echo "============================================"
echo ""

if $DRY_RUN; then
  echo "[DRY RUN] Would upload ${NUM_BATCHES} batches to ${BUCKET}/"
  echo "[DRY RUN] Would launch ${NUM_BATCHES} SkyPilot managed jobs"
  for i in $(seq 0 $((NUM_BATCHES - 1))); do
    BATCH_CIRCUITS=$(ls "$BATCH_DIR/batch_${i}"/*.stim 2>/dev/null | wc -l)
    echo "  batch_${i}: ${BATCH_CIRCUITS} circuits"
  done
  rm -rf "$BATCH_DIR"
  exit 0
fi

# --- Upload circuit batches to cloud storage ---
echo "Uploading circuit batches to ${BUCKET}/..."
aws s3 sync "$BATCH_DIR" "${BUCKET}/" --quiet
echo "Upload complete."
echo ""

# --- Launch SkyPilot jobs ---
for i in $(seq 0 $((NUM_BATCHES - 1))); do
  echo "[${i}/${NUM_BATCHES}] Launching sinter-batch-${i}..."
  sky jobs launch "$YAML" -y \
    --env BATCH_ID="${i}" \
    --env DECODERS="${DECODERS}" \
    --env MAX_SHOTS="${MAX_SHOTS}" \
    --env MAX_ERRORS="${MAX_ERRORS}"
done

# --- Cleanup ---
rm -rf "$BATCH_DIR"

echo ""
echo "All ${NUM_BATCHES} jobs submitted."
echo ""
echo "Monitor:   sky jobs queue"
echo "Logs:      sky jobs logs <job_id>"
echo "Merge:     python scripts/merge.py --bucket s3://qec-kiln-results"
echo "Plot:      sinter plot --in merged.csv ..."
