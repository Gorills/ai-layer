---
slug: documentation
description: Durable technical documentation discipline for contracts, architecture, operations and decisions that stays evidence-based and maintainable.
kind: core
keywords:
- documentation
- readme
- adr
- runbook
- docs
- architecture docs
- api docs
- decision record
- maintenance
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Engineering Documentation Skill

## Apply when

Use when behavior, setup, public contract, architecture, operations or a consequential engineering decision changes and future maintainers/users need durable guidance. Do not use docs to compensate for unclear code or to claim unimplemented behavior.

## Core contract

- Document facts the repository/runtime can support; documentation is not evidence that a feature exists or works.

- Choose the document closest to the consumer: README for entry/setup, API docs for contracts, ADR for consequential choices, runbook for operations/recovery, comments for non-obvious local constraints.

- Explain why a constraint exists when future maintainers might otherwise “simplify” it incorrectly; avoid narrating obvious syntax.

- Keep one canonical source for each fact and link/reference it rather than duplicating version numbers, commands or architecture descriptions across many files.

- Commands and configuration examples must be executable/current for the repository version; verify them when changing them.

- Document failure/recovery and limitations for operationally important features, not only the happy path.

- Separate normative contract from tutorial/example. Readers must know what is guaranteed versus illustrative.

- Remove or update stale material in the same change; adding another contradictory paragraph makes documentation worse.

- Avoid AI/process provenance in product repositories when project policy forbids it; document the engineering result, not how it was generated.

- Prefer concise structured sections, tables and examples where they reduce ambiguity; depth should serve decisions, not word count.

## Evidence to inspect

- Current implementation, tests, CLI/API help and configuration defaults.

- Existing canonical documentation map and links from README/user/operator entry points.

- Deployment/install scripts and real commands used by CI/operators.

- Architecture decisions or invariants encoded in code/tests.

- Historical docs that may now contradict the changed behavior.

- Audience: contributor, integrator, operator, user or future architect.

## Decision rules

- If the fact is a public behavior guarantee, put it with the public contract rather than only in an internal comment.

- If a design choice is costly to reverse and alternatives were considered, capture an ADR-style decision with context/consequences.

- If recovery requires commands/manual decisions under incident pressure, create/update a runbook with prerequisites, verification and rollback.

- If a code comment would repeat the code, omit it; comment only non-obvious invariant, workaround source or hazard.

- If the same setup/version instruction appears in several places, make one canonical and link others.

- If documentation describes planned work, label it explicitly as proposal/roadmap rather than present behavior.

- If a command example is changed, execute it or derive it from a tested source before publishing.

- If behavior is version-sensitive external technology, link to authoritative docs and state the project-specific constraint rather than copying large vendor manuals.

## Workflow

1. Identify which user/maintainer decision becomes ambiguous after the code change.

2. Locate the existing canonical document for that audience/topic and search for stale/conflicting statements.

3. Verify implementation facts against code/tests/runtime before writing.

4. Update the smallest canonical section with contract, rationale, examples and failure/recovery information appropriate to the audience.

5. Update inbound links/indexes/help text only as needed to make the canonical content discoverable.

6. Run doc linters/builders and execute commands/examples that can be verified.

7. Review diff for duplicated facts, speculative claims and internal development-process leakage.

8. Delete or redirect superseded documentation so future search does not surface two truths.

## Implementation patterns

- README: purpose, supported setup, minimal quick start, key commands and links—not a full internal architecture dump.

- ADR: context/problem, decision, alternatives, consequences and status; keep it factual and tied to an actual decision.

- Runbook: symptom/trigger, safety preconditions, diagnostic checks, action, verification, rollback/escalation.

- API contract docs: request/response/errors/auth/idempotency/examples plus version/deprecation notes.

- Migration notes: who is affected, required order, compatibility window and data/rollback caveats.

- Code comments: explain invariant or why a strange workaround must exist; cite issue/upstream fact when it prevents regression.

- Diagrams: show ownership/flow that text cannot communicate efficiently; keep labels aligned with code names.

- Examples: realistic but nonsecret values, deterministic expected output and explicit placeholders.

## Failure modes

- Docs-as-proof: README claims feature works despite missing/broken code. Treat implementation/tests as source of truth.

- Duplicate truth: version/setup copied across many docs drifts. Centralize.

- Comment narration: every line gets prose and important invariants disappear in noise. Remove obvious comments.

- Happy-path runbook: incident docs omit failure verification/rollback. Add operational checkpoints.

- Stale command: copied example no longer runs. Execute/update it.

- Proposal phrased as reality: future architecture confuses audits. Label status clearly.

- Vendor-doc copy: large pasted sections become outdated. Link primary docs and keep local implications only.

- AI provenance leakage: internal agent/tool language appears in product docs contrary to policy. Document product facts only.

## Verification

- Cross-check every changed normative statement against current code, tests or configuration.

- Run documented commands/examples where the environment permits and capture failures before merge.

- Run documentation build/link/lint checks configured by the project.

- Search repository for old terminology/version/command that should have been replaced.

- Verify setup/runbook steps include prerequisites and safe rollback/recovery where relevant.

- Check links point to canonical/current locations and do not create circular duplication.

- Read as the target audience with no hidden conversation context; required assumptions must be stated.

- Ensure no secret/internal path/private credential or disallowed agent-development provenance entered docs.

## Completion criteria

- Changed behavior/architecture/operations have one discoverable canonical explanation for the right audience.

- Documentation claims match implemented and verified behavior.

- Examples/commands are executable or explicitly illustrative.

- Stale/contradictory copies were removed or redirected.

- Consequential decisions and recovery constraints preserve the rationale future maintainers need.

- No unnecessary internal process/provenance or sensitive data is exposed.

## Related skills and escalation

- Use `api-contracts`, `architecture` and migration skills for the underlying contract/decision substance.

- Use `verification` to prove documented commands and behavior.

- Use `source-first` when external version details are required.

- Escalate when documentation would need to assert behavior that cannot be verified from the repository/runtime.
