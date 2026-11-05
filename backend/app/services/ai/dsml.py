"""Text tool-call fallback for providers that return markup as content.

deepseek-v4-pro can put DSML or ``<tool_call>{...}</tool_call>`` markup in
``message.content`` instead of returning OpenAI ``tool_calls``. The markup is
not meant to be shown to users, so normalize it into ToolCall objects and strip
it from the reply text.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import List, Tuple

from app.services.ai.base import ToolCall

logger = logging.getLogger(__name__)

_DSML_TAG = r"<\|+\s*DSML\s*\|+\s*"
_ATTR_RE = re.compile(r"([\w-]+)=[\"']([^\"']*)[\"']")
_ROOT_RE = re.compile(
    _DSML_TAG + r"(?:tool_)?calls\b[^>]*>(.*?)</\|+\s*DSML\s*\|+\s*(?:tool_)?calls\s*>",
    re.IGNORECASE | re.DOTALL,
)
_INVOKE_RE = re.compile(
    _DSML_TAG + r"invoke\b([^>]*)>(.*?)</\|+\s*DSML\s*\|+\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_PARAM_RE = re.compile(
    _DSML_TAG + r"parameter\b([^>]*)>(.*?)</\|+\s*DSML\s*\|+\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ANY_TAG_RE = re.compile(r"</?\|+\s*DSML\s*\|+\s*[^>]*>", re.IGNORECASE)
_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call\b[^>]*>(.*?)</tool_call\s*>", re.IGNORECASE | re.DOTALL,
)
_XML_TOOL_CALL_TAG_RE = re.compile(r"</?tool_call\b[^>]*>", re.IGNORECASE)


def _normalize(content: str) -> str:
    return (
        (content or "")
        .replace("｜", "|")
        .replace("＜", "<")
        .replace("＞", ">")
    )


def _attributes(raw: str) -> dict:
    return {key.lower(): value for key, value in _ATTR_RE.findall(raw)}


def _parameter_value(raw: str, string_attr: str) -> object:
    value = html.unescape(raw.strip())
    if string_attr.lower() == "false":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _load_json_payload(raw: str) -> object:
    payload = raw.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*", "", payload, flags=re.IGNORECASE)
        payload = re.sub(r"\s*```$", "", payload)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start, end = payload.find("{"), payload.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(payload[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def _xml_tool_calls(body: str, offset: int = 0) -> List[ToolCall]:
    payload = _load_json_payload(html.unescape(body))
    items = payload if isinstance(payload, list) else [payload]
    calls: List[ToolCall] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("tool") or "").strip()
        arguments = item.get("arguments", item.get("args", {}))
        if isinstance(arguments, str):
            arguments = _load_json_payload(arguments) or {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        if name:
            calls.append(ToolCall(
                id=f"xml_{offset + len(calls) + 1}",
                name=name,
                arguments=arguments,
            ))
    return calls


def parse_dsml_tool_calls(content: str) -> Tuple[str, List[ToolCall]]:
    upper = (content or "").upper()
    if "DSML" not in upper and "<TOOL_CALL" not in upper:
        return content or "", []

    normalized = _normalize(content)
    calls: List[ToolCall] = []
    for invoke in _INVOKE_RE.finditer(normalized):
        invoke_attrs = _attributes(invoke.group(1))
        name = html.unescape((invoke_attrs.get("name") or "").strip())
        if not name:
            continue
        arguments: dict = {}
        for param in _PARAM_RE.finditer(invoke.group(2)):
            param_attrs = _attributes(param.group(1))
            param_name = html.unescape((param_attrs.get("name") or "").strip())
            if not param_name:
                continue
            arguments[param_name] = _parameter_value(
                param.group(2), param_attrs.get("string") or "",
            )
        calls.append(ToolCall(
            id=f"dsml_{len(calls) + 1}",
            name=name,
            arguments=arguments,
        ))

    for xml_call in _XML_TOOL_CALL_RE.finditer(normalized):
        calls.extend(_xml_tool_calls(xml_call.group(1), offset=len(calls)))

    clean = _XML_TOOL_CALL_RE.sub("", normalized)
    clean = _ROOT_RE.sub("", clean)
    clean = _INVOKE_RE.sub("", clean)
    clean = _PARAM_RE.sub("", clean)
    clean = _ANY_TAG_RE.sub("", clean)
    clean = _XML_TOOL_CALL_TAG_RE.sub("", clean).strip()
    if calls:
        logger.warning(
            "[tool-call] parsed %d text tool call(s) from assistant content: %s",
            len(calls), ", ".join(call.name for call in calls),
        )
    return clean, calls
