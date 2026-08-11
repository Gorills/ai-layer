# ADR 0006 — Clean-install bootstrap boundary

**Status:** accepted for the v0.9.1 candidate.

## Context

The v0.9.0 installer ran `scripts/release_gate.py` with the host Python before creating the isolated runtime. The release gate includes the production Skill contract gate, which imports AI Layer application modules and therefore requires runtime dependencies such as `pydantic-settings`. A genuinely clean machine does not have those dependencies yet, so installation could fail before the installer had a chance to install the exact-pinned release lock.

A release preflight is still required before the installer mutates the active machine runtime. That preflight cannot depend on the package it is about to install.

## Decision

Installation has two validation boundaries:

1. `scripts/bootstrap_release_gate.py` is a stdlib-only, dependency-free preflight. It validates the release manifest, exact lock shape, artifact checksums, wheel safety/identity/version and console-script alignment before a venv is created.
2. The complete `scripts/release_gate.py` runs with the newly created isolated runtime **after** exact-pinned dependencies and the application wheel are installed, but **before** runtime assets or the `current` pointer are changed.

A failed pre-activation install removes its incomplete release environment. Both preflight and full-gate failures remain fail-closed and expose a diagnostic message.

The installer and its bootstrap/release-lock verification scripts are governance-sensitive files.

## Consequences

- Clean installation no longer requires globally preinstalled AI Layer Python packages.
- Production Skill/architecture/governance validation still occurs before activation.
- The host Python is used only for stdlib bootstrap work and creating the isolated CPython 3.12 venv.
- Dependency installation remains closed-world and exact-pinned; the change does not introduce a floating bootstrap environment.
