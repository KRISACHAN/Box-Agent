"""Turn captured records into compact, human-readable display models."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Sequence


UNICODE_PAIR_RE = re.compile(r"\\u([dD][89aAbB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})")
UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")

EVENT_TITLES = {
    "session.start": "会话开始",
    "turn.input": "任务输入",
    "llm.request": "模型请求",
    "llm.response": "模型响应",
    "llm.error": "模型错误",
    "tool.request": "工具调用",
    "tool.response": "工具结果",
    "turn.output": "最终输出",
    "turn.end": "任务结束",
    "turn.error": "任务错误",
    "attempt.started": "评测尝试开始",
    "process.starting": "进程准备启动",
    "process.started": "进程已启动",
    "process.stop_requested": "进程停止请求",
    "signal.sent": "进程信号",
    "signal.not_sent": "进程信号未发送",
    "stream.eof": "数据流结束",
    "stream.error": "数据流错误",
    "process.exited": "进程退出",
    "acp.completed": "ACP 完成",
    "agent_thought_chunk": "Agent 思考",
    "agent_message_chunk": "Agent 回复",
    "tool_call": "ACP 工具调用",
    "tool_call_update": "ACP 工具更新",
}


def _decode_string(value: str) -> str:
    def pair(match: re.Match[str]) -> str:
        high = int(match.group(1), 16)
        low = int(match.group(2), 16)
        return chr(0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00))

    value = UNICODE_PAIR_RE.sub(pair, value)
    return UNICODE_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), value)


def decode_unicode(value: Any) -> Any:
    if isinstance(value, str):
        return _decode_string(value)
    if isinstance(value, list):
        return [decode_unicode(item) for item in value]
    if isinstance(value, dict):
        return {decode_unicode(key): decode_unicode(item) for key, item in value.items()}
    return value


def json_text(value: Any) -> str:
    value = decode_unicode(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def annotate_timing(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    shown = [dict(record) for record in records]
    first: datetime | None = None
    previous: datetime | None = None
    for record in shown:
        current = _parse_timestamp(record.get("timestamp"))
        record["elapsed_start"] = None
        record["elapsed_previous"] = None
        if current is None:
            continue
        if first is None:
            first = current
        record["elapsed_start"] = f"+{(current - first).total_seconds():.3f}s"
        if previous is not None:
            record["elapsed_previous"] = f"Δ{(current - previous).total_seconds():.3f}s"
        previous = current
    return shown


def _event_name(record: dict[str, Any], payload: Any) -> str:
    if record.get("source") == "stderr":
        return str(record.get("category") or "stderr")
    if not isinstance(payload, dict):
        return str(record.get("source") or "记录")
    direct = payload.get("event") or payload.get("type")
    if isinstance(direct, str):
        return direct
    message = payload.get("message")
    if isinstance(message, dict):
        method = message.get("method")
        if method == "session/update":
            update = message.get("params", {}).get("update", {})
            if isinstance(update, dict) and isinstance(update.get("sessionUpdate"), str):
                return update["sessionUpdate"]
        if isinstance(method, str):
            return method
        if "result" in message:
            return "rpc.response"
        if "error" in message:
            return "rpc.error"
    if record.get("source") == "files" and isinstance(payload.get("file"), str):
        return payload["file"]
    return str(record.get("source") or "记录")


def _field(label: str, value: Any) -> dict[str, str] | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    return {"label": label, "value": json_text(value)}


def _agent_fields(event: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    fields: list[dict[str, str] | None]
    if event == "turn.input":
        fields = [_field("输入", data.get("content") or data.get("prompt")), _field("任务", data.get("task_id"))]
    elif event == "llm.request":
        messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        tools = data.get("tools") if isinstance(data.get("tools"), list) else []
        fields = [
            _field("模型", data.get("model")),
            _field("提供方", data.get("provider")),
            _field("消息数", len(messages)),
            _field("可用工具数", len(tools)),
        ]
    elif event == "llm.response":
        tool_calls = data.get("tool_calls") if isinstance(data.get("tool_calls"), list) else []
        tool_names = [call.get("function", {}).get("name") for call in tool_calls if isinstance(call, dict)]
        fields = [
            _field("模型", data.get("model")),
            _field("回复", data.get("content")),
            _field("思考", data.get("thinking")),
            _field("工具", [name for name in tool_names if name]),
            _field("结束原因", data.get("finish_reason")),
            _field("用量", data.get("usage")),
            _field("耗时", data.get("timing")),
        ]
    elif event == "tool.request":
        fields = [
            _field("工具", data.get("tool_name")),
            _field("参数", data.get("arguments")),
            _field("允许执行", data.get("allowed_to_execute")),
        ]
    elif event == "tool.response":
        fields = [
            _field("工具", data.get("tool_name")),
            _field("成功", data.get("success")),
            _field("结果", data.get("content") or data.get("model_content")),
            _field("错误", data.get("error")),
            _field("耗时", f"{data['duration_ms']}ms" if data.get("duration_ms") is not None else None),
        ]
    elif event in {"turn.output", "turn.end", "turn.error", "llm.error"}:
        fields = [
            _field("输出", data.get("content") or data.get("output")),
            _field("状态", data.get("status") or data.get("stop_reason")),
            _field("错误", data.get("error") or data.get("message")),
            _field("用量", data.get("usage")),
        ]
    else:
        fields = [_field("内容", data)]
    return [field for field in fields if field]


def _acp_fields(payload: dict[str, Any]) -> list[dict[str, str]]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    update = params.get("update") if isinstance(params.get("update"), dict) else {}
    result = message.get("result")
    if isinstance(result, dict):
        important_result = {
            key: result[key]
            for key in ("sessionId", "agentInfo", "protocolVersion", "stopReason", "usage")
            if key in result
        }
        if not important_result:
            important_result = {key: value for key, value in result.items() if key != "_meta"}
    else:
        important_result = result
    content = update.get("content") if isinstance(update.get("content"), dict) else {}
    prompt = params.get("prompt") if isinstance(params.get("prompt"), list) else []
    prompt_text = [item.get("text") for item in prompt if isinstance(item, dict) and item.get("text")]
    fields = [
        _field("方向", payload.get("direction")),
        _field("请求 ID", message.get("id")),
        _field("方法", message.get("method")),
        _field("内容", content.get("text") or prompt_text),
        _field("工具", update.get("title") or update.get("toolCallId")),
        _field("状态", update.get("status") or (result.get("stopReason") if isinstance(result, dict) else None)),
        _field("错误", message.get("error")),
        _field("结果", important_result),
    ]
    return [field for field in fields if field]


def _generic_fields(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        field = _field("内容", payload)
        return [field] if field else []
    ignored = {"schema_version", "timestamp", "monotonic_ns", "session_id", "acp_session_id", "turn_id", "event", "type"}
    return [field for key, value in payload.items() if key not in ignored if (field := _field(key, value))][:8]


def present_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = decode_unicode(record.get("payload"))
    event = _event_name(record, payload)
    source = record.get("source")
    if source == "agent" and isinstance(payload, dict):
        fields = _agent_fields(event, payload)
    elif source == "acp" and isinstance(payload, dict):
        fields = _acp_fields(payload)
    elif source == "stderr":
        fields = [_field("日志", payload)]
    else:
        fields = _generic_fields(payload)
    shown = dict(record)
    shown["payload"] = payload
    shown["view"] = {
        "event": event,
        "title": EVENT_TITLES.get(event, event),
        "fields": [field for field in fields if field],
        "raw": json_text(payload),
    }
    return shown
