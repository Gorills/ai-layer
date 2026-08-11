# ADR 0002 — Fail-closed quality and honest governance boundary

**Status:** accepted for the v0.9.0 candidate.

## Context

A repository-local agent with write access can edit tests, thresholds and gates. Pretending a local file hash prevents this would provide false assurance. Contributor checks can also become non-reproducible when pytest implicitly loads unrelated plugins installed in the machine environment.

## Decision

Use built-in non-loosenable architecture ceilings, a local tamper-evident governance baseline, one canonical quality gate and a release builder that invokes it. The canonical pytest stage disables global plugin autoload; any required pytest plugin must be an explicit project dependency/configuration. Production trust is external: protected branch, required CI, human approval for governance-sensitive changes and release-signing identity outside normal feature write access.

## Consequences

Local gates catch mistakes and casual bypasses but are not described as a cryptographic developer sandbox. Test execution does not silently depend on workstation-global pytest extensions. A production release is invalid when canonical quality is red or required external protections/evidence are absent.
