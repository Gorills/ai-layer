# Maintainer Bootstrap

For every new AI development chat working on this repository:

1. Read `AGENTS.md` first; it is the native repository bootstrap and publication contract.
2. Read `PROJECT_CHARTER.md`.
3. Read `PRODUCT_GOAL.md` for the current target outcome and `ROADMAP.md` for sequencing.
4. Read `ARCHITECTURE.md`.
5. Read `QUALITY_GATES.md`.
6. Read `CURRENT_STATE.md` to distinguish implemented behavior from the target goal.
7. Read relevant files in `DECISIONS/`.
8. Inspect the actual source/tests/migrations for the requested change; prose is not proof of behavior.
9. Identify the current task/milestone and the owning capability before editing.
10. Keep Interfaces thin, Dashboard read-only, Domain transport/persistence independent, and Task Engine unaware of Epic internals.
11. Choose the simplest design that satisfies the current verified requirement. Prefer deletion, reuse, native host behavior and direct composition. Do not introduce speculative classifiers, routers, parallel mechanisms, state machines or generic frameworks for possible future needs; every new abstraction must solve a concrete current problem and reduce net complexity.
12. Do not weaken architecture/quality/state-machine/verification policy as part of an ordinary feature. Governance-sensitive changes require explicit rationale, ADR, tests and protected review.
13. Follow the local verification contract in `QUALITY_GATES.md`: initialize the checkout `.venv` with `make dev-setup`, use the documented gate owner for each claim, and never delete another checkout's Docker resources to resolve a conflict.
14. Use focused tests while iterating and run `make fast-gate` before committing code/governance changes.
15. After the final code change, run `make preflight` before any push or PR publication. Any later code/config change invalidates that evidence and requires another preflight.
16. A missing tool, unavailable local worktree, unavailable Docker/PostgreSQL, or failing gate is a publication blocker. Do not use remote CI as the first feedback loop and do not claim a gate passed when it was not executed.
17. End every completed-work response with a concrete **What next** recommendation. When substantive work leaves real next steps or continuation is expected, also provide a ready-to-copy, self-contained **Prompt for the next chat**; do not skip it merely because the current slice is done or the next action is optional. The prompt must require inspection of current source and Git state instead of treating handoff prose as code truth. If no follow-up is appropriate, say so explicitly; an optional audit/publication/next-objective prompt is allowed but not required.

Development governance in this file is for AI Layer source development only. Do not copy it into target projects or runtime skills.
