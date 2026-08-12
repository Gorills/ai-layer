---
slug: file-handling
description: Secure and reliable file engineering for uploads, paths, streaming, validation, storage, archives, naming, cleanup and untrusted content.
kind: capability
keywords:
- file
- upload
- download
- path
- archive
- streaming
- mime
- storage
- symlink
- cleanup
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# File Handling Skill

## Apply when

Use for uploads/downloads, local filesystem access, object storage, archive extraction, import/export files, generated artifacts and any operation where user-controlled names/content can reach storage or parsers.

## Core contract

- Treat file names, paths, MIME types, extensions and content as untrusted independent inputs; none proves the others.

- Resolve filesystem paths against an allowed root and prevent traversal plus symlink escape when operating on local files.

- Generate server-side storage names/keys where possible; preserve user display names as metadata rather than authoritative paths.

- Bound file size, count, archive expansion, parsing complexity and processing time before expensive work.

- Stream large files rather than loading whole payloads into memory, while enforcing size limits during streaming.

- Validate content using the parser/format needs and security policy; client MIME/extension alone is insufficient.

- Store untrusted uploads outside executable/static code roots and serve with deliberate content type/disposition/access control.

- Archive extraction must reject absolute paths, traversal, unsafe links and expansion bombs; enforce total expanded size and file count.

- Use atomic write/rename patterns for generated/critical local files and clean temporary files on both success and failure.

- Define retention/deletion/ownership; object storage consistency and signed URL lifetime are part of the data-access contract.

## Evidence to inspect

- Upload/download endpoints, multipart/body limits and reverse-proxy/server limits.

- Path construction, normalization, symlink behavior and filesystem permissions.

- Storage backend configuration, bucket/key layout, access control and signed URL generation.

- Parser/image/document/archive libraries and their version/security posture.

- Temporary-file creation/cleanup and background processing pipeline.

- Tests for traversal, oversized content, malformed files and partial storage failures.

## Decision rules

- If user input contributes to a path, canonicalize/resolve beneath a fixed allowed root and reject escapes; do not rely on string prefix checks.

- If original filename is needed, store sanitized display metadata separately from a generated storage key.

- If file may be large, stream and count bytes with an enforced maximum rather than reading then checking length.

- If content will be rendered inline in a browser, validate type and set safe content disposition/type; download attachment may be safer for untrusted formats.

- If archive extraction is supported, enforce per-file plus total expanded budgets and safe link policy before materialization.

- If processing can fail after upload, track durable file state and cleanup/retry rather than leaving orphaned storage silently.

- If access is private, authorize every download or generate short-lived scoped URLs; obscurity of object key is not authorization.

- If replacing an existing file atomically matters, write to a temp sibling, fsync as needed for durability model, then rename/replace.

## Workflow

1. Identify trust boundary, expected formats, maximum sizes/counts and storage/access lifecycle.

2. Map the full path from transport through temporary storage, parsing/processing, durable storage and download/deletion.

3. Choose generated keys, safe display-name handling and root/bucket ownership policy.

4. Add streaming bounds, content validation and archive/path defenses before expensive parsing/extraction.

5. Implement atomic persistence/state transition and guaranteed temporary cleanup.

6. Apply authorization/content-disposition/retention semantics at download and deletion boundaries.

7. Test malformed, oversized, traversal/symlink, duplicate name and interrupted processing cases.

8. Inspect disk/object-store leftovers and access behavior after both success and failure.

## Implementation patterns

- Use library-managed temporary files/directories with deterministic cleanup and explicit permissions.

- Hash-based or UUID storage keys avoid collision/path ambiguity; content hashes can deduplicate only when privacy/side-channel implications are acceptable.

- For local safe-join, compare resolved path ancestry after resolution and define whether symlinks are allowed at all.

- For object storage, separate immutable content key from mutable metadata/database record when replacement/versioning matters.

- For import jobs, keep original file plus parsed job state only if retention/security policy permits and it aids reproducibility.

- For generated downloads, stream rows/chunks and set deterministic encoding/escaping; avoid building enormous in-memory buffers.

- For image/media processing, decode with maintained libraries and enforce pixel/dimension/resource limits in addition to compressed byte size.

- For archive inputs, inspect entries before extraction and materialize only after all safety budgets/policies pass.

## Failure modes

- Extension trust: `.jpg` is passed to image code though content is arbitrary. Validate/decode content.

- Traversal substring check: encoded/absolute/symlink path escapes allowed root. Resolve and enforce ancestry/link policy.

- Memory bomb: size checked only after reading. Enforce streaming/decompression limits.

- Archive zip bomb: compressed size is small but expansion exhausts disk. Bound expanded bytes/files/depth.

- Original filename key: collisions/path separators/control chars cause overwrite or header issues. Generate key and sanitize display metadata.

- Public object by accident: bucket/default ACL exposes private upload. Enforce access policy and test unauthenticated fetch.

- Temp leak: exceptions leave large files. Use finally/context cleanup and recovery sweeps when needed.

- Inline active content: user HTML/SVG served under trusted origin executes. Use safe disposition/origin/content policy.

## Verification

- Test traversal variants, absolute paths, encoded separators and symlink escape relevant to the platform.

- Test maximum and just-over-maximum byte/count/dimension/archive expansion limits.

- Feed malformed/truncated/wrong-type files and confirm bounded safe rejection.

- Test duplicate filenames/concurrent upload and overwrite semantics.

- Interrupt/fail parsing/storage and inspect temporary/orphan cleanup plus durable status.

- Verify private file access with wrong user/tenant and expired signed URL if used.

- Inspect response headers for filename/content-type/disposition injection and active-content safety.

- Measure memory/disk behavior for representative large files using streaming path.

## Completion criteria

- Paths/keys cannot escape their intended storage boundary or collide through user-controlled naming.

- Resource limits apply before and during expensive reading/parsing/decompression.

- Content is validated for its intended use and served with safe access/header semantics.

- Large data is streamed where appropriate and temporary state is cleaned predictably.

- Private file authorization/retention is explicit.

- Adversarial file/archive and failure cleanup tests pass.

## Related skills and escalation

- Use `security` for threat model, `backend` for durable processing jobs and `external-integrations` for cloud storage APIs.

- Use `api-contracts` for upload/download wire behavior.

- Use `source-first` for parser/archive library version-sensitive security constraints.

- Escalate when active-content rendering or untrusted complex document parsing is required in a privileged environment.
