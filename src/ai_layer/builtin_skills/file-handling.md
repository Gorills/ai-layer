---
slug: file-handling
description: Safe file upload, path, archive, and filesystem boundary discipline.
kind: capability
keywords:
- file
- upload
- download
- path
- archive
- zip
- filesystem
- traversal
- file upload
- extract
- file path
- path traversal
- attachment
- файл
- загрузк файл
- архив
- путь файла
---
# File Handling Skill

## Apply when
User-controlled files, paths, uploads/downloads, archive extraction, or filesystem writes/reads are involved.

## Mandatory rules
- Treat filenames, paths, MIME types, archive entries, and file contents as untrusted.
- Resolve paths against an allowed root and verify containment after normalization; reject traversal and unsafe symlinks.
- Bound file count, size, decompressed size, and processing time before expensive parsing.
- Generate server-side storage names when user filenames need not be authoritative.
- Keep uploaded/extracted content outside executable/template/config locations unless explicitly required and safely handled.

## Decision rules
- Extension and client MIME are hints, not proof of content type.
- Archive extraction requires per-entry containment checks and decompression-bomb limits.
- Prefer streaming for large files; do not read arbitrary uploads fully into memory by default.

## Failure modes
`../` traversal, symlink escape, zip-slip, overwrite-by-name, unbounded decompression, executable upload exposure, trusting content type, and leaking absolute server paths in errors.

## Quality gates
- Traversal/symlink/oversize negative cases are tested where relevant.
- Cleanup behavior for partial/failed processing is deterministic.
- Authorization protects private file access independently of filename knowledge.
