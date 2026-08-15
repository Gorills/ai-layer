from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_layer.db.work_models import WORK_ASSURANCE, WORK_KINDS, WORK_STATUSES
from ai_layer.memory.knowledge_contract import KNOWLEDGE_CATEGORIES, KNOWLEDGE_STATUSES
from ai_layer.skills.constants import VALID_SCOPES
from ai_layer.tasks.constants import MAX_TASK_GOAL_CHARS
from ai_layer.work.evidence import WORK_CHECK_STATUSES, WORK_PATH_LIMIT, WORK_PATH_MAX_CHARS
from ai_layer.work.service import WORK_GOAL_MAX_CHARS, WORK_SUMMARY_MAX_CHARS


def _openapi() -> dict:
    from ai_layer.api.app import create_app

    return create_app().openapi()


def _schema_enum(schema: dict) -> set[str]:
    if "enum" in schema:
        return set(schema["enum"])
    if schema.get("const") is not None:
        return {schema["const"]}
    for item in schema.get("anyOf") or schema.get("oneOf") or []:
        if "enum" in item:
            return set(item["enum"])
        if item.get("const") is not None:
            return {item["const"]}
    return set()


def _query_schema(openapi: dict, path: str, name: str) -> dict:
    for parameter in openapi["paths"][path]["get"]["parameters"]:
        if parameter["name"] == name:
            return parameter["schema"]
    raise AssertionError(f"missing query parameter {name} on {path}")


def _mcp_tool(name: str):
    from ai_layer.mcp.server import mcp

    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool


def _mcp_property(name: str, field: str) -> dict:
    schema = _mcp_tool(name).parameters
    props = schema.get("properties") or {}
    assert field in props, f"{name} missing {field}: {sorted(props)}"
    return props[field]


def _deref(schema: dict, root: dict) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    node: dict = root
    for part in ref.split("/")[1:]:
        node = node[part]
    return node


def test_openapi_contract_versions_are_const_and_required():
    schema = _openapi()
    work = schema["components"]["schemas"]["WorkListRead"]
    detail = schema["components"]["schemas"]["WorkDetailRead"]
    activity = schema["components"]["schemas"]["ActivityRead"]
    assert work["properties"]["contract_version"]["const"] == 1
    assert detail["properties"]["contract_version"]["const"] == 1
    assert activity["properties"]["contract_version"]["const"] == 2
    assert "contract_version" in work["required"]
    assert "contract_version" in detail["required"]
    assert "contract_version" in activity["required"]


def test_openapi_work_and_activity_query_enums_match_runtime():
    schema = _openapi()
    status = _query_schema(schema, "/api/v1/dashboard/work", "status")
    assert _schema_enum(status) == set(WORK_STATUSES)
    mode = _query_schema(schema, "/api/v1/dashboard/activity", "mode")
    assert _schema_enum(mode) == {"milestones", "all"}
    importance = _query_schema(schema, "/api/v1/dashboard/activity", "importance")
    assert _schema_enum(importance) == {"low", "normal", "high"}
    assurance = _query_schema(schema, "/api/v1/dashboard/activity", "assurance")
    assert _schema_enum(assurance) == set(WORK_ASSURANCE)
    event_type = _query_schema(schema, "/api/v1/dashboard/activity", "event_type")
    assert event_type.get("maxLength") == 96 or any(
        item.get("maxLength") == 96 for item in event_type.get("anyOf") or []
    )
    work_item = schema["components"]["schemas"]["WorkItemRead"]
    assert _schema_enum(work_item["properties"]["kind"]) == set(WORK_KINDS)
    assert _schema_enum(work_item["properties"]["status"]) == set(WORK_STATUSES)
    assert _schema_enum(work_item["properties"]["assurance"]) == set(WORK_ASSURANCE)


def test_dashboard_query_schema_rejects_invalid_work_status_and_activity_mode():
    from ai_layer.api.app import create_app

    client = TestClient(create_app())
    work = client.get("/api/v1/dashboard/work?status=working")
    activity = client.get("/api/v1/dashboard/activity?mode=debug")
    assert work.status_code == 422
    assert activity.status_code == 422


def test_mcp_work_and_task_schemas_reject_invalid_enums_and_overlong_text():
    kind = _mcp_property("work_begin", "kind")
    assert _schema_enum(kind) == set(WORK_KINDS)
    goal = _mcp_property("work_begin", "goal")
    assert goal["maxLength"] == WORK_GOAL_MAX_CHARS
    assert _mcp_property("work_complete", "summary")["maxLength"] == WORK_SUMMARY_MAX_CHARS
    checks = _mcp_property("work_checkpoint", "checks")
    check_items = next(item for item in checks["anyOf"] if item.get("type") == "array")["items"]
    check_schema = _deref(check_items, _mcp_tool("work_checkpoint").parameters)
    assert _schema_enum(check_schema["properties"]["status"]) == set(WORK_CHECK_STATUSES)
    assert check_schema.get("additionalProperties") is False
    paths = _mcp_property("work_checkpoint", "reviewed_paths")
    path_schema = next(item for item in paths["anyOf"] if item.get("type") == "array")
    assert path_schema["maxItems"] == WORK_PATH_LIMIT
    assert path_schema["items"]["maxLength"] == WORK_PATH_MAX_CHARS
    workflow = _mcp_property("task_create", "workflow")
    assert _schema_enum(workflow) == {
        "auto",
        "micro",
        "standard",
        "discovery_first",
        "analysis_only",
    }
    assert _schema_enum(_mcp_property("task_create", "risk")) == {"auto", "low", "normal", "high"}
    assert _schema_enum(_mcp_property("task_create", "complexity")) == {
        "auto",
        "low",
        "normal",
        "high",
    }
    assert _schema_enum(_mcp_property("task_create", "uncertainty")) == {
        "auto",
        "low",
        "normal",
        "high",
    }
    assert _schema_enum(_mcp_property("task_create", "cost_policy")) == {
        "auto",
        "economy",
        "balanced",
        "quality",
    }
    assert _mcp_property("task_create", "goal")["maxLength"] == MAX_TASK_GOAL_CHARS
    status = _mcp_property("knowledge_list", "status")
    assert _schema_enum(status) == set(KNOWLEDGE_STATUSES)
    assert _mcp_property("knowledge_list", "limit")["maximum"] == 200
    category = _mcp_property("knowledge_draft_upsert", "category")
    assert _schema_enum(category) == set(KNOWLEDGE_CATEGORIES)
    search_limit = _mcp_property("project_search", "limit")
    assert search_limit["minimum"] == 1
    assert search_limit["maximum"] == 20
    variants = _mcp_property("project_search", "query_variants")
    variant_schema = next(item for item in variants["anyOf"] if item.get("type") == "array")
    assert variant_schema["maxItems"] == 1
    assert _schema_enum(_mcp_property("skill_remove", "scope")) == set(VALID_SCOPES)

    work_begin = _mcp_tool("work_begin")
    try:
        work_begin.fn_metadata.validate_arguments({"goal": "ship it", "kind": "hotfix"})
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid work kind must fail MCP schema validation")
    try:
        work_begin.fn_metadata.validate_arguments({"goal": "x" * (WORK_GOAL_MAX_CHARS + 1)})
    except ValidationError:
        pass
    else:
        raise AssertionError("overlong work goal must fail MCP schema validation")
    work_complete = _mcp_tool("work_complete")
    try:
        work_complete.fn_metadata.validate_arguments(
            {"work_key": "W-0001", "summary": "done", "map_disposition": {}}
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("map_disposition without status must fail MCP schema validation")
    work_complete.fn_metadata.validate_arguments(
        {
            "work_key": "W-0001",
            "summary": "done",
            "map_disposition": {"status": "pending"},
        }
    )
    task_create = _mcp_tool("task_create")
    try:
        task_create.fn_metadata.validate_arguments({"goal": "managed work", "workflow": "ad-hoc"})
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid task workflow must fail MCP schema validation")
