---
slug: css
description: Maintainable responsive CSS/layout discipline that resists magic-number
  and one-viewport fixes.
kind: stack
keywords:
- css
- scss
- sass
- layout
- grid
- flex
- responsive
- style
- tailwind
- breakpoint
- spacing
- typography
entry_sections:
- Apply when
- Core contract
---
# CSS Skill

## Apply when
Layout, responsive behavior, styling architecture, design tokens, theming or visual component implementation changes.

## Core contract
- Read the project design profile first: existing variables/tokens, spacing, typography, radii, component library and styling system outrank generic preferences.
- Solve layout with document flow, Grid/Flexbox, intrinsic sizing and container constraints before absolute positioning or offset patches.
- Reuse existing tokens/classes/components instead of inventing near-duplicate colors, spacing and radii.
- Avoid magic-number accumulation, negative-margin repairs and escalating `z-index` without understanding the stacking/layout cause.
- Verify at multiple relevant viewport widths and content lengths; a desktop screenshot alone is not completion.

## Responsive layout
Design from constraints rather than device names. Components should tolerate narrower/wider containers, localization, validation messages, long names and empty states. Prefer fluid sizing (`minmax`, `clamp`, intrinsic widths) where it fits the existing browser support.

## Cascade and architecture
Respect the project's CSS Modules/BEM/Tailwind/utility/CSS-in-JS/global convention. Do not introduce a parallel styling system to solve one task. Keep specificity predictable; avoid `!important` unless the existing architecture or third-party override boundary makes it explicit and justified.

## Visual fidelity
When a reference exists, compare spacing, typography, alignment, proportions, borders, states and responsive transformations systematically. Do not chase pixel differences by scattering local offsets; correct the underlying token/layout rule.

## Performance and motion
Avoid huge unused style payloads and layout-thrashing patterns. Motion should communicate state, honor reduced-motion preferences where relevant, and not become a substitute for hierarchy.

## Verification
Inspect real rendered pages at representative desktop/tablet/mobile widths plus hover/focus/error/disabled/loading states. Use screenshot or browser comparison when the project's tooling supports it.
