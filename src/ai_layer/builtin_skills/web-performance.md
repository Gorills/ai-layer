---
slug: web-performance
description: Measurement-first browser performance guidance for loading, responsiveness,
  rendering and bundle/network behavior.
kind: capability
keywords:
- performance
- web vitals
- bundle
- lazy
- render
- lcp
- inp
- cls
- slow
- lazy load
- render performance
- image optimization
entry_sections:
- Apply when
- Core contract
---
# Web Performance Skill

## Apply when
A frontend change targets or risks loading speed, interaction responsiveness, layout stability, bundle/network cost or rendering efficiency.

## Core contract
- Measure the affected path before/after when tooling permits; do not infer user performance only from source diff size.
- Optimize the dominant bottleneck, not generic micro-optimizations.
- Preserve correctness, accessibility and SEO while optimizing.
- Prevent avoidable layout shifts by reserving media/content geometry and avoiding late structural changes.
- Split/lazy-load only at meaningful boundaries; excessive fragmentation can worsen network/runtime cost.

## Runtime
Avoid unnecessary rerender/recompute loops, main-thread blocking and duplicate network requests. Use caching only with explicit ownership/invalidation semantics. Large media should be appropriately sized/formatted for actual display needs.

## Verification
Use project/browser profiling, production build/bundle output and representative network/device conditions where available. Report lab versus field evidence distinctly.
