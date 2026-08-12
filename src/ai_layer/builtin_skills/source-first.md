---
slug: source-first
description: Version-aware research discipline for resolving uncertain technical behavior from repository evidence and authoritative primary documentation.
kind: core
keywords:
- source first
- official docs
- version
- documentation
- specification
- research
- evidence
- uncertainty
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Source-First Engineering Skill

## Apply when

Use whenever implementation depends on framework/library/platform behavior that is version-sensitive, obscure, recently changed or not confidently known. Also use when repository code and documentation disagree, or when an agent is tempted to invent an option, API or configuration key from memory.

## Core contract

- Repository evidence comes first for what this project actually uses: lockfiles, imports, configuration, wrappers, tests and deployed versions.

- For external behavior, prefer authoritative primary sources: official documentation/specification, upstream source, release notes and migration guides.

- Match documentation to the detected version. Current docs can be wrong for a pinned old dependency, and old blog posts can be wrong for current code.

- Separate observed facts, source-backed facts and inference. Do not upgrade an inference into a claim because it sounds conventional.

- Search for the narrow behavior needed to make the decision; do not flood context with an entire manual.

- When official docs are ambiguous, inspect upstream tests/source or build a minimal executable reproduction.

- Preserve existing project conventions unless authoritative evidence proves they are invalid or the task explicitly changes them.

- Never invent configuration names, CLI flags, lifecycle hooks, security guarantees or compatibility behavior.

- If sources conflict, state the conflict, identify version/context differences and choose based on the project's actual environment.

- Capture the decisive source/experiment in concise form so future agents can verify the same assumption.

## Evidence to inspect

- Dependency and tool versions from lockfiles, manifests, generated lock data and runtime `--version` output.

- Existing wrapper code, adapters and tests that demonstrate how the project currently invokes the dependency.

- Official versioned documentation, API references, specifications, release notes and migration guides.

- Upstream source/tests for behavior not clearly documented.

- Minimal isolated reproduction using the project's exact dependency version where practical.

- Commit/history evidence when a local convention might be compatibility debt rather than current best practice.

## Decision rules

- If version is not known and the behavior changed across releases, detect the version before recommending code.

- If official docs show several supported patterns, select the one consistent with the repository architecture and explain the deciding constraint.

- If a blog/StackOverflow answer conflicts with primary documentation, treat it as a lead, not authority.

- If the upstream API is underspecified, reproduce it locally or inspect source/tests before encoding an assumption.

- If a feature requires an upgrade, make the upgrade an explicit scope/compatibility decision rather than silently coding against newer APIs.

- If local code intentionally wraps an external API, respect the wrapper boundary and avoid spreading direct vendor calls.

- If a source states a default, verify local configuration does not override it before relying on the default.

- If no reliable evidence can resolve a high-impact question, stop the risky assumption and surface the uncertainty.

## Workflow

1. State the exact technical question in one sentence, including the behavior that affects implementation.

2. Detect the project's relevant version, configuration and existing usage before searching external material.

3. Read the narrow official page/spec/release note for that version and extract only the decisive constraints.

4. Cross-check against repository code/tests; investigate mismatches instead of assuming either side is automatically right.

5. If ambiguity remains, inspect upstream source/tests or construct a minimal reproduction with the exact version.

6. Make the implementation decision and record which fact/source/experiment supports it.

7. Implement through existing project abstractions and add a regression/contract test for behavior likely to regress across upgrades.

8. If the fact is upgrade-sensitive, leave a durable note/test at the boundary rather than copying a transient explanation everywhere.

## Implementation patterns

- Version detection should use lock/resolution data when possible; broad manifest ranges do not prove the installed version.

- Official migration guides are particularly valuable when behavior appears to contradict memory from another major version.

- Specifications outrank framework examples for protocol semantics, while framework docs govern the framework's supported API.

- Upstream tests often reveal edge semantics such as cancellation, encoding or exception mapping more reliably than tutorial prose.

- A minimal reproduction should eliminate application-specific layers until only the disputed external behavior remains.

- When citing source-backed behavior in code comments, explain why the constraint matters rather than pasting documentation.

- Pinning a workaround to a detected version plus a removal test is safer than an unconditional compatibility hack.

- Treat generated AI search summaries as navigation aids; verify decisive details at the primary source.

## Failure modes

- Memory-driven API: an agent writes a plausible method/flag that does not exist in the pinned version. Detect version and consult primary docs.

- Latest-doc drift: implementation follows current docs while project is pinned to an older major. Use versioned docs/migration notes.

- Cargo-cult workaround: old local code is copied without checking whether the upstream issue was fixed. Trace history/version.

- Blog authority: secondary content becomes the only basis for a security/compatibility decision. Verify with primary sources.

- Context flooding: an entire documentation page is pasted into working context. Retrieve only the relevant section/fact.

- Inference laundering: “probably”, “usually” disappears from the final claim. Label inference or test it.

- Local-default assumption: official default is quoted while project overrides it. Inspect runtime/project config.

- Research without a decision: many links are collected but no implementation constraint is extracted. Return to the exact technical question.

## Verification

- Confirm dependency/platform version from repository or runtime evidence.

- Confirm every version-sensitive implementation choice has primary-source or executable evidence.

- Confirm the referenced source applies to the exact major/minor context that matters.

- Confirm local wrappers/configuration do not change the documented default behavior.

- Run a focused test/reproduction for any behavior whose ambiguity could cause a material defect.

- Add or update a regression/contract test when future dependency upgrades could silently change the assumption.

- Remove exploratory code/files and summarize the decisive evidence rather than the research transcript.

- If uncertainty remains, explicitly mark the affected claim and avoid presenting it as resolved.

## Completion criteria

- The implementation no longer depends on an unverified version-sensitive assumption.

- Decisive facts are grounded in repository evidence plus authoritative external evidence where needed.

- Documentation/version context matches the project's actual dependency or planned upgrade.

- Conflicts or residual uncertainty are explicit and do not hide behind confident wording.

- A durable test or boundary note protects material assumptions likely to change with upgrades.

## Related skills and escalation

- Use this skill alongside any framework/stack skill when API behavior could have changed.

- Use `compatibility` for upgrade/mixed-version planning and `verification` for executable evidence.

- Use `security` when the disputed behavior affects security guarantees.

- Escalate when no authoritative source or representative runtime can resolve a high-impact decision.
