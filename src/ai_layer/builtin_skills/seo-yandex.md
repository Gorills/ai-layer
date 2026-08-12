---
slug: seo-yandex
description: Yandex Search engineering for Webmaster diagnostics, crawl/index controls, site structure, metadata, mobile usability and evidence-based optimization.
kind: domain
keywords:
- yandex seo
- yandex search
- webmaster
- yandexbot
- robots
- sitemap
- indexing
- region
- snippet
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Yandex Search SEO Skill

## Apply when

Use when the task specifically targets Yandex Search crawling, indexing, site diagnostics or search appearance. Apply on top of `seo-core` and verify current Yandex Webmaster documentation because directives and diagnostics can change.

## Core contract

- Use Yandex Webmaster diagnostics and current official recommendations as evidence, not generic SEO folklore.

- Make important pages reachable through ordinary links and coherent site structure; deep/orphaned content is harder for crawlers and users to discover.

- Keep robots, sitemaps, status codes, canonical/index directives and internal links consistent with the intended indexable URL set.

- Titles/descriptions and visible content should be unique, useful and representative; duplicate metadata across many pages reduces clarity.

- Mobile usability and accessible, understandable presentation matter to users and are part of a technically healthy search-facing site.

- Do not use 429 or 5xx as a normal signal for deleted/nonexistent pages; return appropriate permanent/not-found behavior according to current guidance.

- Yandex Webmaster site settings such as region/site ownership are operational metadata, not substitutes for relevant content and technical accessibility.

- The crawler cannot rely on user-only interactions such as registration/SMS/action to access core indexable content; design public pages accordingly.

- Measure indexing/diagnostic changes in Webmaster and logs after deployment; do not promise exact ranking movement.

- Prefer current Yandex documentation for Yandex-specific behavior and avoid assuming Google-specific directives/features behave identically.

## Evidence to inspect

- Yandex Webmaster diagnostics, page status/indexing tools and crawl information when available.

- Current Yandex Webmaster recommendations for robots, sitemap, metadata, site structure and search appearance.

- Server logs for Yandex robot requests/status.

- Rendered/server HTML and ordinary internal links.

- Robots/sitemap/status/canonical/index directives for representative URL classes.

- Regional/mobile/site settings relevant to the site's product audience.

## Decision rules

- If Webmaster reports missing/invalid robots or sitemap, fix syntax/accessibility and ensure directives match the intended index policy.

- If many pages have duplicate title/description, generate meaningful page-specific metadata from canonical content rather than artificial keyword variations.

- If content is only reachable after interactive action/registration, decide whether it should be publicly indexable and expose a suitable public route if yes.

- If a URL is deleted, return a correct 4xx or redirect to a truly relevant replacement rather than generic success/home redirect.

- If site structure buries important pages deeply, improve user/internal-link hierarchy rather than manufacturing sitemap-only discovery.

- If a Yandex-specific claim conflicts with current official docs, follow the official documented behavior for the current service.

- If regional targeting is relevant, configure it intentionally and ensure content/business data supports the region rather than treating the setting as a ranking trick.

- If technical checks pass but ranking is weak, do not keep adding directives; investigate content relevance/quality/competition as a separate problem.

## Workflow

1. Run `seo-core` audit, then identify Yandex-specific diagnostics/objective.

2. Review current official Yandex Webmaster documentation for the exact warning/directive.

3. Inspect representative page status, rendered metadata/content and internal-link path.

4. Fix contradictory crawl/index/status/sitemap signals at their canonical generator/source.

5. Address user-facing structure/mobile/content presentation issues that the diagnostic exposes.

6. Validate robots/sitemap and page status locally/crawler-side.

7. After deployment, use Webmaster tools/logs to verify robot access/indexing/diagnostic resolution.

8. Report technical change and observed diagnostic/index evidence separately from ranking predictions.

## Implementation patterns

- Use a clear hierarchical internal link structure where each important document belongs to a discoverable section.

- Generate unique titles/descriptions from the page's actual primary content and intent.

- Keep robots.txt simple, intentional and testable; broad disallow rules can hide content needed for indexing/debugging.

- Generate sitemaps from canonical indexable records rather than crawling arbitrary URL parameters.

- Treat Yandex Webmaster recommendations as prioritized diagnostic input and confirm each against product intent before changing.

- Serve important textual information directly on the public page without requiring user-only actions when indexing is desired.

## Failure modes

- Yandex=Google assumption: engine-specific feature/directive copied without official verification. Check Yandex docs.

- Sitemap as architecture: orphan pages only appear in XML. Build crawlable internal links.

- Duplicate metadata factory: keyword-swapped titles create low-value differences. Reflect real page content.

- Wrong missing-page status: 200/5xx used for permanently absent resource. Return appropriate 4xx/relevant redirect.

- Robots overblocking: diagnostics/indexing fail because critical routes/resources are disallowed. Align policy.

- Ranking promise: Webmaster fix is claimed to guarantee positions. Measure indexing/diagnostic outcome only.

- Interactive gate: crawler cannot access content without action. Provide public content or accept non-indexing.

- Region setting as trick: metadata setting used without real regional relevance. Align product/content.

## Verification

- Validate robots.txt and sitemap accessibility/syntax and URL set.

- Crawl representative pages and inspect status, title, description, canonical/index directives and internal links.

- Use current Yandex Webmaster page/diagnostic tools when access exists.

- Check Yandexbot server logs for unexpected 4xx/5xx/redirect loops/resource blocks.

- Verify mobile/reflow and content availability without user-only interaction for indexable pages.

- Check deleted/nonexistent routes return intended permanent status behavior.

- Monitor Webmaster diagnostic/index changes after deployment.

- Avoid claiming search-position outcome before longitudinal evidence.

## Completion criteria

- Yandex-specific implementation follows current official Webmaster guidance.

- Important indexable pages are crawlably linked and technically accessible.

- Robots/sitemap/status/metadata/index signals match product intent.

- Webmaster diagnostics/logs provide post-change evidence where accessible.

- Ranking expectations are kept separate from technical correctness.

## Related skills and escalation

- Always combine with `seo-core`; use `html`/`web-performance` for page implementation quality.

- Use `source-first` for current Yandex-specific directives and Webmaster behavior.

- Use `documentation` for operational site-verification/monitoring runbooks where needed.

- Escalate content/region/business strategy decisions rather than encoding them as technical SEO hacks.
