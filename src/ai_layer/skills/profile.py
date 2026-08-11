from __future__ import annotations

FRAMEWORK_SIGNALS = {
    "django": ("django", "djangorestframework", "drf"),
    "fastapi": ("fastapi",),
    "flask": ("flask",),
    "sqlalchemy": ("sqlalchemy",),
    "postgresql": ("postgres", "psycopg", "asyncpg"),
    "express": ("express",),
    "nestjs": ("@nestjs", "nestjs"),
    "fastify": ("fastify",),
    "react": ("react", "next"),
    "vue": ("vue", "nuxt"),
    "svelte": ("svelte", "@sveltejs"),
    "laravel": ("laravel/framework", "laravel"),
    "stripe": ("stripe",),
    "yookassa": ("yookassa", "yoo-kassa", "yoo_kassa"),
}

TASK_SIGNAL_TERMS = {
    "webhook": ("webhook", "callback"),
    "signature_verification": ("verify_webhook_signature", "signature", "hmac"),
    "csrf_exemption": ("csrf_exempt",),
    "idempotency": ("idempotency_key", "idempotency", "idempotent"),
    "integrity_error": ("integrityerror", "integrity_error"),
    "transaction": ("transaction.atomic", "begin_transaction", "atomic("),
    "pagination": ("pagination", "page_size", "paginator"),
    "authentication": ("authenticate", "login", "jwt", "oauth", "session"),
    "authorization": ("permission", "authorize", "rbac", "ownership", "tenant"),
    "migration": ("alembic", "migration", "schema change", "backfill"),
    "file_boundary": ("upload", "archive", "extract", "path traversal", "filesystem"),
    "payment_provider": ("stripe", "yookassa", "payment provider", "payment_provider"),
    "stub_or_placeholder": ("notimplemented", "not implemented", "todo", "stub", "pass\n"),
}


def _dependency_text(dependencies: dict[str, list[str]]) -> str:
    return " ".join(str(item) for values in dependencies.values() for item in values).casefold()


def _frameworks(languages: dict[str, int], dependencies: dict[str, list[str]]) -> list[str]:
    dep_text = _dependency_text(dependencies)
    found = [
        name
        for name, needles in FRAMEWORK_SIGNALS.items()
        if any(needle.casefold() in dep_text for needle in needles)
    ]
    if "gdscript" in {str(lang).casefold() for lang in languages}:
        found.append("godot")
    return sorted(set(found))


def detect_project_profile(languages: dict[str, int], dependencies: dict[str, list[str]]) -> dict:
    return {
        "languages": sorted(languages, key=lambda name: languages[name], reverse=True),
        "frameworks": _frameworks(languages, dependencies),
        "dependency_ecosystems": sorted(dependencies),
    }


def extract_task_evidence(memory_hits: list[dict], max_files: int = 6) -> list[dict]:
    evidence: list[dict] = []
    seen: set[str] = set()
    for hit in memory_hits:
        path = hit.get("source_path")
        if not path or path in seen:
            continue
        low = (str(path) + "\n" + str(hit.get("content", ""))).casefold()
        signals = [
            name
            for name, needles in TASK_SIGNAL_TERMS.items()
            if any(needle.casefold() in low for needle in needles)
        ]
        risk_flags = list((hit.get("meta") or {}).get("risk_flags") or [])
        if signals or risk_flags:
            evidence.append({"path": path, "signals": signals, "risk_flags": risk_flags})
            seen.add(path)
        if len(evidence) >= max_files:
            break
    return evidence
