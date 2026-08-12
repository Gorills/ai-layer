---
slug: web-performance
description: Web performance engineering for loading, Core Web Vitals, network payloads, rendering, caching, images, JavaScript cost and measured regressions.
kind: capability
keywords:
- web performance
- lcp
- inp
- cls
- core web vitals
- bundle
- image
- cache
- render
- lighthouse
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Web Performance Skill

## Apply when

Use when page load, interaction responsiveness, layout stability, bundle/network cost or rendering performance matters, or when a UI change adds large assets/dependencies. Optimize from measurements in representative conditions rather than generic scores alone.

## Core contract

- Measure before and after under controlled conditions. Performance work without a baseline cannot prove improvement or detect regressions.

- Separate server/network, loading/render and interaction/main-thread bottlenecks; each needs different fixes.

- Prioritize user-visible critical content and eliminate unnecessary critical-path requests, parsing and execution.

- Images/fonts often dominate visual load: serve correct dimensions/formats, avoid layout shifts and preload only genuinely critical resources.

- JavaScript cost includes download, parse, execute, hydration and long-task interaction delay; bundle size alone is not full runtime cost.

- Keep DOM/layout work bounded and avoid forced synchronous layout/read-write thrashing in hot interactions.

- Caching requires ownership/invalidation and correct HTTP/CDN semantics; do not cache personalized/sensitive content accidentally.

- Lazy loading helps noncritical resources but can hurt LCP/interaction when applied blindly to above-the-fold or imminently needed content.

- Core Web Vitals are field-oriented user experience measures; lab tools are diagnostic approximations and should not be treated as identical.

- Preserve correctness/accessibility/design while optimizing; a faster broken or unreadable UI is not success.

## Evidence to inspect

- Field analytics/RUM/Core Web Vitals if available, plus lab traces such as browser Performance/Lighthouse.

- Network waterfall: TTFB, redirects, blocking resources, transfer sizes, cache status and request priority.

- Bundle/chunk analyzer and dependency graph for client JavaScript/CSS.

- Performance trace showing long tasks, scripting, style/layout, paint and interaction timing.

- Image/font dimensions, formats, loading priority and layout reservation.

- Server/API timing and cache/CDN headers for critical data/resources.

## Decision rules

- If LCP is network-bound by hero/content asset, prioritize the actual LCP resource and remove competing critical requests rather than preloading everything.

- If interaction delay comes from long JS tasks, reduce work/split scheduling or architecture; shaving image bytes will not solve main-thread blocking.

- If CLS comes from media/dynamic content, reserve geometry and avoid inserting content above current viewport unexpectedly.

- If a large dependency is used on one route/interaction, lazy/code-split that feature when startup benefit exceeds added request/complexity.

- If server response dominates, optimize backend/cache/data path before micro-optimizing client rendering.

- If a cache entry depends on user/locale/auth/query variants, encode correct cache key/Vary/private policy or do not share-cache it.

- If repeated renders are suspected, profile actual component/render causes before adding memoization everywhere.

- If a lab score improves by delaying essential work until after measurement window, reject the gaming and measure real user task completion.

## Workflow

1. Choose target journey/device/network and capture baseline field/lab metrics plus trace.

2. Identify the dominant bottleneck category: server/network, resource loading, JS main thread, style/layout/paint or interaction architecture.

3. Trace the largest contributor to code/resource/component source rather than applying broad optimization checklists.

4. Implement the smallest change expected to reduce that measured cost while preserving behavior.

5. Re-measure in the same controlled setup and compare trace/metric, not only a score.

6. Test slow network/CPU and realistic data/content to catch hidden loading/interaction issues.

7. Run regression checks for accessibility/visual correctness and bundle/cache behavior.

8. Record threshold/budget or monitoring for regressions when the performance characteristic is important.

## Implementation patterns

- Serve responsive image variants with intrinsic dimensions and modern supported formats; avoid shipping desktop-resolution images to tiny slots.

- Subset/self-host/load fonts according to brand requirements and use fallback metrics/loading strategy that minimizes invisible text/layout shift.

- Route/feature code splitting should follow actual user navigation and avoid tiny over-fragmented chunks with request overhead.

- Use server compression/CDN caching for static versioned assets and immutable cache headers where deployment names are content-hashed.

- Virtualize extremely large lists only when DOM/render cost is proven; preserve keyboard/accessibility and search semantics.

- Batch DOM reads/writes and prefer CSS transforms/opacity for high-frequency animation where visually appropriate.

- Use request cancellation/debouncing for high-frequency search/filter calls only with clear stale/result semantics.

- Set explicit performance budgets for high-value metrics/resources where CI can enforce them deterministically.

## Failure modes

- Lighthouse-only optimization: score improves but field/user journey does not. Use traces/RUM and target bottleneck.

- Preload everything: bandwidth contention delays real critical resource. Preload only proven critical assets.

- Lazy LCP image: above-fold asset intentionally delayed. Prioritize it.

- Memoization blanket: complexity rises without profile evidence and dependencies become stale. Profile first.

- Cache privacy bug: personalized response shared due broad CDN cache. Define cache key/private semantics.

- Bundle focus tunnel: network bytes shrink while long-task runtime remains. Inspect execution/interaction.

- CLS patch with fixed heights that break responsive content. Reserve aspect/space semantically.

- Metric gaming: essential content/work deferred outside lab window. Optimize real task, not score.

## Verification

- Capture before/after in same browser/device throttling/data state and retain metric deltas.

- Inspect network waterfall for critical resource ordering/cache/compression/redirect changes.

- Inspect performance trace for long tasks, scripting/layout/paint and interaction work.

- Run bundle analyzer when JS dependency/chunk changes are involved.

- Check image/font loading and layout stability at responsive sizes.

- Verify cache headers/variants with authenticated/anonymous/localized cases as relevant.

- Run visual/accessibility regression because loading/splitting/virtualization can alter UI behavior.

- Where available, monitor field/RUM metrics after deployment and distinguish them from lab prediction.

## Completion criteria

- A measured baseline and bottleneck hypothesis drove the change.

- Before/after evidence shows improvement or at least no regression in the targeted user metric/path.

- Optimization does not sacrifice correctness, accessibility or visual hierarchy.

- Caching/loading priority and code splitting have explicit correctness semantics.

- Performance-sensitive paths have regression budgets/monitoring where justified.

- Claims distinguish lab evidence from field outcomes.

## Related skills and escalation

- Use `frontend`, framework skills and `design` for implementation tradeoffs.

- Use `backend` when TTFB/API timing is dominant and `seo-core` for public search-facing pages.

- Use `visual-qa` to catch layout/loading regressions.

- Use `source-first` for current Core Web Vitals definitions and browser/framework optimization APIs.
