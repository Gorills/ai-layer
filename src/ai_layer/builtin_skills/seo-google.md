---
slug: seo-google
description: Google Search engineering grounded in Search Essentials, crawl/index controls, canonical signals, structured data and Search Console evidence.
kind: domain
keywords:
- google seo
- google search
- search console
- googlebot
- search essentials
- rich results
- canonical
- indexing
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Google Search SEO Skill

## Apply when

Use when the task specifically targets Google Search discovery, indexing, appearance or diagnostics. Apply on top of `seo-core`; consult current Google Search Central documentation because supported structured-data features and guidance can change.

## Core contract

- Follow Google Search Essentials and people-first content principles; there is no technical trick that guarantees first position or inclusion.

- Use URL Inspection/Search Console evidence where available to distinguish discovered, crawled, rendered, indexed and search-performance issues.

- Google generally discovers pages through crawlable links and sitemaps; submission tools are aids, not substitutes for a coherent crawlable site.

- Canonical is a signal among consistent site signals. Redirects, canonical tags, internal links and sitemap should converge on the preferred URL.

- Use `noindex` on pages Google can crawl when removal from indexing is desired; blocking crawling can prevent Google from seeing a noindex directive.

- Structured data must follow the current Google documentation for the specific search feature and represent visible truthful page content.

- Rendering matters for JavaScript sites; ensure Google can access required resources and that critical content/links are present in a reliably renderable form.

- Core Web Vitals/page experience can be useful quality signals/UX diagnostics, but do not reduce SEO to one performance score.

- Avoid doorway, scaled thin or search-engine-first content strategies; technical implementation should support genuinely useful pages.

- Measure changes over time in Search Console/logs/analytics, controlling for external factors; ranking is not deterministically testable in CI.

## Evidence to inspect

- Current Google Search Central docs for the exact feature/directive/structured-data type.

- Search Console URL Inspection, indexing reports, enhancement/rich-result reports and performance data when accessible.

- Googlebot access/status in server/CDN logs.

- Rendered HTML and resource accessibility for JavaScript-heavy pages.

- Sitemap/canonical/redirect/internal-link consistency.

- Rich Results Test or other current Google validation tool output where applicable.

## Decision rules

- If a page should be removed from Google but remains accessible, use supported noindex/removal semantics and allow crawling long enough for the directive to be seen.

- If duplicates exist, choose one preferred URL and align permanent redirects/canonical/internal links/sitemap rather than relying on canonical alone.

- If a rich-result feature is requested, first confirm Google currently supports it for the content type and market/context; do not add schema because a generic schema.org type exists.

- If JavaScript rendering hides critical content until user interaction, render/provide important content and links in a crawler-accessible way.

- If Search Console says crawled-not-indexed, investigate content/duplication/quality/canonical/server issues rather than repeatedly resubmitting unchanged URL.

- If site migration changes domain/path, plan redirects, canonicals, sitemaps, internal links and monitoring as one migration.

- If an SEO claim comes from unofficial ranking folklore, verify against current official Google guidance and user/site evidence before implementing.

- If generated content is used, judge usefulness/original value and policy compliance rather than assuming generation method alone decides ranking.

## Workflow

1. Start with `seo-core` URL/indexability audit and identify the Google-specific symptom or target.

2. Read current official Google docs for the relevant directive, Search feature or migration behavior.

3. Inspect representative URLs in rendered HTML plus Search Console/URL Inspection/logs when available.

4. Fix underlying crawl/status/canonical/content/render issue rather than optimizing around the diagnostic label.

5. Validate structured data/rich-result eligibility with official tooling if used.

6. Deploy and submit/update sitemap or inspection only as appropriate; do not spam submission as a substitute for fixes.

7. Monitor indexing/coverage/performance after crawl cycles and compare to baseline.

8. Report technical evidence separately from ranking/traffic outcomes that require time and are influenced by competition/content.

## Implementation patterns

- Use Google-supported canonical methods consistently: redirects and `rel=canonical` plus canonical URLs in internal links/sitemaps.

- Keep Googlebot access to CSS/JS needed for rendering unless there is a deliberate security/crawl reason otherwise.

- Use Search Console to prioritize real indexed/crawled URL problems instead of theoretical checklist issues.

- For migrations, keep redirects long enough for users/search systems and avoid redirect chains.

- Use structured-data generation from the same canonical content model displayed to users to prevent markup/content drift.

- Keep title links/snippet inputs descriptive but understand Google may generate search appearance from multiple page signals.

## Failure modes

- Guaranteed-ranking tactic: code change promised to produce position. Replace with standards/evidence-based objective.

- Search Console resubmit loop: URL repeatedly requested for indexing without fixing quality/canonical/server issue. Diagnose cause.

- Noindex blocked by robots: crawler cannot see directive. Adjust crawl/index controls coherently.

- Rich-result cargo cult: unsupported/irrelevant schema added. Verify current Google feature docs.

- JS hidden content: important page exists only after interaction. Make content crawlably renderable.

- Migration redirect chain: multiple hops/partial old URLs lose clarity. Map old→best new directly.

- Canonical-only cleanup: internal links/sitemap still point to duplicates. Align all signals.

- Search-engine-first pages: generated thin pages target queries without user value. Reconsider product/content strategy.

## Verification

- Use current Google Search Central docs as source of truth for changed Google-specific behavior.

- Inspect actual Google-facing HTML/status/robots/canonical and resources.

- Use URL Inspection/Rich Results validation when access/tooling exists; record result and environment.

- Validate sitemap and redirect mapping for site migrations.

- Check server logs for Googlebot status/resource errors when diagnosing crawl failures.

- Track Search Console indexing/performance after deployment rather than claiming immediate ranking success.

- Verify structured data mirrors visible content and passes applicable current validation.

- Keep a baseline so post-change trends can be distinguished from preexisting issues.

## Completion criteria

- Google-specific changes are grounded in current official Search Central guidance.

- The technical crawl/index/render/canonical issue is reproduced and corrected with observable evidence.

- Structured-data/search-feature implementation is currently eligible and truthful where applicable.

- Monitoring plan distinguishes technical correctness from later ranking/traffic outcomes.

- No unsupported guarantee or folklore-driven change remains.

## Related skills and escalation

- Always combine with `seo-core` for shared technical SEO fundamentals.

- Use `web-performance`, `html` and `accessibility` for page experience and render quality.

- Use `source-first` whenever Google feature/status guidance may have changed.

- Escalate content/marketing strategy decisions that cannot be solved by code.
