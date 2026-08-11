# Maintainer Bootstrap

For every new AI development chat working on this repository:

1. Read `AGENTS.md` first; it is the native repository bootstrap and publication contract.
2. Read `PROJECT_CHARTER.md`.
3. Read `ARCHITECTURE.md`.
4. Read `QUALITY_GATES.md`.
5. Read `CURRENT_STATE.md`.
6. Read relevant files in `docs/DECISIONS/`.
7. Inspect the actual source/tests/migrations for the requested change; prose is not proof of behavior.
8. Identify the current task/milestone and the owning capability before editing.
9. Keep Interfaces thin, Dashboard read-only, Domain transport/persistence independent, and Task Engine unaware of Epic internals.
10. Choose the simplest design that satisfies the current verified requirement. Prefer deletion, reuse, native host behavior and direct composition. Do not introduce speculative classifiers, routers, parallel mechanisms, state machines or generic frameworks for possible future needs; every new abstraction must solve a concrete current problem and reduce net complexity.
11. Do not weaken architecture/quality/state-machine/verification policy as part of an ordinary feature. Governance-sensitive changes require explicit rationale, ADR, tests and protected review.
12. Use focused tests while iterating and run `make fast-gate` before committing code/governance changes.
13. After the final code change, run `make preflight` before any push or PR publication. Any later code/config change invalidates that evidence and requires another preflight.
14. A missing tool, unavailable local worktree, unavailable Docker/PostgreSQL, or failing gate is a publication blocker. Do not use remote CI as the first feedback loop and do not claim a gate passed when it was not executed.

Development governance in this file is for AI Layer source development only. Do not copy it into target projects or runtime skills.
