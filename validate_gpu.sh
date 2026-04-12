#!/usr/bin/env bash
#
# Single-trial GPU validation run. Verifies the tsim+GPU pipeline works
# end-to-end before committing to a multi-trial benchmark.
#
# Cost: ~$2-5. Duration: ~10-30 min (mostly spot provisioning).
#
# Usage:
#   ./validate_gpu.sh

set -euo pipefail

export AWS_PROFILE=experiments

echo "=== Step 1: AWS auth ==="
aws sso login --profile experiments

echo ""
echo "=== Step 2: Upload circuits to S3 ==="
aws s3 sync circuits_tsim/ s3://qec-kiln-circuits/batch_0/ --profile experiments
echo "Uploaded $(ls circuits_tsim/*.circuit | wc -l) circuits"

echo ""
echo "=== Step 3: Launch GPU spot instance ==="
sky launch sinter_job_gpu.yaml -y -d \
  --name sinter-gpu-validate \
  --env BATCH_ID=0 \
  --env MAX_SHOTS=100000 \
  --env MAX_ERRORS=1000 \
  -i 20 --down

echo ""
echo "=== Step 4: Polling S3 for results ==="
echo "(DO NOT run 'sky status --refresh' while this is running)"
echo ""
while true; do
  if aws s3 ls s3://qec-kiln-results/gpu_batch_0/stats.csv --profile experiments 2>/dev/null; then
    echo ""
    echo "Results found!"
    break
  fi
  echo "  $(date +%H:%M:%S) -- waiting..."
  sleep 30
done

echo ""
echo "=== Step 5: Download results ==="
mkdir -p gpu_validation
aws s3 cp s3://qec-kiln-results/gpu_batch_0/stats.csv gpu_validation/stats.csv --profile experiments

echo ""
echo "=== Step 6: Summary ==="
echo "Results saved to gpu_validation/stats.csv"
echo ""
head -1 gpu_validation/stats.csv
echo "---"
tail -n +2 gpu_validation/stats.csv | while IFS=, read -r line; do
  echo "  $line"
done
echo ""
echo "Lines: $(wc -l < gpu_validation/stats.csv)"

echo ""
echo "=== Step 7: Tear down ==="
sky down -a -y

echo ""
echo "=== Done ==="
echo "Check gpu_validation/stats.csv for results."
echo "If everything looks good, proceed to multi-trial benchmark."
