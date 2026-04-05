# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2025-04-05

### Added

- Initial release
- Circuit partitioning across SkyPilot managed jobs (`partition.py`)
- Job launch orchestration (`launch.sh`)
- CSV fragment merging via `sinter combine` (`merge.py`)
- CPU Dockerfile with Stim, Sinter, and PyMatching
- GPU Dockerfile with tsim and CUDA support
- SkyPilot task YAML for CPU and GPU jobs
- Example circuit generators for surface codes and Clifford+T circuits
