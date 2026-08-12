---
slug: design
description: Professional UI/UX design discipline for hierarchy, systems, interaction states, responsive composition, references and rendered visual quality.
kind: capability
keywords:
- design
- ui
- ux
- layout
- visual hierarchy
- typography
- spacing
- design system
- responsive
- reference
- dashboard
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# UI/UX Design Skill

## Apply when

Use when creating or redesigning visible UI, translating a reference into code, extending an existing product's visual language, or fixing a screen whose usability depends on hierarchy and composition rather than isolated CSS. This skill is intentionally deeper than a style checklist: the agent should use it to make explicit design decisions, implement them as a coherent system, and verify the rendered result.

## Core contract

- Start from evidence, not taste: inspect existing screens, tokens, components, fonts, spacing, radii, icon family, data density and interaction conventions. Existing high-quality product grammar outranks generic trends.

- Before coding, write a compact visual contract for the task: primary user goal, hierarchy, density, grid/container, typography roles, spacing rhythm, surface/elevation policy, corner policy, accent role, icon treatment and responsive behavior.

- Hierarchy comes first from placement, size, spacing, grouping, typography and contrast; decoration should reinforce hierarchy rather than manufacture it.

- Use a small coherent set of repeated decisions. One screen should not contain five card anatomies, four radius values, unrelated shadows and several competing accent colors.

- Design the information architecture before the chrome: determine what must be immediately visible, what can be secondary/disclosed, and what can be omitted entirely.

- Every interactive component needs intentional default, hover, focus-visible, active/pressed, selected, disabled, loading, empty, validation and error behavior where applicable.

- Data-dense interfaces should optimize scanning, comparison and action proximity. Do not solve density by shrinking everything or by wrapping each fact in a decorative card.

- Responsive design is reprioritization, not column stacking. Decide what remains primary, what collapses, how navigation changes, and how tables/actions transform.

- Reference-driven work requires measurable decomposition and rendered comparison. Source-code similarity is not visual fidelity.

- A design is not complete until realistic content and major states are rendered and inspected; if rendering tools are unavailable, report visual QA as unexecuted.

## Evidence to inspect

- Existing design tokens/theme variables: colors, type scale, spacing, radii, shadows, borders and responsive breakpoints.

- Reusable component primitives and their actual rendered usage on the strongest existing screens.

- Product navigation/information architecture and the user's main task on the target screen.

- Realistic data: long names, empty states, error messages, many rows/items, localization-like expansion and permission-dependent states.

- Reference images/design files decomposed into container widths, columns, baselines, component dimensions, typographic roles and visual rhythm.

- Rendered screenshots at relevant viewports and states; browser accessibility/layout tools where available.

## Decision rules

- If an existing product has a coherent visual system, extend it; redesign only elements within explicit scope and avoid importing a foreign dashboard/template aesthetic.

- If the current system is weak/inconsistent, define one restrained direction and a minimal token set before creating components.

- If two elements compete for attention, decide which supports the primary task and reduce size/contrast/decoration of the secondary element.

- If every section is boxed, remove containers until boundaries correspond to real grouping, interaction, background separation or scroll behavior.

- If a control is rarely used or destructive, move it away from the primary action hierarchy while keeping it discoverable and accessible.

- If information must be compared across rows, prefer aligned columns/table/list structure over independent cards that break scanning.

- If a mobile layout makes a desktop table unreadable, choose priority columns, row drill-down, horizontal strategy or alternate card/list anatomy intentionally.

- If a reference conflicts with product accessibility/content constraints, preserve the reference's hierarchy and rhythm while adapting interaction/contrast semantics safely.

- If visual mismatch appears across many components, fix shared tokens/grid/type first before local pixel offsets.

- If a layout needs many one-off negative margins/absolute coordinates to match the concept, revisit component/grid structure rather than accumulating nudges.

## Workflow

1. Define the user's primary task and rank content/actions into primary, secondary and tertiary layers.

2. Audit the existing product grammar or, for greenfield work, define the restrained visual contract and core tokens.

3. Sketch the page as structural regions and alignment lines before styling individual components.

4. Establish typography and spacing rhythm; then define surfaces, borders, elevation, radius and accent rules.

5. Implement reusable component anatomy and all meaningful interaction/data states with realistic content.

6. Adapt deliberately for each relevant breakpoint: navigation, columns, tables, action placement and touch density.

7. Render the real UI and compare against requirements/reference at representative desktop and mobile widths.

8. Fix systemic mismatches first, then component anatomy, then fine spacing; repeat until no obvious hierarchy/state/responsive defect remains.

9. Run accessibility/interaction checks and verify loading/empty/error/overflow content, not just the ideal populated state.

10. Inspect the final screen without implementation context: can a first-time user identify what matters, what changed, and what action is available within seconds?

## Implementation patterns

- Use a spacing scale with a small number of steps and semantic grouping: tighter within one concept, larger between distinct concepts. Avoid uniform 16px padding everywhere.

- Use a limited typography ladder with explicit roles such as page title, section title, body, label, metadata and numeric/data emphasis. Weight and line-height are part of the role.

- For dashboards, reserve strongest contrast for key status/action and keep supporting metrics neutral; aligned numbers and compact labels often outperform oversized statistic cards.

- For forms, group fields by user decision, keep labels persistent, place help/errors near their controls, and keep primary submission location predictable.

- For navigation, show location and selected state clearly without relying only on color; avoid making every nav item a pill unless the product language calls for it.

- For cards, define one anatomy: optional heading/meta/action, content rhythm, border/surface and state. Use cards only where a bounded object/group benefits from containment.

- For tables/lists, align comparable values, keep row actions discoverable without dominating, use truncation only with a recovery path, and make empty/loading states preserve structure.

- For dialogs/drawers, use them for focused temporary tasks, not as a substitute for information architecture. Size according to content and keep escape/close/focus behavior coherent.

- For icons, use one family, consistent stroke/fill/optical size and meaningful pairing with labels; do not use decorative icons to make every row look designed.

- For color, define semantic roles (surface, text, muted, border, accent, success, warning, danger) and control saturation; status colors should not become general decoration.

## Existing-product mode

- Inventory the strongest existing screen/components and treat them as the local reference set. Copy their rhythm and anatomy before inventing anything new.

- Preserve established navigation, typography and interaction conventions unless the redesign explicitly targets them; inconsistency is worse than a locally imperfect but coherent pattern.

- Refactor tokens/components when the same defect repeats, but avoid a stealth global redesign triggered by one feature.

- When adding a new component, compare it next to sibling components at the same state/density so it looks native to the product rather than imported from a template.

## Greenfield or weak-style mode

- Choose one direction in plain language, for example: compact neutral operations dashboard with soft borders, low elevation and one cool accent. Avoid mood-board vagueness.

- Define content width/grid, base font and type scale, spacing scale, radius family, border/elevation policy, accent/status palette and interaction language before page-level styling.

- Default to neutral surfaces and readable contrast; earn every gradient, glow, glass effect, illustration and oversized display treatment through the brief.

- Create one representative complex screen first and use it to test the system under forms, data, navigation and state variation before expanding.

## Composition and hierarchy

- Establish shared left/right edges and baselines across unrelated components to create visual order. Misaligned 1-off containers make polished components feel amateur.

- Use whitespace to encode relationships: elements that belong together should be visibly closer than elements that only share a parent section.

- Keep page title/context/actions in a stable hierarchy; do not make breadcrumbs, tabs, filters and headings all equally prominent.

- Avoid symmetrical empty space when the product is information-heavy; density should reflect task frequency and scanning needs.

- Use progressive disclosure for secondary detail, but never hide information required to understand a destructive or irreversible action.

- Reserve prominent full-width regions for content that deserves interruption; repeated banners and oversized headers reduce the signal of each other.

## Typography

- Start with readable body text and derive heading sizes from hierarchy rather than aesthetics. Most application UIs need fewer and smaller heading jumps than marketing pages.

- Use weight before large size changes for compact hierarchy; too many bold weights flatten distinction and create visual noise.

- Keep measure/line-height suitable to content: prose needs comfortable line length and leading, while dense labels/rows need tighter but still legible rhythm.

- Use tabular numerals or aligned numeric columns where comparison matters; units and secondary deltas should not overpower the number.

- Handle truncation intentionally: allow wrapping where meaning matters, provide tooltip/detail when truncated, and test long unbroken identifiers.

- Do not use low-contrast gray for all secondary text; distinguish hierarchy without making required content difficult to read.

## Components and states

- Specify component anatomy before variants. A button differs by intent/priority, not by arbitrary radius/shadow for each page.

- Selected, active, hover and focus are different states; do not use the same faint background for all and rely on context to explain it.

- Loading states should preserve layout and indicate what is pending; avoid skeletons for tiny operations where a spinner/disabled action is clearer.

- Empty states should explain absence and next action only when an action is possible; avoid decorative empty-state art that consumes most of a dense work screen.

- Errors should be proximal and recoverable. System-wide banners are for cross-cutting failures; field/row errors belong where the correction happens.

- Disabled controls should not conceal why an action is unavailable when users reasonably need to understand the prerequisite.

## Data-dense and operational UI

- Prioritize scan paths: status → identity → key metrics → next action. Repeated metadata should align and recede.

- Use tables when users compare the same fields across many records; use cards when each record has heterogeneous content or stronger visual identity.

- Avoid one KPI per oversized card by default. Group related measures and provide trends/context only when they change decisions.

- Status labels should use consistent semantics and widths/density; reserve strong warning/danger color for actionable abnormal conditions.

- Filters should reflect frequent decisions, expose active filter state and make reset clear; advanced rarely used filters can be disclosed.

- Pagination or bounded recent lists should replace giant technical feeds. Show totals/continuation affordances without dumping hundreds of rows.

- Operational timelines/logs need time, actor/source, action/outcome and expandable detail; raw serialized payload should be secondary on demand.

## Responsive behavior

- At each breakpoint identify what can disappear, move, collapse or become a drill-down. Preserve the user's primary task, not desktop geometry.

- Navigation may shift from persistent sidebar to drawer/bottom/top pattern, but location and major sections must remain discoverable.

- Keep touch targets and separation adequate; do not simply scale desktop controls down.

- For action bars, preserve the primary action and move secondary actions into overflow before wrapping into confusing multiple rows.

- For dense grids, consider frozen key column, horizontal scroll, priority columns or row detail rather than turning every cell into a vertical label/value card.

- Test real viewport heights as well as widths; sticky headers/footers can leave little usable content area on small screens.

## Reference-driven work

- Measure reference viewport, outer margins/container width, columns, gutters, recurring vertical gaps, control heights, radii and major alignment lines before coding.

- Classify typography by semantic role and approximate size/weight/line-height rather than matching only the page title.

- Extract color roles (background, surface, border, primary text, muted text, accent/status) instead of sampling dozens of near-duplicate pixels.

- Identify repeated component anatomy and state behavior; a reference screenshot shows one state, so infer missing states from product/system conventions rather than inventing unrelated styling.

- Render the implementation at the same viewport and compare large geometry first: container, columns, header height, density, then typography/components, then fine offsets.

- When a mismatch repeats across the screen, change the shared token/grid/component. Pixel nudges should be the last step, not the method.

## Anti-patterns for generated UI

- Card inside card inside rounded section; excessive pills; gratuitous gradients/glow/glass; arbitrary shadows; giant hero headings in utility screens; decorative blobs and fake charts.

- Every section with icon + eyebrow + subtitle + card regardless of information need. Generated symmetry often adds ceremony while hiding the task.

- Too many accent colors or semantic colors used decoratively, making genuine status/error states less meaningful.

- Excessive whitespace in dashboards that forces scrolling without improving comprehension, or extreme compactness that removes grouping and touch usability.

- Mismatched icon families, inconsistent control heights/radii, and per-page component copies that drift from the shared system.

- Placeholder-perfect design validated only with short English text, one row and no loading/error/permission state.

## Failure modes

- Template aesthetic injection: product-specific UI becomes generic SaaS cards/pills/gradients. Re-anchor to existing grammar and task hierarchy.

- Hierarchy by decoration: many borders/shadows/colors compensate for weak layout. Rebuild grouping, alignment and type scale first.

- Uniform importance: every panel gets same padding/title/contrast. Rank primary, secondary and metadata layers.

- Card inflation: each label/value becomes a rounded container. Remove boxes and align information structurally.

- Responsive stacking: desktop columns simply become a long mobile page with buried actions. Reprioritize and transform components.

- Reference pixel chasing: local margins are nudged before matching container/grid/type, producing fragile CSS. Fix systemic geometry first.

- State omission: beautiful populated screen fails on loading/error/empty/long content. Design states as part of component contract.

- Source-only QA: implementation is declared pixel-perfect without render comparison. Report unverified or render it.

- Accessibility sacrificed for style: focus, contrast, semantics or readable sizes are weakened. Preserve functional quality and adapt visual intent.

- One-off component variants: each new screen forks spacing/radius/style. Consolidate repeated anatomy into shared tokens/primitives.

## Verification

- Render at every materially different responsive layout, at minimum representative desktop and small-screen widths when both are in scope.

- Inspect default, hover/focus/selected, loading, empty, error, disabled and overflow/long-content states that apply.

- Compare reference-driven work at the same viewport and fix container/grid/type/token mismatches before local spacing.

- Check keyboard focus, contrast, labels and interaction semantics with accessibility tooling for interactive UI.

- Use realistic data volume and long values; ensure pagination/scrolling/truncation/disclosure preserve scanability.

- Inspect visual consistency of radius, border, surface, icon family, control heights and spacing scale across the screen.

- Check primary task clarity: primary action/status must be identifiable without reading every panel.

- Verify no decorative element steals more attention than the information/action it supports.

- Capture screenshots or equivalent render evidence when tooling supports it; otherwise state exactly which visual checks remain unexecuted.

- Reinspect after final CSS/layout changes because late token adjustments can regress unrelated breakpoints.

## Completion criteria

- The screen has an explicit, coherent visual contract grounded in existing product evidence or a deliberate greenfield direction.

- Information hierarchy and density support the primary task without unnecessary decorative containers.

- Typography, spacing, surfaces, radii, icons and accent usage form a small reusable system.

- Major interactive/data states and realistic content are intentionally designed.

- Responsive layouts are reprioritized rather than merely stacked.

- Reference fidelity claims are backed by systematic render comparison.

- Accessibility and visual QA are executed for the available environment, with limitations stated honestly.

- New components look like siblings of the product's strongest existing components rather than generated template fragments.

## Related skills and escalation

- Use `frontend`, `html`, `css` and the framework skill to implement the design without breaking architecture.

- Use `accessibility` for detailed semantic/keyboard requirements and `visual-qa` for render comparison workflow.

- Use `web-performance` when visual effects/assets/layout choices affect runtime performance.

- Escalate ambiguous brand/product direction rather than inventing multiple incompatible visual languages inside one feature.
