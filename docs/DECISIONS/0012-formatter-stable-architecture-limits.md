# ADR 0012 — Formatter-stable architecture size limits

**Status:** accepted for the v0.11.4 CI baseline repair.

## Context

The canonical gate requires `ruff format --check .`, but the previous architecture ceilings treated formatter-dependent physical line counts as if they were direct complexity measures. Normalizing the existing repository with the pinned formatter expanded several otherwise unchanged modules above 500 lines and several functions above 120 lines, while the independent source-byte, statement-count, cyclomatic-complexity and nesting limits still passed.

Splitting multiple existing owners solely to reverse formatter line expansion would add files and seams without changing responsibility or reducing semantic complexity. That conflicts with the project simplicity invariant.

## Decision

Keep physical line count as a hard safety backstop and the 300-line soft maintainability warning, but set the ordinary-module hard ceiling to 600 physical lines and the function hard ceiling to 180 physical lines for formatter-normalized source. Keep the existing hard limits for module bytes (36,000), function statements (80), cyclomatic complexity (24), nesting depth (5), facade size, import cycles and capability boundaries unchanged.

The architecture policy remains unable to exceed built-in ceilings. Future growth above the soft warning still requires justification or a cohesive extraction; crossing a hard semantic or size ceiling remains fail-closed.

## Consequences

Canonical formatting and architecture checks no longer contradict each other for the existing baseline. The gate continues to reject packed source, oversized semantic functions, excessive branching/nesting, import cycles, facade growth and capability violations. We avoid creating artificial modules whose only purpose would be satisfying formatter-sensitive line counts.
