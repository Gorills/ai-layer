---
slug: design
description: Constraint-driven UI/UX design discipline for weak models using observed
  design systems, hierarchy, composition and explicit anti-patterns.
kind: capability
keywords:
- design
- ui
- ux
- layout
- visual
- typography
- spacing
- design system
- pixel perfect
- ui design
- redesign
- reference
- макет
- дизайн
- интерфейс
- визуал
entry_sections:
- Apply when
- Core contract
---
# UI/UX Design Skill

## Apply when
The task creates/redesigns visible UI, translates a reference into code, or extends an existing product's visual language.

## Core contract
- Start from scanner evidence: fonts, tokens, colors, spacing, radii, component library and existing screens. Existing product grammar outranks generic aesthetics.
- Before coding, state a compact visual contract: hierarchy, density, grid/container, typography, spacing scale, surface/elevation, corner policy, accent usage, icon style and responsive behavior.
- Use a small coherent set of visual decisions repeatedly. Do not make every card/button/section unique.
- Hierarchy must come primarily from layout, spacing and typography; decoration is secondary.
- Render and inspect the actual UI. Source-code plausibility is not visual verification.

## Existing-product mode
Preserve the established component library and visual language unless redesign scope is explicit. Improve local defects without injecting a foreign design system. New components should look like siblings of existing high-quality components, not examples from a generic template gallery.

## Greenfield or weak-style mode
Choose one restrained direction and make it explicit before implementation. Define information density, grid/container width, typography scale, spacing scale, surface treatment, border/radius policy, accent color role and interaction language. Prefer neutral surfaces and one deliberate accent over many decorative colors.

## Composition and hierarchy
Identify the primary action/content first, secondary actions second, metadata/status third. Align related elements to shared edges/baselines. Use whitespace to group and separate meaningfully; avoid uniform padding that makes every region equally important. Keep line lengths, label/value relationships and control sizes consistent.

## Typography
Use a limited type scale and weights with clear semantic roles. Avoid oversized headings simply to make a screen feel designed. Preserve readable line height and contrast. Numerical/dashboard data needs alignment and scanability, not decorative display typography.

## Components and states
Every interactive component needs intentional default, hover, focus, active/selected, disabled, loading and error behavior when applicable. Empty states and long/realistic content are part of design validation. Reuse component anatomy rather than duplicating near-identical cards and controls.

## Anti-patterns for generated UI
Treat these as smells unless the brief explicitly asks for them: card-inside-card nesting, excessive pill shapes, gratuitous gradients/glow/glass, giant hero typography, every section floating in a rounded rectangle, arbitrary shadows, many accent colors, mismatched icon families, excessive empty space, and decorative widgets that weaken information density.

## Responsive behavior
Do not merely stack desktop columns. Decide what remains primary, what can collapse, how navigation changes, which tables/actions need alternate presentation, and how touch targets/spacing adapt. Verify realistic long content, not lorem-only ideal cases.

## Reference-driven work
Decompose the reference into measurable structure: viewport/container, columns, key alignments, spacing rhythm, typography roles, component dimensions, colors/surfaces and state behavior. Compare the rendered implementation to the reference systematically; fix shared layout/tokens before local pixel nudges.

## Quality gate
A UI task is not complete until a real render is inspected across relevant viewports and major states. If browser/screenshot tooling is unavailable, explicitly report visual QA as unexecuted instead of claiming pixel fidelity.
