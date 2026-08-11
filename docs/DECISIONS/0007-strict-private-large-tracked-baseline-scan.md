# ADR 0007 — Stream large tracked baseline files without weakening mutation privacy gates

**Status:** accepted for the v0.9.2 candidate.

## Context

`strict-private` repair audits both current changed/staged content and the existing tracked repository baseline. The same 1 MB read cap was previously reused for both purposes. A legitimate generated text file such as `package-lock.json` larger than that cap was therefore classified as `tracked_unscannable`, which made project repair and the entire machine upgrade fail even when there was no privacy violation.

Treating file size itself as a violation is not the intended security property. At the same time, relaxing the changed/staged gate would allow an agent to evade provenance scanning by making a file large.

## Decision

Use separate policies for the two responsibilities:

1. **Changed/staged mutation gate remains fail-closed.** Text above `MAX_SCAN_BYTES` continues to produce `privacy-scan-limit` and blocks the commit/workflow until it is explicitly handled.
2. **Tracked baseline audit streams large text.** Existing tracked non-binary files are read in bounded chunks with overlap, so regex matches crossing chunk boundaries are still detected without loading the complete file into memory.
3. Known binary content and NUL-detected binary content are not treated as text provenance. Actual read failures remain `tracked_unscannable` and therefore still require manual attention.
4. `src/ai_layer/privacy/service.py` is governance-protected because changing these semantics modifies a security/privacy invariant.

## Consequences

- Large clean lockfiles no longer make `ai-layer upgrade` fail solely because of size.
- Existing large tracked text containing forbidden provenance is still reported.
- New/changed oversized text cannot use streaming baseline behavior to bypass the strict-private mutation gate.
- Future changes to this policy require governance review and tests for both the baseline and mutation paths.
