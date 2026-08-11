---
slug: typescript
description: TypeScript boundary modeling and maintainable typing without unsafe assertion-driven
  development.
kind: stack
keywords:
- typescript
- ts
- type
- interface
- generic
- tsconfig
- typecheck
entry_sections:
- Apply when
- Core contract
---
# TypeScript Skill

## Apply when
TypeScript source, public types, runtime-boundary decoding, generics or compiler configuration changes.

## Core contract
- Follow the existing `tsconfig`, strictness and generated-type ownership; do not weaken compiler options to make one change pass.
- Model stable domain/public boundaries explicitly, but avoid type-level complexity that obscures straightforward runtime behavior.
- `unknown` at untrusted boundaries is safer than `any`; validate before narrowing when runtime data can violate compile-time assumptions.
- Avoid broad assertions (`as`, non-null `!`) used only to silence a real state problem.
- Reuse generated API/schema types when they are authoritative instead of maintaining parallel manual shapes.

## API evolution
When changing shared types, trace producers and consumers. Optionality should reflect actual runtime absence, not convenience. Discriminated unions are useful for real state alternatives; avoid giant bags of optional fields.

## Verification
Run the project's actual typecheck/build plus behavior tests. A clean compiler does not replace runtime validation for network/storage/user input.
