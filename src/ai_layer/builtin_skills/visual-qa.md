---
slug: visual-qa
description: Rendered UI verification for reference fidelity, responsive layouts, states, typography, overflow, accessibility cues and regression evidence.
kind: capability
keywords:
- visual qa
- screenshot
- render
- pixel
- responsive
- reference
- layout
- overflow
- browser
- regression
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Visual QA Skill

## Apply when

Use whenever a task claims a UI is visually correct, reference-matched, responsive, polished or pixel-accurate. Apply after implementation and after late CSS/token changes; source review cannot establish visual correctness.

## Core contract

- Render the actual implementation in the target environment. HTML/CSS/component source is not evidence that layout, fonts or states appear correctly.

- Compare at controlled viewport, zoom, theme and data state; mismatched capture conditions produce false visual conclusions.

- Fix errors from large to small: page/container geometry → grid/alignment → typography → component anatomy → color/elevation → fine spacing.

- Test representative states, not only the ideal populated screenshot: loading, empty, error, selected, focus, disabled and long content.

- Responsive QA requires materially different layouts and viewport heights; do not verify one desktop screenshot then infer mobile.

- Reference fidelity is systematic comparison, not subjective memory. Record the most important mismatches and iterate.

- Automated screenshot diffs are useful for regression but need thresholds/masks/review; they cannot judge whether the design itself is good.

- Inspect clipping, overflow, scroll containers, sticky elements and z-index interactions that often appear only at runtime.

- Verify focus indicators, error states and contrast visually alongside semantic accessibility checks.

- If rendering/browser tooling is unavailable, explicitly label visual QA as unexecuted and do not claim pixel fidelity.

## Evidence to inspect

- Target reference/image/design dimensions and known viewport/device assumptions.

- Live rendered page/component in the actual browser/runtime with loaded fonts/assets.

- Screenshots at fixed viewport and data/state combinations.

- Computed styles/layout boxes when a mismatch is hard to localize.

- Visual regression baseline/diff if the project has one.

- Accessibility tree/focus order and browser console/network for asset/font failures.

## Decision rules

- If the whole page feels offset, measure container/viewport/header/grid before changing child margins.

- If many text elements differ, verify font loading, base size/line-height/weight mapping before local typography overrides.

- If only long/real data breaks layout, fix content constraints/structure rather than hiding overflow globally.

- If a screenshot diff changes because of animation/time/random data, stabilize those inputs instead of raising thresholds until it passes.

- If reference uses unavailable proprietary assets/font, choose/declare the substitution and judge layout with its actual metrics.

- If mobile simply stacks but important actions become buried, return to responsive design rather than accepting a technically non-overflowing screenshot.

- If visual regression is intentional, update baseline only after human/requirement review confirms the new appearance.

- If a mismatch is systemic, fix the token/component source and recapture all affected states.

## Workflow

1. Define the visual matrix: routes/components, viewport sizes, theme, data fixtures and interaction states.

2. Render baseline/current implementation under controlled conditions and confirm fonts/assets finished loading.

3. Compare against reference/requirements and list highest-impact mismatches by geometry/hierarchy/state.

4. Fix systemic layout/tokens first; recapture rather than stacking compensating CSS.

5. Inspect component states, long content, empty/error/loading and keyboard focus.

6. Inspect small-screen and short-height behavior including sticky/fixed/scroll interactions.

7. Run automated screenshot regression if configured and manually review meaningful diffs.

8. Perform a final capture after all changes and report exact states/viewports executed.

## Implementation patterns

- Use stable fixtures and deterministic clocks/animations for screenshot tests.

- Capture full page plus focused component crops when large pages make small regressions difficult to review.

- Overlay/difference images are effective for reference matching once capture dimensions align.

- Measure bounding boxes/computed typography for persistent mismatch instead of guessing pixels.

- Keep visual baselines versioned only for stable components/routes; avoid thousands of low-value screenshots.

- Disable caret/blinking/transition noise in automated capture while preserving production behavior outside test mode.

- Use representative long strings, many rows and no-data fixtures as named visual cases.

- For browser UI, wait on a semantic readiness condition rather than arbitrary sleep before capture.

## Failure modes

- Source-only confidence: CSS looks right, but font/assets/layout differ at runtime. Render it.

- One-viewport proof: desktop passes while mobile overflows. Define viewport matrix.

- Baseline rubber stamp: every diff is accepted by updating screenshots. Review intent first.

- Pixel whack-a-mole: child offsets hide a wrong grid/token. Fix structural cause.

- Ideal-data bias: one short row hides truncation/wrap bugs. Use realistic fixtures.

- Animation flake: unstable screenshots cause threshold inflation. Freeze/stabilize nondeterminism.

- Font fallback: capture occurs before webfont load and alignment is judged incorrectly. Wait/verify fonts.

- Hidden focus defect: visual QA never keyboards into controls. Include focus/error/selected states.

## Verification

- Capture/reference compare at each materially different responsive layout.

- Inspect page/container dimensions, shared alignment lines and typography metrics for fidelity-sensitive work.

- Exercise long content, empty, loading, error, selected, disabled and focus states applicable to the feature.

- Check horizontal/vertical overflow and scroll ownership at narrow/short viewports.

- Verify font/icon/image assets load without console/network errors.

- Run configured visual regression tests and manually inspect diff images rather than only exit code.

- Cross-check accessibility focus/contrast cues in rendered state.

- Record exact viewport/state coverage and explicitly list any unexecuted visual checks.

## Completion criteria

- Visual claims are backed by real render evidence at relevant viewports/states.

- Systemic reference mismatches were corrected at shared structure/tokens rather than patched locally.

- Long/empty/loading/error/focus behavior is visually coherent.

- No unintended clipping/overflow/z-index/sticky issue remains in tested matrix.

- Automated visual baselines, if used, changed only with intentional review.

- Unexecuted environments/states are reported without pixel-perfect claims.

## Related skills and escalation

- Use `design` to decide what the interface should be and `frontend`/`css` to implement fixes.

- Use `accessibility` for semantic/keyboard validation beyond appearance.

- Use `testing` for stable screenshot harness construction.

- Escalate when reference assets/viewport/expected state are fundamentally ambiguous.
