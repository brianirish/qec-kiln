# Contributing to qec-kiln

Thanks for your interest in contributing. This project bridges QEC research tooling and cloud infrastructure, so contributions from both domains are welcome.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up your environment:

```bash
pip install stim sinter pymatching
pip install "skypilot[kubernetes]"  # or [aws], [gcp], etc.
```

4. Verify SkyPilot can see a backend: `sky check`

## What to Contribute

**High-value contributions:**

- Support for additional decoders (fusion_blossom, chromobius, Tesseract)
- Smarter partitioning strategies (balance by circuit complexity, not just count)
- Cost estimation tooling (predict spend before launching a sweep)
- Better error handling in merge.py (partial failures, malformed CSVs)
- CI/CD: automated tests, container builds, linting
- Documentation improvements and usage examples

**Out of scope:**

- Changes to Sinter or Stim internals — contribute those upstream
- Custom decoder implementations — those belong in their own packages
- Cloud provider-specific optimizations that break multi-cloud compatibility

## Development Workflow

1. Create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature
   ```

2. Make your changes. Keep commits focused and descriptive.

3. Test locally before submitting:
   - For Python changes: verify with a small circuit sweep
   - For YAML/shell changes: use `--dry-run` to inspect generated commands
   - For Docker changes: build and test the image locally

4. Open a pull request against `main`.

## Code Style

- **Python**: Follow PEP 8. Use type hints for function signatures. Keep scripts self-contained — this is a glue project, not a library.
- **Shell**: Use `set -euo pipefail`. Quote variables. Prefer long-form flags (`--output` over `-o`) for readability.
- **YAML**: Use comments to explain non-obvious SkyPilot configuration choices.

## Pull Request Guidelines

- **One concern per PR.** Don't mix a bug fix with a new feature.
- **Describe the "why."** The diff shows what changed; the PR description should explain why.
- **Test evidence.** Show that your change works — a dry-run output, a small sweep result, or a screenshot of `sinter plot` output.
- **Keep it compatible.** Changes should work across SkyPilot backends (at minimum Kubernetes + one public cloud). If your change is backend-specific, document that clearly.

## Reporting Issues

- **Bugs**: Open a GitHub issue with your SkyPilot version, Python version, cloud backend, and the error output.
- **Feature requests**: Open an issue describing the use case first. We'd rather discuss the approach before you invest time coding.
- **Security issues**: See [SECURITY.md](SECURITY.md). Do not open public issues for security vulnerabilities.

## Architecture Notes

Before making significant changes, read [design.md](design.md) to understand the architectural decisions. The key constraint is: **Sinter handles the inner loop, SkyPilot handles the outer loop, qec-kiln is just glue.** Contributions that respect this boundary are much easier to review and merge.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
