---
slug: verification
description: Evidence-based completion discipline that maps engineering claims to tests, static checks, runtime inspection and explicit unverified risk.
kind: core
keywords:
- verification
- evidence
- quality gate
- acceptance
- validation
- inspection
- test plan
- claim
- done
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Verification and Evidence Skill

## Apply when

Use before declaring implementation, refactor, fix, migration or review complete. Apply whenever a result could look plausible from source code while still being wrong at runtime, in a browser, against a real database, or under failure.

## Core contract

- Convert “it works” into explicit claims and attach the strongest practical evidence to each claim.

- Use the repository's canonical gates as the baseline; targeted checks supplement but do not silently replace required full verification.

- Different claims require different evidence: type/static checks prove some structure, tests prove specified behavior, runtime inspection proves integration, visual inspection proves appearance.

- Never report a check as passed unless it was actually executed in the relevant environment and its exit/result is known.

- Distinguish not-run, blocked, failed and passed. An unavailable tool is not a pass and should leave the associated claim explicitly unverified.

- Verify negative and failure behavior for high-impact changes, not only the successful path.

- Inspect the final diff/state after automated checks: accidental files, debug code, stale generated artifacts and unrelated modifications are common completion failures.

- For compatibility and migrations, test representative old state or mixed versions; clean-slate tests do not prove upgrade safety.

- For security-sensitive work, include adversarial evidence; for UI, include real render evidence; for performance, include measurement rather than intuition.

- Preserve concise provenance: command/tool, scope/environment and outcome so another reviewer can reproduce the evidence.

## Evidence to inspect

- Acceptance criteria and stated implementation claims.

- Canonical quality commands from Makefile/package scripts/CI configuration.

- Targeted tests/static analyzers relevant to changed files and risk.

- Runtime logs, API responses, database state, screenshots or traces where they directly prove a claim.

- Git diff/status and generated/build artifact freshness.

- Known unavailable environments or external dependencies that limit verification.

## Decision rules

- If a claim is purely structural and statically enforceable, use a deterministic static gate rather than a brittle runtime test.

- If a claim concerns integration semantics, run through the real boundary rather than only mocking it.

- If a claim concerns pixels/layout, inspect rendered output at relevant states/viewports; source review is insufficient.

- If a migration must support existing data, create representative pre-migration state and run the upgrade path.

- If a failure cannot be induced safely in production, reproduce it in a test/staging harness and state the environmental difference.

- If canonical CI and local checks disagree, investigate environment/configuration drift instead of choosing the favorable result.

- If an external dependency prevents verification, report the exact blocked claim and do not broaden the limitation to unrelated verified claims.

- If the final diff includes generated artifacts, verify they are reproducible from the checked-in sources.

## Workflow

1. List the important claims introduced by the change and rank them by consequence of being wrong.

2. Map each claim to a verification method and environment before finishing implementation.

3. Run fast targeted checks while iterating and capture failures as signals, not obstacles to bypass.

4. Run integration/runtime/visual/adversarial checks for claims that static or unit tests cannot establish.

5. Run the repository's canonical quality gate from a clean-enough state matching CI as closely as practical.

6. Inspect final diff/status and rerun checks affected by any late edits.

7. Summarize evidence as passed/failed/blocked/not-run with scope; keep unsupported claims out of the completion statement.

8. When handing off, include exact residual risk and the next concrete verification action if something remains blocked.

## Implementation patterns

- A claim-evidence matrix keeps verification proportional: claim, risk, evidence, environment and outcome.

- Use targeted commands for quick iteration, then canonical aggregate commands to catch interactions and packaging/governance checks.

- For bugs, combine regression reproduction with a post-fix run and, when practical, a negative control showing the test would catch reintroduction.

- For stateful systems, verify both returned output and authoritative persisted state/side effects.

- For async systems, verify eventual outcome plus duplicate/retry behavior, not just that a message was enqueued.

- For APIs, verify status/schema/error semantics and side effects; for CLIs, include exit code and stderr/stdout contract.

- For UI, preserve screenshots at representative widths/states only when the project workflow supports them; visual assertions should focus on meaningful invariants.

- For releases, include artifact integrity/reproducibility and installation/smoke evidence when the repository treats artifacts as canonical.

## Failure modes

- Plausibility proof: code “looks correct” and no executable evidence exists. Run the relevant boundary.

- Targeted-only confidence: one unit test passes while canonical lint/type/package gates are skipped. Run the project gate.

- False pass: a command was unavailable or timed out but is summarized as successful. Mark blocked/not-run.

- Green-test masking: tests mock the component that changed or never assert the important side effect. Strengthen the evidence.

- Clean-install bias: migrations/upgrades are tested only from empty state. Reproduce representative old data/version.

- Late-edit invalidation: checks ran before the final code change. Rerun checks whose evidence is now stale.

- Environment drift: local success uses different versions/configuration than CI/production. Record and align the environment.

- Unbounded verification dump: thousands of log lines obscure result. Retain concise outcome and only the diagnostic slice needed for failures.

## Verification

- Confirm every completion statement can point to an executed check or is explicitly labeled as inference/limitation.

- Confirm canonical repository gates were run or clearly explain why they could not be run.

- Confirm high-risk negative/failure cases were exercised and did not merely share the success setup.

- Confirm final source/generated artifact state matches what was tested.

- Confirm environment-sensitive claims name the actual environment/version used.

- Confirm no failing or skipped check was silently omitted from the summary.

- Confirm residual risks have a concrete owner/action rather than vague “needs testing later”.

- Confirm evidence is reproducible without private scratch state known only to the current agent.

## Completion criteria

- The change has a concise claim-to-evidence record covering all material acceptance criteria.

- Canonical quality checks pass in the available supported environment, or blocked stages are explicit.

- Runtime/visual/integration claims have corresponding runtime/visual/integration evidence.

- Failure and compatibility paths are verified where they are material.

- The final diff/artifacts are the ones actually verified.

- No unsupported claim of pixel-perfect, production-safe, secure or fully tested remains in the handoff.

## Related skills and escalation

- Use `testing` for construction of the automated test evidence.

- Use `visual-qa`, `security`, `web-performance` and migration skills for specialized evidence.

- Use `source-first` when verification depends on version-specific external behavior.

- Escalate when a critical claim cannot be verified in any available representative environment.
