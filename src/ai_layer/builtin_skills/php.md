---
slug: php
description: PHP/Composer engineering discipline for maintainable modern and legacy
  applications without accidental architecture rewrites.
kind: stack
keywords:
- php
- composer
- autoload
- phpunit
- fpm
- psr
- php-fpm
- namespace
- phpstan
- psalm
entry_sections:
- Apply when
- Core contract
---
# PHP Skill

## Apply when
PHP source, Composer dependencies/autoloading, PHP-FPM/CLI behavior, framework-neutral PHP services, or PHP tests change.

## Core contract
- Follow the project's supported PHP version, Composer ownership, namespace/autoload structure, coding standard, static analysis and tests.
- Preserve the existing architectural style in legacy code. A small feature or bugfix is not permission to convert the project to a new framework/pattern.
- Keep request/CLI/worker lifecycle differences explicit; avoid hidden mutable static/global state that leaks across long-running workers.
- Use parameterized database APIs/framework query builders and framework-native validation/security boundaries.
- Do not edit Composer-generated lock/autoload files manually.

## Types and errors
Match the project's `strict_types`, type declarations and error policy. Add types at stable boundaries when compatible; do not create partial typing churn across unrelated files. Catch exceptions only where the layer can recover, translate, retry, or add meaningful context; do not swallow `Throwable` broadly.

## Composer and autoloading
Respect `composer.json` namespaces and package constraints. Prefer existing dependencies before adding another package. Regenerate autoload metadata with Composer when required. Treat `composer.lock` as the reproducible application dependency graph when the repository commits it.

## Runtime lifecycle
Understand PHP-FPM request isolation versus queue/server processes that remain alive. Long-running workers must not assume per-request cleanup of static state, DB connections, caches, or singleton objects. Ensure resources and transactions are closed on exceptional paths.

## Legacy changes
Trace callers, side effects, database writes and externally visible quirks before refactoring. Prefer characterization tests and small seams over broad class hierarchies or parallel replacements. Keep formatting/renames out of behavioral fixes unless they are necessary.

## Verification
Run the configured PHPUnit/Pest/static-analysis/style gates that cover the change. For persistence or HTTP behavior, exercise the real framework/database boundary where unit mocks cannot prove compatibility.
