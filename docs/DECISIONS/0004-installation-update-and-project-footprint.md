# ADR 0004 — Immutable releases, signed update channel and project footprint

**Status:** accepted for the v0.9.0 candidate.

## Context

Normal updates should not overwrite the active environment in place, and target repositories should not become a storage location for AI Layer implementation. A public update URL/trust key cannot be invented inside source code. Earlier project attachment also coupled external storage with a strict provenance/privacy policy, even though these are independent concerns.

## Decision

Keep immutable per-release runtimes plus atomic active pointer. `ai-layer update` verifies a signed manifest, artifact checksum and safe archive before invoking release preflight/installer. Publisher endpoint/key are release-channel infrastructure. Development repository contents and runtime artifact allowlist are separate.

Project attachment has independent modes: `standard` may create only minimal generated/reversible host bridges; `external` stores AI Layer state at machine level and removes project bridges while retaining normal provenance policy; `strict-private` uses the same external attachment plus provenance prohibition and the repository privacy guard. Default attachment remains `standard` until supported hosts demonstrate equivalent black-box behavior with `external`.

## Consequences

Zero repository footprint no longer requires selecting the privacy policy. A future default switch is a host-compatibility/UX promotion decision rather than an architectural rewrite. Production update trust remains external to ordinary feature write access.
