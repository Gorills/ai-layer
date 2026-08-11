---
slug: verification
description: Evidence assurance discipline separating worker-reported claims from
  host- or AI-Layer-executed verification.
kind: core
keywords:
- verify
- verification
- evidence
- command
- test
- check
- exit code
- timeout
entry_sections:
- Apply when
- Core contract
---
# Verification Skill

## Apply when
A task changes behavior, claims checks passed, reviews implementation, or decides whether work can advance.

## Core contract
- Never treat a worker statement such as “tests passed” as executed evidence.
- Preserve the assurance level of each result: reported, host-verified, or AI-Layer-verified.
- AI-Layer-verified evidence must record the command/specification, environment boundary, timestamps, exit status, timeout state, bounded output summary, and durable evidence reference.
- Verification should target acceptance criteria and affected invariants, not only implementation details.
- A failed or unavailable required check remains visible; do not convert it to success through wording or omission.

## Verification guidance
Run the narrowest falsifying check first, then the broader gate proportional to risk. Keep secret-bearing environment values and unbounded logs out of evidence.

## Failure modes
Fabricated PASS claims, losing command provenance, parsing free-form prose as authoritative status, hiding timeouts, and allowing the same fixer assertion to close its own finding.
