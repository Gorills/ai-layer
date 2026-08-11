---
slug: html
description: Semantic HTML, forms, document structure, native interaction and search/accessibility-friendly
  markup.
kind: stack
keywords:
- html
- semantic
- markup
- form
- heading
- link
- button
- dialog
- table
- metadata
entry_sections:
- Apply when
- Core contract
---
# HTML Skill

## Apply when
Markup structure, forms, navigation, interactive controls, metadata, content hierarchy or server-rendered templates change.

## Core contract
- Use native semantic elements for their real behavior: links navigate, buttons act, labels identify controls, headings describe hierarchy.
- Do not recreate native controls with clickable `div`/`span` elements unless a genuine custom-widget requirement exists and keyboard/ARIA behavior is implemented.
- Keep important user/search content in the actual DOM and preserve meaningful source order independent of CSS layout.
- Forms need explicit labels, suitable input types/autocomplete, validation/error association and predictable submit behavior.
- Reuse the project's template/component conventions and avoid markup churn unrelated to the task.

## Document and content structure
Use one coherent heading hierarchy based on content, not visual size. Prefer landmarks such as `main`, `nav`, `header`, `footer`, `aside` when they describe the page. Tables are for tabular relationships, not layout.

## Media
Provide useful alternative text for informative images and empty alt text for purely decorative images. Reserve dimensions/aspect ratio where possible to avoid layout shift. Captions/transcripts belong to content requirements, not decorative ARIA.

## Metadata and SEO
When a public page changes, preserve/verify title, description, canonical/robots and structured-data mechanisms already used by the project. Do not add duplicate competing metadata systems.

## Verification
Inspect rendered DOM, keyboard behavior, form errors, heading/landmark structure and responsive reading order rather than judging template source alone.
