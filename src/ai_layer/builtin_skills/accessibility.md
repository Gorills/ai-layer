---
slug: accessibility
description: Practical WCAG-oriented web accessibility for semantics, keyboard, focus,
  forms, contrast and dynamic UI.
kind: capability
keywords:
- accessibility
- a11y
- wcag
- keyboard
- focus
- aria
- contrast
- screen reader
- form
- modal
- dialog
- menu
- button
entry_sections:
- Apply when
- Core contract
---
# Accessibility Skill

## Apply when
Interactive web UI, forms, navigation, dialogs, visual states, content structure or custom widgets change.

## Core contract
- Prefer native HTML semantics before ARIA. ARIA changes accessibility exposure; it does not automatically implement keyboard behavior, focus management or state.
- Every interaction must be usable by keyboard with visible focus and a predictable focus order.
- Inputs need programmatic labels and errors/instructions associated with the relevant control.
- Do not encode state or meaning by color alone; preserve adequate text/control contrast under the project's accessibility target.
- Dynamic overlays/dialogs must manage focus intentionally and return it sensibly when closed.

## Custom widgets
Use established accessible patterns for tabs, menus, comboboxes, dialogs and similar widgets. Do not invent partial keyboard conventions. Keep roles, names, states and relationships synchronized with actual behavior.

## Responsive and zoom behavior
Do not create layouts that require horizontal scrolling for ordinary content at narrow widths unless the content itself (for example a data table) genuinely requires it. Avoid fixed dimensions that break with text scaling/localization.

## Verification
At minimum verify keyboard-only operation, visible focus, labels/errors, semantic roles/names and major contrast/state issues. Use the project's automated accessibility tooling where available, but do not treat an automated scan as proof of complete accessibility.
