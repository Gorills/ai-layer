from __future__ import annotations

from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.memory.navigation import build_navigation_document, extract_symbols


def test_python_navigation_keeps_symbols_but_not_default_values_or_body():
    source = """\nfrom fastapi import FastAPI\napp = FastAPI()\nSECRET = "do-not-store"\n\nclass PaymentService:\n    def create_payment(self, token="secret-default", amount: int = 10):\n        marker = "body-secret"\n        return marker\n\n@app.post("/payments")\ndef create_payment(payload, api_key="private-key"):\n    return PaymentService().create_payment(api_key)\n"""
    document = build_navigation_document(
        path="src/payments.py",
        text=source,
        language="python",
        purpose="Application source file.",
        imports=["fastapi"],
        risk_flags=[],
        content_sha256="a" * 64,
        scanner_schema=5,
    )
    text = document["navigation_text"]
    assert "PaymentService.create_payment" in text
    assert "POST /payments" in text
    assert "token=..." in text
    assert "api_key=..." in text
    assert "secret-default" not in text
    assert "private-key" not in text
    assert "body-secret" not in text
    assert "do-not-store" not in text


def test_javascript_navigation_extracts_names_without_source_bodies():
    source = """\nexport async function syncOrder(order, token = "secret") {\n  const internal = "body-secret";\n  return internal;\n}\nconst retryOrder = async (order) => order;\nclass OrderClient {}\n"""
    symbols = extract_symbols(source, "javascript")
    names = {item["name"] for item in symbols}
    assert {"syncOrder", "retryOrder", "OrderClient"} <= names
    assert all("secret" not in str(item) for item in symbols)


def test_bootstrap_uses_status_and_project_map_without_disabling_native_execution():
    bootstrap = native_bootstrap_markdown()
    assert "project_status" in bootstrap
    assert "project_search" in bootstrap
    assert "knowledge_search" in bootstrap
    assert "host-native" in bootstrap
    assert "native reads, edits, shell, tests, code search and subagents are allowed" in bootstrap
    assert "first project-related tool call MUST be `memory_context" not in bootstrap
    assert "The top-level chat is the orchestrator, not an implementation worker" not in bootstrap
