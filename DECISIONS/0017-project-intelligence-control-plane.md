# ADR 0017 — Project Intelligence control plane

## Status

Accepted for 0.13.0.

## Context

The previous global workflow made AI Layer an execution harness above host coding agents. It duplicated native agent loops, made ordinary edits depend on Task navigation, and added coordination cost without verified cost-per-accepted-result evidence.

## Decision

AI Layer is an engineering control plane. Host runtimes own ordinary read/edit/search/shell/test/subagent execution. AI Layer owns Project Intelligence, durable Tasks/Epics, reviewed Knowledge/Decisions, verification evidence and observability. Strict worker/provenance/review orchestration remains available only inside explicitly managed high-assurance workflows.

Project Map navigation is separate from curated Project Knowledge and never persists source bodies. Current repository source remains authoritative.

## Consequences

- Existing Tasks, Epics, review/fix loops, findings, verification and dashboard state are preserved.
- Legacy `memory_context` remains compatibility-only and no longer controls Task/Epic navigation.
- `project_status` and `project_search` become the low-cost continuation/navigation surfaces.
- The release is versioned 0.13.0 because execution semantics change materially while preserving public project-state capabilities.

