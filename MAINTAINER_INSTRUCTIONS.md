# Maintainer Bootstrap

For every new AI development chat working on this repository:

1. Read `PROJECT_CHARTER.md`.
2. Read `ARCHITECTURE.md`.
3. Read `QUALITY_GATES.md`.
4. Read `CURRENT_STATE.md`.
5. Read relevant files in `docs/DECISIONS/`.
6. Inspect the actual source/tests/migrations for the requested change; prose is not proof of behavior.
7. Identify the current task/milestone and the owning capability before editing.
8. Keep Interfaces thin, Dashboard read-only, Domain transport/persistence independent, and Task Engine unaware of Epic internals.
9. Choose the simplest design that satisfies the current verified requirement. Prefer deletion, reuse, native host behavior and direct composition. Do not introduce speculative classifiers, routers, parallel mechanisms, state machines or generic frameworks for possible future needs; every new abstraction must solve a concrete current problem and reduce net complexity.
10. Do not weaken architecture/quality/state-machine/verification policy as part of an ordinary feature. Governance-sensitive changes require explicit rationale, ADR, tests and protected review.
11. Run `python scripts/quality_gate.py --deterministic-wheel` before release. A missing tool or unsupported environment is a failure, not permission to bypass the gate.

Development governance in this file is for AI Layer source development only. Do not copy it into target projects or runtime skills.
