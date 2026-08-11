---
slug: visual-qa
description: Render-based visual verification loop for frontend/design changes, references
  and responsive states.
kind: capability
keywords:
- visual qa
- screenshot
- browser
- responsive
- reference
- pixel
- playwright
- cypress
- visual
- design
- ui
- frontend
- layout
entry_sections:
- Apply when
- Core contract
---
# Visual QA Skill

## Apply when
A change affects visible layout, design fidelity, responsive behavior or interactive UI states.

## Core contract
- Verify the rendered application, not only component source.
- Use existing project browser/E2E tooling first (for example Playwright/Cypress) instead of introducing a second stack solely for screenshots.
- Inspect representative desktop, tablet/narrow and mobile widths relevant to the product.
- Include real states: loading, empty, error, disabled/selected, long content, focus and overlays when the changed component supports them.
- When a visual reference exists, compare structure/hierarchy/spacing/typography/components systematically and fix root layout/token causes before local nudges.

## Evidence loop
Implement -> run application -> render/capture -> inspect -> fix -> recapture. Keep screenshots/artifacts disposable unless the project intentionally tracks visual baselines. A test passing does not prove visual quality if it never renders the affected state.

## What to inspect
Alignment, spacing rhythm, content density, truncation/wrapping, overflow, contrast, visual hierarchy, icon consistency, state feedback, touch/keyboard affordances and responsive transformations.

## Completion
Record which viewports/states were actually inspected. If environment/browser tooling prevents rendering, mark visual verification unexecuted and keep claims correspondingly limited.
