from __future__ import annotations

import re
from typing import Any

from ai_layer.epics.contracts import MAX_EPIC_SPEC_CHARS

MAX_EPIC_SPEC_EDIT_OPERATIONS = 32


def _fragment(value: Any, *, field: str, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if required and not value:
        raise ValueError(f"{field} is required")
    if len(value) > MAX_EPIC_SPEC_CHARS:
        raise ValueError(f"{field} exceeds {MAX_EPIC_SPEC_CHARS} characters")
    return value


def _unique_index(content: str, target: str, *, field: str) -> int:
    count = content.count(target)
    if count != 1:
        raise ValueError(f"{field} must match exactly once; found {count} matches")
    return content.index(target)


def _replace_unique(content: str, target: str, replacement: str, *, field: str) -> str:
    _unique_index(content, target, field=field)
    return content.replace(target, replacement, 1)


def _replace_section(content: str, *, heading: Any, body: Any, index: int) -> str:
    heading_text = _fragment(heading, field=f"edits[{index}].heading")
    match = re.fullmatch(r"(#{1,6})\s+\S.*", heading_text)
    if match is None:
        raise ValueError(
            f"edits[{index}].heading must be an exact Markdown ATX heading such as `## Failure recovery`"
        )
    lines = content.splitlines(keepends=True)
    matches = [
        line_index for line_index, line in enumerate(lines) if line.rstrip("\r\n") == heading_text
    ]
    if len(matches) != 1:
        raise ValueError(
            f"edits[{index}].heading must match exactly once; found {len(matches)} matches"
        )
    start_heading = matches[0]
    level = len(match.group(1))
    end = len(lines)
    for line_index in range(start_heading + 1, len(lines)):
        candidate = lines[line_index].rstrip("\r\n")
        candidate_match = re.match(r"^(#{1,6})\s+\S", candidate)
        if candidate_match and len(candidate_match.group(1)) <= level:
            end = line_index
            break

    normalized_body = _fragment(
        body,
        field=f"edits[{index}].content",
        required=False,
    )
    if normalized_body and not normalized_body.endswith("\n"):
        normalized_body += "\n"
    return "".join(lines[: start_heading + 1]) + normalized_body + "".join(lines[end:])


def apply_spec_edits(markdown: str, edits: list[dict]) -> str:
    """Apply deterministic document-style edits in memory.

    Every anchor is exact and must be unique in the document state produced by all
    previous edits in the same call. The caller persists only the final result, so
    the batch is atomic from the database's point of view.
    """
    if not isinstance(edits, list) or not edits:
        raise ValueError("edits must be a non-empty list")
    if len(edits) > MAX_EPIC_SPEC_EDIT_OPERATIONS:
        raise ValueError(
            f"edits supports at most {MAX_EPIC_SPEC_EDIT_OPERATIONS} operations per revision"
        )

    result = str(markdown)
    for index, raw in enumerate(edits, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"edits[{index}] must be an object")
        operation = str(raw.get("op") or "").strip().casefold()
        if operation == "replace":
            target = _fragment(raw.get("target"), field=f"edits[{index}].target")
            replacement = _fragment(
                raw.get("replacement"),
                field=f"edits[{index}].replacement",
                required=False,
            )
            if target == replacement:
                raise ValueError(f"edits[{index}] is a no-op")
            result = _replace_unique(
                result,
                target,
                replacement,
                field=f"edits[{index}].target",
            )
        elif operation == "delete":
            target = _fragment(raw.get("target"), field=f"edits[{index}].target")
            result = _replace_unique(
                result,
                target,
                "",
                field=f"edits[{index}].target",
            )
        elif operation in {"insert_before", "insert_after"}:
            target = _fragment(raw.get("target"), field=f"edits[{index}].target")
            text = _fragment(raw.get("text"), field=f"edits[{index}].text")
            _unique_index(result, target, field=f"edits[{index}].target")
            replacement = text + target if operation == "insert_before" else target + text
            result = result.replace(target, replacement, 1)
        elif operation == "replace_section":
            result = _replace_section(
                result,
                heading=raw.get("heading"),
                body=raw.get("content"),
                index=index,
            )
        else:
            raise ValueError(
                f"edits[{index}].op must be one of replace, delete, insert_before, "
                "insert_after, replace_section"
            )
        if len(result) > MAX_EPIC_SPEC_CHARS:
            raise ValueError(f"edited epic spec exceeds {MAX_EPIC_SPEC_CHARS} characters")

    if result == markdown:
        raise ValueError("edits produce no net change")
    return result
