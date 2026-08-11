---
slug: seo-google
description: Google Search-specific verification and optimization guidance layered
  on SEO Core.
kind: capability
keywords:
- google seo
- search console
- googlebot
- core web vitals
- rich results
- google
- rich result
- lcp
- inp
- cls
entry_sections:
- Apply when
- Core contract
---
# Google SEO Skill

## Apply when
The task explicitly targets Google Search behavior, Search Console diagnostics, Google structured-data features or Core Web Vitals.

## Core contract
- Apply SEO Core first. Use semantic HTML and ensure important text is present in the rendered DOM.
- Treat Search Console/URL Inspection/real-user measurements as evidence when available, not as a substitute for source/runtime inspection.
- Core Web Vitals currently center on LCP, INP and CLS; measure before/after rather than guessing from code size alone.
- Implement only structured-data types/features supported for the page's real visible content.
- Technical compliance improves eligibility/quality but does not guarantee indexing or ranking.

## Performance
Prioritize user-visible loading, responsiveness and layout stability. Avoid changes that improve one lab metric by degrading content correctness or accessibility. Use field data when available and lab tooling for reproducible diagnosis.

## Verification
Inspect representative URL status/rendering, Search Console evidence when accessible, structured-data validation and measured Web Vitals/performance for affected templates.
