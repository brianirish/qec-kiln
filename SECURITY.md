# Security Policy

## Scope

qec-kiln orchestrates cloud compute jobs via SkyPilot. It handles cloud credentials indirectly (through SkyPilot's credential management), generates shell commands, and reads/writes to cloud storage buckets. Security issues in any of these areas are in scope.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| main branch (latest) | Yes |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities using [GitHub's private vulnerability reporting](https://github.com/brianirish/qec-kiln/security/advisories/new).

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You should receive an acknowledgment within 72 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Security Considerations

### Cloud Credentials

qec-kiln relies on SkyPilot for cloud authentication. It never stores or manages cloud credentials directly. Ensure your SkyPilot configuration follows your cloud provider's security best practices:

- Use IAM roles with least-privilege permissions
- Scope S3/GCS bucket policies to only the buckets needed for CSV output
- Rotate credentials regularly

### Command Injection

`launch.sh` constructs shell commands from user-provided arguments (circuit paths, decoder names, etc.). While these are typically run by the researcher who wrote them, be aware that:

- Circuit file paths are passed to shell commands — avoid paths with special characters
- Decoder names are interpolated into SkyPilot YAML — only use trusted decoder names
- The `--dry-run` flag lets you inspect generated commands before execution

### Container Images

The provided Dockerfiles install packages from PyPI and conda-forge. For production use:

- Pin all package versions (not just Stim/Sinter)
- Use a private container registry
- Scan images for vulnerabilities before deploying to shared clusters

### Cloud Storage

CSV output files contain statistical data (error rates, shot counts), not sensitive information. However, bucket access should still be restricted to authorized users to prevent:

- Data tampering (modified CSV results)
- Unauthorized cost incurrence (launching jobs against your cloud account)

## Dependency Security

Key dependencies and their security posture:

| Dependency | Role | Notes |
| ---------- | ---- | ----- |
| [Stim](https://github.com/quantumlib/Stim) | Circuit simulation | Google Quantum AI, actively maintained |
| [Sinter](https://github.com/quantumlib/Stim) | Monte Carlo collection | Part of Stim, same maintainers |
| [SkyPilot](https://github.com/skypilot-org/skypilot) | Cloud orchestration | Handles all credential management |
| [PyMatching](https://github.com/oscarhiggott/PyMatching) | MWPM decoder | Widely used in QEC research |

## Disclosure Policy

We follow coordinated disclosure. Once a fix is available, we will:

1. Release a patched version
2. Publish a GitHub Security Advisory
3. Credit the reporter (unless they prefer anonymity)
