---
slug: seo-core
description: Search-engine-neutral technical SEO engineering for crawlability, indexability,
  canonicalization, semantic content and rendering.
kind: capability
keywords:
- seo
- search
- indexing
- crawl
- canonical
- sitemap
- robots
- structured data
- schema
- search engine
- schema.org
- metadata
- title
- description
entry_sections:
- Apply when
- Core contract
---
# SEO Core Skill

## Apply when
Public pages, routing/URLs, metadata, crawl/index controls, structured data, rendering or performance changes can affect search discovery/presentation.

## Core contract
- Separate crawlability, indexability, canonicalization and ranking; fixing one does not prove another.
- Preserve stable meaningful URLs and intentional redirect behavior. Do not create duplicate crawlable URL variants casually.
- Important content and navigation must exist in accessible rendered DOM/HTML; use semantic headings, links and meaningful page structure.
- Each indexable page type needs intentional title/description/canonical/robots behavior and only supported truthful structured data.
- `robots.txt`, meta robots and canonical directives have different purposes; do not use one as a substitute without understanding the effect.
- Never promise rankings. Report verified technical state and measurements only.

## Crawling and indexing
Ensure important pages are reachable through normal links and included in Sitemap strategy when appropriate. Avoid indexing technical/search/filter/session/duplicate pages unless deliberately useful. HTTP status codes must describe reality: removed/missing pages are not successful 200 pages with error text.

## Canonical and duplicates
Determine the preferred URL for duplicate/similar content, pagination/filter variants and alternate forms. Canonical should reference a real indexable equivalent and must not accidentally point entire page classes to the home page.

## Rendering
For JavaScript-heavy sites, inspect what search engines can actually receive/render. SSR/prerendering is an architectural choice, not an automatic requirement, but critical content should not depend on fragile client-only execution without verification.

## Structured data
Use schema only when it matches visible page content and the target engine supports the relevant rich-result type. Validate generated markup and avoid duplicating conflicting schemas from several plugins/components.

## Verification
Check representative URLs: response/status, robots directives, canonical, title/description, rendered primary content, internal links, Sitemap/robots behavior and structured-data validation where applicable.
