---
slug: design
description: Professional UI/UX design discipline for hierarchy, art direction, systems, interaction states, responsive composition, references and rendered visual quality.
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

Use when creating, redesigning, materially restyling or visually evaluating a user-facing interface: application screens, dashboards, websites, landing pages, forms, navigation, data views, design systems, responsive redesigns, reference reproductions and visual-polish work.

Do not activate this skill merely because frontend code is touched when the task has no material visual or interaction-design decision. Combine it with the relevant frontend/framework/CSS skills for implementation, but treat this skill as the authority for visual hierarchy, composition, art direction and rendered design quality.

## Core contract

For every substantial visual task, follow this protocol before declaring the design complete:

1. **CLASSIFY THE MODE** — explicitly decide whether the task is `existing-product`, `greenfield`, or `reference-driven`. Do not apply greenfield novelty rules to an established product and do not let a greenfield task collapse into generic template defaults.
2. **IDENTIFY THE JOB** — state the audience, primary user job, primary information/action, and material constraints. Design around the user's task rather than around a component catalog.
3. **WRITE A VISUAL THESIS BEFORE CODING** — one or two sentences describing a recognizable direction. Generic labels such as “modern”, “clean”, “beautiful”, “premium” or “professional” are insufficient unless they are translated into concrete typography, composition, density, surface and color decisions.
4. **SET THREE DESIGN DIALS** — choose `design_variance`, `visual_density`, and `motion_intensity` on a 0–10 scale. The chosen values must affect layout and styling decisions; they are not decorative metadata.
5. **DEFINE ONE SIGNATURE MOVE** — identify one dominant or repeated visual decision that gives the interface recognizable identity without harming usability. In existing-product mode this must normally be expressed through the local design language rather than by importing a foreign aesthetic.
6. **LOCK THE SYSTEM BEFORE LOCAL STYLING** — establish typography roles, color roles, spacing rhythm, geometry/radius policy, borders/elevation, icon language, primary alignment lines and responsive priorities before accumulating page-specific exceptions.
7. **RUN ANTI-SLOP CHECKS BEFORE IMPLEMENTATION** — reject generic generated-UI defaults that are not justified by the brief, reference or established product grammar. A polished implementation of a generic template still fails this skill.
8. **BUILD HIERARCHY AND MACROSTRUCTURE BEFORE DECORATION** — placement, scale, grouping, whitespace, typography and alignment must explain what matters before shadows, gradients, illustrations or effects are added.
9. **DESIGN REAL STATES** — interactive components and data surfaces need intentional default, hover, focus-visible, active/pressed, selected, disabled, loading, empty, validation, error and overflow behavior where applicable.
10. **RENDER THE ACTUAL RESULT** — source review is not visual evidence. Inspect representative viewport and state combinations with realistic content.
11. **RUN THE BEAUTY GATE** — critique the render against hierarchy, coherence, distinctiveness, craft and brief fit. If it fails and rendering/editing is available, perform a focused correction pass before completion.
12. **REPORT LIMITATIONS HONESTLY** — if rendering, reference assets or target environments are unavailable, state exactly which visual claims remain unverified instead of declaring the work polished or pixel-perfect.

Professional quality does not mean visual timidity. Choose the appropriate intensity deliberately. Distinctiveness never outranks comprehension, accessibility or the user's primary task, but “safe” is not a substitute for art direction.

## Evidence to inspect

- Existing design tokens/theme variables: colors, typography, spacing, radii, shadows, borders, breakpoints and motion conventions.
- Reusable component primitives and their actual rendered usage on the strongest existing screens; code definitions alone may not reveal density or visual rhythm.
- Product navigation/information architecture and the user's main task on the target screen.
- Existing page silhouettes, container widths, common alignment lines, control heights, icon family and recurring component anatomy.
- Realistic data: long names, long identifiers, empty states, error messages, many rows/items, localization-like expansion, permission-dependent states and destructive actions.
- Reference images/design files decomposed into viewport, outer margins, container width, columns, gutters, baselines, component dimensions, typographic roles, color proportions and recurring visual motifs.
- Rendered screenshots at relevant viewport widths/heights and states; browser accessibility/layout tools where available.
- Approved project or external design-intelligence resources when they are available, while treating them as evidence/options rather than as authority over the task brief.

## Decision rules

- If an existing product has coherent visual grammar, extend it. Project grammar outranks generic design advice unless changing that grammar is explicit scope.
- If the current product system is weak or inconsistent, define a restrained but intentional local direction and minimal reusable token/component set; do not trigger a stealth global redesign from one feature.
- If the task is greenfield, do not fall back to generic SaaS aesthetics merely because they are familiar. Choose an explicit art direction and signature move before implementation.
- If the task is reference-driven, the reference's visual DNA outranks model taste. Adapt only where accessibility, content, platform or product constraints require it.
- If `design_variance >= 6`, introduce a structural or typographic decision that is visibly intentional; changing only colors, shadows or border radii does not satisfy this.
- If `visual_density >= 7`, optimize scan paths, aligned comparison, compact grouping and action proximity. Do not solve density with tiny text or decorative micro-cards.
- If `motion_intensity <= 3`, motion should be limited to feedback, focus, state changes and spatial continuity. If it is higher, motion must reinforce hierarchy/navigation rather than animate everything.
- If two elements compete for attention, decide which supports the primary task and reduce scale, contrast, saturation, weight or decoration of the secondary element.
- If more than half of the major content groups are boxed surfaces/cards without a containment reason, remove containers and restore hierarchy through alignment, spacing, type and background structure.
- If information must be compared across records, prefer aligned tables/lists/grids over independent cards that break scanning.
- If the mobile layout makes desktop information unreadable, choose priority columns, row drill-down, horizontal strategy or a deliberately different anatomy rather than blindly stacking everything.
- If many mismatches repeat across the screen, fix shared tokens, grid, typography or component anatomy before local pixel offsets.
- If a layout needs many one-off negative margins or absolute coordinates to resemble the concept, revisit the macrostructure instead of accumulating compensating nudges.
- If the design looks polished but could be swapped into a thousand unrelated AI-generated SaaS products with only logo/copy changes, the Beauty Gate fails.
- If a signature move harms comprehension, accessibility, interaction or product consistency, simplify it. Identity is a constraint-solving tool, not permission for gimmicks.

## Design preflight

Before substantial implementation, form a compact internal design contract. It may remain internal unless the user asks for it, but the decisions must be explicit enough to guide the code.

Use this shape:

```yaml
mode: existing-product | greenfield | reference-driven

audience: ""
primary_job: ""
primary_action_or_information: ""

visual_thesis: ""

design_variance: 0-10
visual_density: 0-10
motion_intensity: 0-10

signature_move: ""

typography_strategy: ""
color_strategy: ""
composition_strategy: ""
surface_strategy: ""

must_preserve: []
must_avoid: []
```

A valid `visual_thesis` predicts visible decisions. “Clean modern professional dashboard” is not a thesis. “Dense precision operations console with near-flat surfaces, editorial numeric typography and one high-chroma signal color” is actionable because it constrains density, surfaces, typography and color.

Do not turn the preflight into ceremonial prose. Keep it compact, then use it as a consistency check during implementation and final critique.

## Design modes

### Existing-product mode

Treat the strongest current screens/components as a local reference set. Inventory typography, spacing, radii, borders, surfaces, iconography, navigation, density, control heights and interaction-state language before inventing anything new.

Preserve established navigation, typography and interaction conventions unless redesigning them is explicit scope. A locally imperfect but coherent pattern is normally better than a visually impressive component that looks imported from another product.

The signature move in this mode should usually be a stronger expression of existing grammar: better hierarchy, clearer grouping, more disciplined data alignment, a more confident summary region, or an established visual motif used deliberately. Do not use “signature move” as justification for a foreign redesign.

When adding a new component, compare it beside sibling components at the same density and state so it reads as native to the product.

### Greenfield mode

Greenfield work requires intentional identity. Start from user/product context, then choose a concrete visual thesis rather than the statistically safest UI defaults.

Define content width/grid, typography roles, spacing scale, radius family, border/elevation policy, palette roles, icon language, density and interaction language before page-level styling.

Neutral surfaces and readable contrast remain good defaults, but “neutral” must not mean “anonymous”. Earn gradients, glow, glass, illustration, display-scale typography, asymmetry and dramatic imagery through the brief and the selected variance level.

Create one representative complex screen or section first when the system must support many states. A visual language that only works on a hero or a three-card mockup is not a production design system.

### Reference-driven mode

Treat the reference as a system to reverse-engineer rather than a screenshot to imitate with local offsets.

Extract macrostructure, grid, whitespace rhythm, typography roles, dominant geometry, color proportions, image treatment, surface language, recurring component anatomy and signature motifs.

Measure and render at matching viewport conditions where possible. Correct large geometry first, then typography/component anatomy, then color/elevation, then fine spacing. Source-code resemblance is irrelevant if the render differs.

Where the reference conflicts with accessibility, real content or platform constraints, preserve its hierarchy and rhythm while adapting semantics and interaction safely.

## Art direction and design dials

### Design variance

`design_variance` controls how far the composition may depart from familiar product conventions.

- **0–2 — Conventional:** stable grids, familiar navigation, restrained scale contrast, no deliberate overlap, low novelty.
- **3–5 — Distinct but restrained:** one recognizable visual idea, modest asymmetry, stronger type hierarchy and selective character.
- **6–8 — Expressive:** a structural signature move is required, repeated perfect symmetry should be questioned, stronger scale contrast and more assertive composition are allowed.
- **9–10 — Experimental:** unconventional composition/navigation may be appropriate, but only when the brief earns it and usability is explicitly validated.

Do not simulate variance with gratuitous gradients, rounded corners or animation. Variance is primarily structural, typographic and compositional.

### Visual density

`visual_density` controls information throughput and whitespace pressure.

- **0–2 — Spacious/editorial:** generous negative space, fewer simultaneous facts, larger visual moments.
- **3–5 — Standard product:** normal application/commerce density with clear grouping.
- **6–8 — Operational/analytical:** compact rhythm, aligned comparison, stronger scan paths, less decorative containment.
- **9–10 — Expert console:** very high information throughput; demands excellent alignment, hierarchy, stable interaction and legibility.

Higher density does not permit unreadably small text. Lower density does not permit empty ceremonial space that pushes routine work below the fold.

### Motion intensity

`motion_intensity` controls how much motion participates in hierarchy and navigation.

- **0–2 — Feedback only:** focus, press, success/error, expand/collapse and minimal state transitions.
- **3–5 — Restrained:** subtle entrance/state transitions and spatial continuity.
- **6–8 — Choreographed:** motion may sequence hierarchy, support navigation and preserve object continuity.
- **9–10 — Motion-led:** movement is part of the experience concept and requires careful performance/accessibility validation.

High motion intensity is not permission to animate every element. Repeated decorative motion creates noise and weakens functional feedback.

### Signature move

A signature move is one dominant or repeated visual decision that gives the interface identity without compromising use. Examples include oversized numeric typography, an editorial rail, asymmetric primary frame, strong divider language, monochrome surfaces plus one signal color, technical monospace metadata, a distinctive crop system, split-canvas composition or a purposeful interruption of the main grid.

Prefer one clear move over many gimmicks. The rest of the system should support it rather than compete with it.

## Composition and hierarchy

Design the page silhouette and macrostructure before styling isolated components. Decide major regions, primary axis, secondary axis, focal point, content sequence, alignment anchors and any intentional visual interruption.

Changing card shadows or button radii does not create a new composition. A repeated `hero → three cards → two-column section → testimonials → CTA` sequence remains generic even if its colors change.

Establish shared left/right edges and baselines across unrelated components. Misaligned one-off containers make polished components feel amateur.

Use whitespace to encode relationships: elements that belong together must be visibly closer than elements that merely share a parent section. Vary rhythm intentionally when one section deserves interruption; equal spacing everywhere produces mechanical sameness.

Keep page title/context/actions in a stable hierarchy. Breadcrumbs, tabs, filters, headings, summaries and primary actions should not all demand equal attention.

Reserve full-width or visually dominant regions for content that deserves interruption. Repeated banners and oversized headers reduce the signal of each other.

## Typography

Choose a typography strategy, not merely a font family. Define display/title, body, label/meta and data/numeric roles as needed, including size, weight, line-height and contrast mechanism.

Start with readable body text and derive heading sizes from hierarchy rather than aesthetics. Most application UIs need fewer and smaller heading jumps than marketing/editorial pages.

Use weight before excessive size changes for compact hierarchy, but avoid making every heading and label bold. Too many strong weights flatten distinction and create visual noise.

For greenfield expressive work, do not choose the most statistically common UI font merely because it is familiar. Either justify the choice through the thesis/system or choose a type strategy with more identity. Existing-product/reference mode may correctly require common fonts.

Keep measure and line-height suitable to content: prose needs comfortable line length and leading; dense labels/rows need tighter but still legible rhythm.

Use tabular numerals or aligned numeric columns where comparison matters. Units, deltas and metadata should not overpower the values they qualify.

Handle truncation intentionally: wrap where meaning matters, provide a recovery path when truncated, and test long unbroken identifiers.

Do not use low-contrast gray for all secondary text. Hierarchy must not make required information difficult to read.

## Color and surfaces

Define semantic color roles before individual hex values: background, primary surface, secondary surface, primary text, muted text, border/divider, accent, success, warning and danger.

Treat accent as scarce. If the accent is distributed uniformly across headings, icons, borders, buttons and decorative shapes, it loses its ability to signal priority.

Think in proportions as well as swatches. A restrained interface may be mostly neutral with a small accent footprint; an expressive concept may invert that relationship, but the allocation must still support hierarchy.

Use surfaces only when they encode containment, elevation, interaction, scroll ownership or meaningful background separation. Do not create a card merely to make a block “look designed”.

Use one coherent radius/elevation family. Mixed unrelated shadows and rounded shapes make the page feel assembled from component samples.

Status colors carry semantic meaning and should not become general decoration. Reserve strong warning/danger treatments for actionable abnormal conditions.

## Components and states

Specify component anatomy before variants. A button differs by intent/priority, not by arbitrary radius/shadow choices on each page.

Selected, active, hover and focus are distinct states. Do not reuse the same faint background for all of them and expect context to explain the difference.

Loading states should preserve layout where possible and indicate what is pending. Avoid large skeleton displays for tiny operations where a spinner, optimistic state or disabled action is clearer.

Empty states should explain absence and the next useful action only when an action exists. Decorative empty-state art should not consume most of a dense work screen.

Errors should be proximal and recoverable. Cross-cutting failures may justify a banner; field and row failures belong where correction happens.

Disabled controls should not conceal why an action is unavailable when users need to understand the prerequisite.

For icons, use one family with consistent optical size/stroke/fill behavior. Decorative icon boxes on every row or card are not a substitute for hierarchy.

## Data-dense and operational UI

Prioritize scan paths: status → identity → key metrics → next action. Repeated metadata should align and recede.

Use tables when users compare the same fields across many records. Use cards when records contain heterogeneous content or need stronger individual identity.

Avoid one KPI per oversized card by default. Group related measures and show trends/context only when they change decisions.

Status labels should use consistent semantics and density. Reserve strong warning/danger color for actionable abnormal states.

Filters should reflect frequent decisions, expose active filter state and make reset clear. Rare advanced filters can be disclosed progressively.

Pagination or bounded recent lists should replace giant technical feeds. Show totals/continuation affordances without dumping hundreds of rows.

Operational timelines/logs need time, actor/source, action/outcome and expandable detail. Raw serialized payload is secondary on demand.

At higher density, remove decorative containment before shrinking type. Alignment and grouping should carry more of the hierarchy.

## Responsive behavior

Responsive design is reprioritization, not column stacking.

At each material breakpoint identify what stays primary, what can disappear, move, collapse or become drill-down, and how action placement changes. Preserve the user's primary task rather than desktop geometry.

Navigation may shift from persistent sidebar to drawer/bottom/top patterns, but location and major sections must remain discoverable.

Keep touch targets and separation adequate; do not simply scale desktop controls down.

For action bars, preserve the primary action and move secondary actions into overflow before wrapping into confusing multiple rows.

For dense grids, consider frozen key column, horizontal scroll, priority columns or row detail rather than converting every table cell into a vertical label/value card.

Test real viewport heights as well as widths. Sticky headers/footers can consume most of a small screen even when width technically fits.

## Reference-driven work

Measure the reference viewport, outer margins/container width, columns, gutters, recurring vertical gaps, control heights, radii and major alignment lines before coding.

Classify typography by semantic role and approximate size/weight/line-height rather than matching only the page title.

Extract color roles and approximate proportions instead of sampling dozens of near-duplicate pixels.

Identify repeated component anatomy and state behavior. A screenshot shows one state, so infer missing states from the reference's product/system conventions rather than inventing unrelated styling.

Render implementation at the same viewport where possible and compare large geometry first: container, columns, header height and density; then typography/components; then fine offsets.

When a mismatch repeats across the screen, change the shared token/grid/component. Pixel nudges should be the last step, not the method.

## Hard anti-slop gates

These are **fail conditions** in greenfield work unless the brief, reference or established design system explicitly justifies them. In existing-product/reference mode, preserve legitimate local patterns rather than applying these gates blindly.

- Generic purple/blue gradient used as the primary identity without a concept reason.
- Page composed predominantly of independent rounded cards even when content does not require containment.
- Automatic three-equal-icon-card section used merely because it is a familiar template.
- Every section repeats `eyebrow → heading → paragraph → cards` regardless of information need.
- Repeated alternating text/image sections with no narrative or interaction reason.
- Pill-shaped treatment applied to most navigation, statuses and controls without a coherent product language.
- Decorative icon boxes attached to nearly every row/card.
- Gradient text used merely to signal “technology” or “AI”.
- Glassmorphism, glow or heavy blur used without a brief or hierarchy reason.
- Fake metrics, charts or visualizations invented to make an empty concept look complete.
- Centered composition used throughout an application workflow where scanning/action hierarchy would benefit from stronger alignment.
- Every major section receives equal visual weight and spacing.
- The design contains no identifiable signature move in greenfield work.
- The visual thesis can only be described with generic adjectives such as “modern”, “clean”, “minimal” or “premium”.
- Common default typography/palette choices are used with no relation to the product thesis when the task explicitly calls for distinctive greenfield design.

A gate may be overridden by real evidence. The override must come from the brief, reference or established product system—not from convenience.

## Structural slop

Generated UI often remains generic even after colors and typography improve because the underlying information architecture and macrostructure are template-derived.

Treat structural slop as a defect when:

- nearly every major region has the same width, anatomy and surface treatment;
- nearly every content group is a card;
- every section uses identical vertical rhythm;
- a marketing page follows a canonical template sequence without any product-specific narrative logic;
- all visual interest is delegated to gradients, icons or illustration while the layout remains generic;
- information architecture appears to come from a template rather than from the user's primary job;
- repeated symmetric grids flatten differences in importance;
- secondary controls occupy as much space or contrast as primary actions;
- whitespace is distributed uniformly instead of encoding relationships.

Fix structural slop at the macrostructure, grid, grouping and hierarchy level. Do not try to decorate it away.

## Design intelligence

When an approved design-intelligence resource such as `ui-ux-pro-max` is available, use it to explore typography pairings, palette directions, product-specific UI patterns, style references, accessibility considerations or stack-specific implementation hints.

Design intelligence **informs**; this skill **decides**. Never blindly combine recommendations from several databases or style catalogs. Filter every option through the preflight thesis, mode, dials and existing product constraints.

If a recommended font, palette or style conflicts with the product grammar, reference or content requirements, reject it. The goal is a coherent system, not maximum recommendation coverage.

Do not require external design intelligence for competent work. The core skill must still produce a deliberate design when only repository evidence and the user brief are available.

## Workflow

1. **INSPECT** — gather current product/reference evidence, real content and relevant constraints.
2. **CLASSIFY MODE** — existing-product, greenfield or reference-driven.
3. **PREFLIGHT** — define audience, primary job, visual thesis, three dials, signature move and preserve/avoid constraints.
4. **DEFINE MACROSTRUCTURE** — establish page silhouette, focal point, primary/secondary axes, alignment anchors and content sequence.
5. **LOCK THE SYSTEM** — typography, color roles, spacing rhythm, geometry, surfaces, icon language and responsive priorities.
6. **RUN PRE-CODE ANTI-SLOP CHECK** — remove generic template decisions that are not justified.
7. **IMPLEMENT SEMANTIC STRUCTURE** — build hierarchy and component anatomy before decorative effects.
8. **DESIGN STATES** — loading, empty, error, selected, focus, disabled, long content and other material states.
9. **ADAPT RESPONSIVELY** — reprioritize navigation, columns, tables and actions for each material breakpoint.
10. **RENDER** — inspect the actual UI with loaded fonts/assets and realistic content.
11. **CRITIQUE THE TOP THREE VISUAL DEFECTS** — identify the most important problems by impact, not by ease of fixing.
12. **CORRECT SYSTEMIC CAUSES FIRST** — grid/tokens/type/component anatomy before local offsets.
13. **RENDER AGAIN WHEN A SUBSTANTIAL CORRECTION WAS MADE** — verify that the fix improved rather than merely changed the result.
14. **RUN BEAUTY GATE AND ACCESSIBILITY/INTERACTION CHECKS** — then report exact coverage and any unexecuted visual checks.

Do not iterate indefinitely. Two focused visual correction passes without new evidence are enough; after that, report the remaining limitation instead of entering random pixel-whack-a-mole.

## Implementation patterns

- Use a spacing scale with a small number of steps and semantic grouping: tighter within one concept, larger between distinct concepts. Avoid uniform padding everywhere.
- Use a limited typography ladder with explicit roles such as page title, section title, body, label, metadata and numeric/data emphasis.
- For dashboards, reserve strongest contrast for key status/action and keep supporting metrics neutral; aligned numbers and compact labels often outperform oversized statistic cards.
- For forms, group fields by user decision, keep labels persistent, place help/errors near their controls, and keep primary submission location predictable.
- For navigation, show location and selected state clearly without relying only on color; avoid making every nav item a pill unless the product language calls for it.
- For cards, define one anatomy: optional heading/meta/action, content rhythm, border/surface and state. Use cards only where a bounded object/group benefits from containment.
- For tables/lists, align comparable values, keep row actions discoverable without dominating, use truncation only with a recovery path, and make empty/loading states preserve structure.
- For dialogs/drawers, use them for focused temporary tasks, not as a substitute for information architecture. Size according to content and keep escape/close/focus behavior coherent.
- Prefer shared tokens/components when the same visual rule repeats. Avoid per-page copies that drift from sibling screens.
- Use intrinsic/responsive layout primitives before absolute positioning; many local offsets usually indicate the wrong parent structure.

## Failure modes

- **Generic SaaS convergence:** neutral sidebar, interchangeable cards, familiar accent and no visual thesis. Return to mode/preflight and choose a real direction.
- **Template aesthetic injection:** product-specific UI becomes an imported dashboard/landing template. Re-anchor to existing grammar and the user's task.
- **Hierarchy by decoration:** borders, shadows, gradients and colors compensate for weak grouping. Rebuild layout, alignment and type hierarchy first.
- **Uniform importance:** every panel gets the same padding, title size and contrast. Re-rank primary, secondary and metadata layers.
- **Card inflation:** each label/value becomes a rounded container. Remove boxes and align information structurally.
- **Signature-move overload:** several gimmicks compete. Keep the one move that best supports the thesis and simplify the rest.
- **Responsive stacking:** desktop columns simply become a long mobile page with buried actions. Reprioritize and transform components.
- **Reference pixel chasing:** local margins are nudged before matching container/grid/type, producing fragile CSS. Fix systemic geometry first.
- **State omission:** beautiful populated screen fails on loading/error/empty/long content. Treat states as part of component anatomy.
- **Source-only QA:** implementation is declared polished without rendered inspection. Render it or report visual QA as unexecuted.
- **Accessibility sacrificed for style:** focus, contrast, semantics or readable sizes are weakened. Preserve functional quality and adapt visual intent.
- **Design-database collage:** unrelated font/palette/style recommendations are combined. Reapply the thesis and remove conflicting ideas.
- **Endless pixel iteration:** repeated tiny offsets replace structural diagnosis. Stop after bounded correction passes and report what remains.

## Beauty gate

The Beauty Gate is a structured visual-quality check on the rendered result, not a confidence statement about the code.

First answer these observable questions:

- Is the primary focal point immediately obvious?
- Does the composition have a deliberate macrostructure rather than a component-template silhouette?
- Is there one identifiable signature move where the mode calls for one?
- Is typography doing meaningful hierarchy work?
- Is accent scarce or allocated deliberately enough to preserve emphasis?
- Do repeated components visibly belong to one system?
- Is whitespace encoding relationships rather than being uniformly distributed?
- Are there any triggered hard anti-slop or structural-slop gates?
- If logo and copy were removed, would the design still have some recognizable visual identity in greenfield expressive work?
- Does the design fit the actual user job rather than merely looking good as a portfolio screenshot?

Then score:

- **Hierarchy:** 0 = unclear, 1 = workable, 2 = immediately legible.
- **Coherence:** 0 = conflicting systems, 1 = mostly consistent, 2 = disciplined and unified.
- **Distinctiveness:** 0 = generic/template-derived, 1 = some identity, 2 = recognizable and intentional for the selected mode.
- **Craft:** 0 = obvious spacing/state/detail defects, 1 = competent, 2 = polished under realistic content.
- **Brief fit:** 0 = aesthetic fights the task/product, 1 = acceptable, 2 = strongly supports the intended user/product context.

Pass requires **8/10 or higher**, no dimension at `0`, and no unjustified hard anti-slop gate.

Before correcting a failed or weak render, list the **top three visual defects** by impact. Fix systemic causes first. Do not praise the implementation instead of critiquing it.

## Verification

- Render every materially different responsive layout; at minimum representative desktop and small-screen widths when both are in scope.
- Inspect default, hover/focus/selected, loading, empty, error, disabled and overflow/long-content states that materially apply.
- Compare reference-driven work at matching viewport conditions and fix container/grid/type/token mismatches before local spacing.
- Check keyboard focus, contrast, labels and interaction semantics with accessibility tooling for interactive UI.
- Use realistic data volume and long values; ensure pagination/scrolling/truncation/disclosure preserve scanability.
- Inspect visual consistency of radius, border, surface, icon family, control heights, type roles and spacing rhythm across the screen.
- Check primary task clarity: primary action/status/information must be identifiable without reading every panel.
- Verify no decorative element steals more attention than the information/action it supports.
- Run the Beauty Gate against the rendered result and record the top three visual defects before a substantial correction pass.
- Capture screenshots or equivalent render evidence when tooling supports it; otherwise state exactly which visual checks remain unexecuted.
- Reinspect after final CSS/layout/token changes because late adjustments can regress unrelated breakpoints.

## Completion criteria

- The task mode is explicit and the design follows the correct novelty/coherence rules for that mode.
- The design has a concrete visual thesis rather than generic aesthetic adjectives.
- The three design dials materially influenced decisions.
- A signature move exists where appropriate and does not compromise usability or product coherence.
- Information hierarchy and density support the primary task without unnecessary decorative containment.
- Typography, spacing, surfaces, radii, icons and accent usage form a small reusable system.
- Major interactive/data states and realistic content are intentionally designed.
- Responsive layouts are reprioritized rather than merely stacked.
- Reference fidelity claims are backed by systematic rendered comparison when reference-driven.
- The final render passes the Beauty Gate or the remaining visual limitation is reported explicitly.
- Accessibility and visual QA are executed for the available environment, with limitations stated honestly.
- New components look like siblings of the product's strongest existing components rather than generated template fragments.

## Related skills and escalation

- Use `frontend`, `html`, `css` and the relevant framework skill to implement the design without breaking application architecture.
- Use `accessibility` for detailed semantic, keyboard and contrast requirements.
- Use `visual-qa` for systematic screenshot/reference comparison, viewport/state matrices and regression evidence.
- Use `web-performance` when visual effects, fonts, assets, motion or layout choices materially affect runtime performance.
- When an approved external design-intelligence skill such as `ui-ux-pro-max` is installed, use it as a searchable option/reference source, not as an authority over this skill's preflight decisions.
- Escalate ambiguous brand/product direction when one missing decision would create multiple incompatible visual systems. Do not hide uncertainty by mixing them.
