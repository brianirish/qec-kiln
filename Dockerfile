# Pre-built worker image for qec-kiln distributed Sinter runs.
# Skips the ~3-5 min pip install at every cluster cold start by baking
# the QEC simulation dependencies directly into the image.
#
# Build & push:
#   gh auth token | docker login ghcr.io -u brianirish --password-stdin
#   docker buildx build --platform linux/amd64 \
#     -t ghcr.io/brianirish/qec-kiln-worker:latest --push .
#
# Used by sinter_job_docker.yaml via:
#   resources:
#     image_id: docker:ghcr.io/brianirish/qec-kiln-worker:latest

FROM python:3.11-slim

# SkyPilot requires a Debian-based image with sudo (or root) and rsync
# for file mounts. python:3.11-slim runs as root by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo \
        rsync \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Sinter and the decoders we use. These wheels (~150 MB total)
# are what we want to skip downloading on every cold start.
RUN pip install --no-cache-dir \
        stim \
        sinter \
        pymatching \
        fusion-blossom

# Patch sinter for numpy 2.x compatibility (np.count_nonzero returns
# numpy.intp, which fails sinter's strict isinstance(x, int) assertion).
# See patches/sinter_numpy2_fix.py for the full explanation.
COPY patches/sinter_numpy2_fix.py /tmp/sinter_numpy2_fix.py
RUN python3 /tmp/sinter_numpy2_fix.py && rm /tmp/sinter_numpy2_fix.py

WORKDIR /workspace
