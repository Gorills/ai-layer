---
slug: seo-core
description: Technical SEO engineering for crawlability, indexability, canonicalization, internal linking, metadata, structured data and measurable search hygiene.
kind: domain
keywords:
- seo
- technical seo
- crawl
- index
- canonical
- robots
- sitemap
- metadata
- structured data
- internal links
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Technical SEO Core Skill

## Apply when

Use for public web pages where organic search discoverability matters, especially route/template changes, site migrations, metadata systems, faceted navigation, pagination, canonicals, robots directives, sitemaps and structured data. Do not apply ranking folklore blindly to authenticated/private application screens.

## Core contract

- Serve users first and make important public content discoverable, crawlable and understandable to search engines; technical SEO cannot compensate for absent or low-value content.

- Determine which URLs should be indexable before generating canonicals, sitemaps or robots rules. Indexability is a product/content decision with technical enforcement.

- Canonicalization must identify the preferred equivalent URL without contradicting redirects, internal links, sitemap entries or indexing directives.

- `robots.txt` controls crawling, not a guaranteed method for removing an already indexed URL; use appropriate HTTP/meta indexing controls for indexability.

- Important pages need ordinary crawlable links and coherent site structure; JavaScript-only discovery or orphan URLs reduce reliability across crawlers.

- Titles/descriptions should be unique and representative; avoid templated duplication that tells search systems/users little about page differences.

- HTTP status and redirect semantics matter: deleted/nonexistent pages should not masquerade as successful soft-404 pages; permanent moves should redirect coherently.

- Structured data must match visible page content and the relevant search engine's current eligibility rules; markup is not a ranking guarantee.

- Sitemaps are a discovery aid and should contain canonical indexable URLs with trustworthy timestamps where maintained.

- Measure with crawl/index/search console/webmaster evidence and logs; do not claim ranking outcomes from code changes alone.

## Evidence to inspect

- Public route inventory/templates and which pages product owners intend to index.

- Rendered/server HTML: title, description, canonical, robots directives, headings, internal links and structured data.

- HTTP status/redirect chains and duplicate URL variants (scheme, host, slash, params, filters).

- `robots.txt`, XML sitemaps and generated URL feeds.

- Search engine inspection tools/logs for crawl/index problems when access exists.

- JavaScript rendering dependence and whether critical content/links exist in initial/server-rendered HTML.

## Decision rules

- If two URLs contain equivalent content, choose one preferred canonical and align internal links/sitemap/redirects where practical.

- If a URL must not appear in search, use `noindex`/authentication/removal semantics appropriate to the page; do not rely only on robots disallow.

- If a page is permanently moved, use a permanent redirect to the closest relevant replacement and update internal links.

- If a faceted/filter URL space is effectively infinite, define crawl/index policy before exposing every combination as links.

- If content is private/user-specific, keep it out of public indexing rather than trying to optimize it.

- If a page is important but only reachable via JS event without anchor semantics, add a crawlable link/navigation path.

- If structured data is proposed, verify the current official supported type/required properties and that visible content actually supports it.

- If title/description generation produces large duplicates, derive them from meaningful page-specific content or simplify template taxonomy.

## Workflow

1. Inventory public URL classes and mark indexable, canonical-only, redirected, noindex/private and intentionally crawl-blocked.

2. Inspect actual server/rendered output and status behavior for representative URLs in each class.

3. Normalize host/scheme/path/query policy and align redirects/canonical/internal links.

4. Fix title/description/headings and crawlable internal linking around real user information architecture.

5. Generate sitemaps from authoritative canonical indexable URL sources and keep robots directives consistent.

6. Add only relevant structured data validated against current engine documentation.

7. Run a crawler/link/status/metadata validation and inspect rendered output.

8. Use Google/Yandex webmaster tools or logs where available to verify crawl/index effects; report ranking outcomes as external/longitudinal rather than guaranteed.

## Implementation patterns

- Generate metadata from explicit route/content models rather than each template hand-writing slightly different canonical logic.

- Centralize canonical URL construction so host/scheme/trailing slash/query normalization cannot drift.

- Use ordinary `<a href>` internal links with descriptive anchor text for key navigation/content relationships.

- Keep pagination/filter navigation bounded and user-useful; do not manufacture millions of thin combinatorial pages.

- Build XML sitemaps in bounded chunks when URL count is large and include only canonical indexable URLs.

- Use 404/410 for genuinely gone content when no meaningful replacement exists instead of redirecting everything to home.

- Keep hreflang/internationalization only if multiple localized equivalents exist and reciprocal/URL semantics are maintainable.

- Validate structured data with official tools but also inspect whether markup reflects visible page truth.

## Failure modes

- Robots-as-noindex: blocked URL may remain indexed without fresh directive/content. Use correct index control.

- Canonical contradiction: canonical says A, sitemap/internal links say B and redirect says C. Align signals.

- Soft 404: missing product/article returns 200 generic page. Return meaningful status/replacement behavior.

- Infinite facets: crawler spends budget on low-value parameter combinations. Bound navigation/index policy.

- Metadata cloning: thousands of pages share same title/description. Generate meaningful differentiation.

- JS-only links: users/crawlers need events to discover routes. Use semantic anchors.

- Schema spam: structured data describes content not visible/eligible. Remove or correct.

- Ranking promise: technical fix is claimed to guarantee traffic/position. Report implementation/index evidence, not guaranteed ranking.

## Verification

- Crawl representative site/routes and check status, redirects, canonical, robots, title/description and internal-link discoverability.

- Inspect raw/server-rendered and hydrated HTML for critical metadata/content.

- Validate robots/sitemap syntax and ensure sitemap URLs are canonical/indexable/successful.

- Test duplicate URL variants and confirm preferred redirect/canonical behavior is consistent.

- Test nonexistent/deleted pages for correct status and useful user experience.

- Validate structured data using current official engine tools/guidelines when present.

- Check mobile/render performance/accessibility because search-facing pages still need good user experience.

- Where tool access exists, use URL inspection/webmaster diagnostics after deployment and distinguish crawl/index evidence from ranking outcomes.

## Completion criteria

- Public URL classes have an intentional crawl/index/canonical policy.

- Canonical, redirects, internal links, sitemap and robots/index directives do not contradict each other.

- Important content/routes are crawlably linked and return appropriate status codes.

- Metadata is meaningful and structured data is truthful/currently valid where used.

- Technical SEO verification is based on rendered/status/crawl evidence.

- No ranking guarantee or speculative tactic is presented as fact.

## Related skills and escalation

- Use `seo-google` and `seo-yandex` for engine-specific official-tool/details after this shared foundation.

- Use `html`, `accessibility` and `web-performance` for page semantics and user experience.

- Use `source-first` because search engine guidelines/features change.

- Escalate product decisions about which content should be public/indexable rather than guessing.
