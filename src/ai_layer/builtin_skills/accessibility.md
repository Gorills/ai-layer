---
slug: accessibility
description: Accessible interface engineering for semantic structure, keyboard use, focus, forms, contrast, dynamic content and assistive-technology behavior.
kind: capability
keywords:
- accessibility
- a11y
- wcag
- aria
- keyboard
- focus
- screen reader
- contrast
- forms
- semantic html
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Web Accessibility Skill

## Apply when

Use for any visible or interactive web UI, especially forms, navigation, dialogs, menus, tables, custom controls, live updates and redesigns. Apply during component design rather than as a final audit, because semantic structure and interaction models are expensive to retrofit.

## Core contract

- Prefer native semantic HTML and controls before ARIA. Native elements bring keyboard, focus and accessibility semantics that custom div-based controls must otherwise recreate correctly.

- Every operation available by pointer should be operable by keyboard unless the interaction is inherently path-dependent; visible focus must remain discoverable.

- Name, role, value/state and relationships must be programmatically determinable for interactive controls and important content structure.

- Do not encode meaning only in color, position, icon shape or animation. Provide text/semantic equivalents and sufficient contrast for the project's target standard.

- Focus management is part of component behavior: opening/closing dialogs, validation errors, route changes and dynamic insertion must not strand or steal focus unexpectedly.

- Forms need persistent labels, instructions tied to controls, field-level error association and a clear error summary/next action for complex submissions.

- Dynamic content should announce material changes intentionally; do not turn whole pages into noisy live regions.

- Responsive/reflow behavior must preserve reading and focus order. CSS visual reordering must not create a different logical interaction sequence.

- Support user preferences such as reduced motion where motion is nonessential, and avoid animation that blocks understanding or control.

- Test with keyboard and accessibility tooling, then manually inspect critical flows; automated scanners cannot validate interaction intent or announcement quality.

## Evidence to inspect

- Rendered DOM/semantic tree, heading landmarks, form associations and interactive element types.

- Keyboard tab order, focus indicator, focus trapping/restoration and skip/navigation behavior.

- Computed color contrast, zoom/reflow behavior and high-density/long-content states.

- ARIA attributes, accessible names/descriptions and live-region usage.

- Validation/error UI, disabled/loading state semantics and asynchronous updates.

- Existing accessibility standard or product requirement, plus the current W3C WCAG version when conformance details matter.

## Decision rules

- If a native element can express the control, use it instead of recreating behavior with `div`/`span` plus ARIA.

- If visual order differs from DOM order, change source/layout structure when interaction order matters rather than relying on CSS `order` alone.

- If an icon-only action exists, provide an accessible name that describes the action, not the icon artwork.

- If a dialog opens, move focus to an appropriate element, keep keyboard navigation within modal scope when truly modal, and restore focus logically on close.

- If validation fails, associate each message with its field and move/announce focus in a way that lets the user find errors efficiently.

- If content updates without navigation, announce only changes users must know to continue; avoid broad `aria-live` regions that repeat irrelevant content.

- If a control is visually disabled but still focusable/actionable, decide whether disabled or aria-disabled semantics are correct and make behavior consistent.

- If drag-and-drop is essential, provide an alternative operable method for users who cannot perform precise pointer gestures.

## Workflow

1. Identify user journeys and custom interactions most likely to fail for keyboard or assistive-technology users.

2. Inspect the existing semantic/component system before introducing accessibility wrappers or duplicate semantics.

3. Choose native element patterns and logical DOM structure before styling.

4. Implement accessible names, relationships, states, error semantics and focus behavior alongside component states.

5. Verify keyboard-only navigation end-to-end, including escape/cancel, modal boundaries, menus and form errors.

6. Run automated accessibility checks and fix deterministic semantic/contrast violations.

7. Inspect the accessibility tree or use a screen reader for critical custom/dynamic interactions.

8. Re-test at zoom/reflow and responsive breakpoints with realistic long text and localization-like expansion.

## Implementation patterns

- Use `<button>` for actions and `<a href>` for navigation; avoid click handlers on inert elements unless implementing the full equivalent interaction.

- Use real `<label>` association or an equally strong accessible naming mechanism; placeholder text is not a stable label.

- For data tables, preserve table semantics and correct header scope/relationships; do not replace them with generic grids solely for styling.

- For disclosure/accordion, expose expanded state and control relationship; keep behavior predictable and keyboard-native where possible.

- For tabs, use a coherent tabs pattern only when content behaves as one composite widget; ordinary navigation links may be simpler and more robust.

- For status/loading, keep the triggering control's state understandable and announce completion/error only when it changes the user's next action.

- For decorative icons/images, omit them from the accessibility tree; meaningful imagery needs equivalent text appropriate to context.

- For validation, retain user input, identify invalid fields and explain how to correct errors without relying on color alone.

## Failure modes

- ARIA-first recreation: a custom element duplicates a native button/select badly. Replace with native semantics unless a real interaction requirement prevents it.

- Positive tabindex maze: manual numbers attempt to repair DOM order and become unmaintainable. Fix DOM/focus sequence instead.

- Focus disappearance: dialog closes and focus jumps to document start or removed node. Restore to the logical trigger/next control.

- Invisible keyboard focus: outline removed for aesthetics. Provide a strong intentional focus-visible treatment.

- Label-by-placeholder: field loses its only label when populated. Add persistent programmatic/visible labeling.

- Noisy live region: every render announces large content blocks. Restrict announcements to concise material status changes.

- Color-only status: success/error/selected state relies on hue. Add text/icon semantics and programmatic state.

- Responsive semantic inversion: CSS changes visual order but keyboard/screen-reader order remains confusing. Rework structural order.

## Verification

- Navigate the primary flow using only keyboard, including all interactive controls and escape/cancel paths.

- Verify visible focus never becomes hidden behind sticky elements or removed without a clear destination.

- Inspect accessible names, roles and states for custom components in browser accessibility tooling.

- Run the project's automated a11y scanner/test suite and review rather than blindly suppress findings.

- Check contrast and non-color cues for text, controls, focus and status indicators at relevant states.

- Test form submission with missing/invalid input and confirm errors are discoverable and associated.

- Test at high zoom/narrow reflow and with long text to detect clipping, overlap and order problems.

- For critical custom widgets, perform at least one manual screen-reader pass or explicitly report it as unexecuted.

## Completion criteria

- Primary journeys are fully keyboard-operable with logical focus order and visible focus.

- Interactive controls expose correct semantics, names, relationships and states.

- Forms and errors remain understandable without placeholder, color or pointer dependence.

- Responsive and dynamic behavior preserves reading/focus order and communicates material updates.

- Automated checks pass for the relevant scope and critical interactions have manual evidence.

- Any accessibility behavior not manually verified is explicitly identified rather than assumed.

## Related skills and escalation

- Use `html` for deeper semantic markup, `css` for focus/reflow/contrast implementation, and `design` for visual hierarchy.

- Use `visual-qa` to inspect zoom, focus, error and responsive states in rendered UI.

- Use `source-first` for exact WCAG success criteria or framework accessibility APIs; consult current W3C/framework documentation.

- Escalate when a custom interaction lacks a clear accessible interaction model instead of inventing semantics.
