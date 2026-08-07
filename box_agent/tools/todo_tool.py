"""Todo Tool - Task tracking for multi-step agent workflows.

Lets the agent decompose complex tasks into trackable items,
update progress, and stay oriented across long execution chains.

Design:
- Two tool classes share a single ``TodoStore`` (in-memory list).
- Store is injected at construction time — the wiring lives in setup.py.
- Optional ``persist_path`` makes the store survive restarts.
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


def _todo_snapshot(items: list[dict]) -> dict[str, Any]:
    """Return a host-friendly todo snapshot payload."""
    normalized = [dict(item) for item in items]
    total = len(normalized)
    completed = sum(1 for item in normalized if item.get("status") == "completed")
    in_progress = sum(1 for item in normalized if item.get("status") == "in_progress")
    pending = sum(1 for item in normalized if item.get("status") == "pending")
    return {
        "type": "todo_snapshot",
        "items": normalized,
        "summary": {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
        },
    }


# ── Shared store ────────────────────────────────────────────


def _todo_model_context(items: list[dict], *, action: str) -> str:
    """Keep the complete execution checklist salient in future model turns."""
    current = [
        {
            "id": item.get("id"),
            "task": item.get("task"),
            "status": item.get("status"),
            "priority": item.get("priority", "medium"),
        }
        for item in items
    ]
    if not current:
        return (
            f"Todo action '{action}' succeeded. The current todo list is empty. "
            "Do not assume unfinished work remains from an older list."
        )
    return (
        f"Todo action '{action}' succeeded. This is the complete current todo list "
        "and the execution state for the task:\n"
        f"{json.dumps(current, indent=2, ensure_ascii=False)}\n"
        "Continue with the single in_progress item. After completing and verifying it, "
        "call todo_write with action='set' and the complete updated list so the next "
        "pending item becomes in_progress. Do not execute work unrelated to this list; "
        "revise the plan and then rebuild the list if the execution scope must change."
    )


class TodoStore:
    """Lightweight in-memory todo list with optional JSON persistence."""

    def __init__(self, persist_path: Path | None = None):
        self._items: dict[str, dict] = {}
        self._counter = count(1)
        self._persist_path = persist_path
        if persist_path and persist_path.exists():
            self._load()

    # -- internal helpers --------------------------------------------------

    def _next_id(self) -> str:
        return str(next(self._counter))

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(list(self._items.values()), indent=2, ensure_ascii=False)
        )

    def _load(self) -> None:
        try:
            items = json.loads(self._persist_path.read_text())  # type: ignore[union-attr]
            for item in items:
                self._items[item["id"]] = item
            # Resume counter after highest existing id
            if self._items:
                max_id = max(int(i) for i in self._items)
                self._counter = count(max_id + 1)
        except Exception:
            pass

    # -- public API --------------------------------------------------------

    def create(self, task: str, priority: str = "medium", status: str = "pending") -> dict:
        todo_id = self._next_id()
        item = {
            "id": todo_id,
            "task": task,
            "status": status,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
        }
        self._items[todo_id] = item
        self._save()
        return item

    def replace(self, todos: list[dict[str, Any]]) -> list[dict]:
        self._items = {}
        self._counter = count(1)
        for todo in todos:
            todo_id = self._next_id()
            self._items[todo_id] = {
                "id": todo_id,
                "task": str(todo["task"]).strip(),
                "status": str(todo.get("status") or "pending"),
                "priority": str(todo.get("priority") or "medium"),
                "created_at": datetime.now().isoformat(),
            }
        self._save()
        return self.list()

    def update(self, todo_id: str, *, status: str | None = None, task: str | None = None) -> dict | None:
        item = self._items.get(todo_id)
        if item is None:
            return None
        if status is not None:
            item["status"] = status
        if task is not None:
            item["task"] = task
        self._save()
        return item

    def delete(self, todo_id: str) -> bool:
        removed = self._items.pop(todo_id, None) is not None
        if removed:
            self._save()
        return removed

    def get(self, todo_id: str) -> dict | None:
        return self._items.get(todo_id)

    def list(self, status: str | None = None) -> list[dict]:
        items = list(self._items.values())
        if status:
            items = [i for i in items if i["status"] == status]
        return items


# ── Tools ───────────────────────────────────────────────────

_VALID_STATUSES = ("pending", "in_progress", "completed")
_VALID_PRIORITIES = ("high", "medium", "low")


class TodoWriteTool(Tool):
    """Create, replace, update, or delete todo items."""

    def __init__(self, store: TodoStore):
        self._store = store

    def _result(self, *, content: str, action: str, item: dict | None = None) -> ToolResult:
        items = self._store.list()
        snapshot = _todo_snapshot(items)
        raw_output = {**snapshot, "action": action}
        if item is not None:
            raw_output["item"] = dict(item)
        return ToolResult(
            success=True,
            content=content,
            raw_output=raw_output,
            model_context=_todo_model_context(items, action=action),
        )

    @property
    def name(self) -> str:
        return "todo_write"

    @property
    def description(self) -> str:
        return (
            "Manage a todo list for tracking multi-step tasks. "
            "Actions: 'set' the full current list in one call, 'create' a new item, "
            "'update' an existing item's status or text, or 'delete' an item. "
            "For new or substantially revised multi-step work, and for every progress "
            "transition, prefer 'set' with the complete ordered todos array so the host "
            "and model receive the whole current checklist. "
            "If a current plan exists, call plan_read before setting todos. Derive the "
            "todos from plan steps in order and keep the plan's objective, scope, and "
            "verification requirements aligned. A plan step may be split into executable "
            "subtasks, but do not omit plan steps, change their meaning, or add unrelated "
            "work. Revise the plan with plan_write before materially changing execution. "
            "Use this to decompose complex work into trackable steps "
            "and mark progress as you go: keep exactly the current item in_progress, mark "
            "finished items completed, and move the next item to in_progress before working "
            "on it. This tool is only a progress tracker: it is not "
            "factual evidence, a search strategy, or a source for final conclusions. Do not "
            "narrow the user's request or lower verification standards because a todo exists."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set", "create", "update", "delete"],
                    "description": "Operation to perform.",
                },
                "todos": {
                    "type": "array",
                    "description": (
                        "Complete ordered todo list for action='set'. This replaces the "
                        "current list. Each item needs task, with optional status and priority."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "Task description."},
                            "status": {
                                "type": "string",
                                "enum": list(_VALID_STATUSES),
                                "description": "Task status. Default: pending.",
                            },
                            "priority": {
                                "type": "string",
                                "enum": list(_VALID_PRIORITIES),
                                "description": "Priority level. Default: medium.",
                            },
                        },
                        "required": ["task"],
                    },
                },
                "task": {
                    "type": "string",
                    "description": "Task description (required for 'create', optional for 'update').",
                },
                "todo_id": {
                    "type": "string",
                    "description": "ID of the todo item (required for 'update' and 'delete').",
                },
                "status": {
                    "type": "string",
                    "enum": list(_VALID_STATUSES),
                    "description": (
                        "Status to set for 'create' or 'update'. One of: pending, "
                        "in_progress, completed."
                    ),
                },
                "priority": {
                    "type": "string",
                    "enum": list(_VALID_PRIORITIES),
                    "description": "Priority level (for 'create'). Default: medium.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        task: str | None = None,
        todo_id: str | None = None,
        status: str | None = None,
        priority: str = "medium",
        todos: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        if action == "set":
            validation_error = self._validate_todos(todos)
            if validation_error:
                return ToolResult(success=False, error=validation_error)
            items = self._store.replace(todos or [])
            return self._result(
                content=f"Set todo list with {len(items)} item{'s' if len(items) != 1 else ''}.",
                action="set",
            )

        if action == "create":
            if not task:
                return ToolResult(success=False, error="'task' is required for create.")
            item = self._store.create(task, priority, status or "pending")
            return self._result(content=f"Created todo #{item['id']}: {task}", action="create", item=item)

        if action == "update":
            if not todo_id:
                return ToolResult(success=False, error="'todo_id' is required for update.")
            item = self._store.update(todo_id, status=status, task=task)
            if item is None:
                return ToolResult(success=False, error=f"Todo #{todo_id} not found.")
            return self._result(
                content=f"Updated todo #{todo_id}: [{item['status']}] {item['task']}",
                action="update",
                item=item,
            )

        if action == "delete":
            if not todo_id:
                return ToolResult(success=False, error="'todo_id' is required for delete.")
            if not self._store.delete(todo_id):
                return ToolResult(success=False, error=f"Todo #{todo_id} not found.")
            return self._result(content=f"Deleted todo #{todo_id}.", action="delete")

        return ToolResult(success=False, error=f"Unknown action: {action}")

    @staticmethod
    def _validate_todos(todos: list[dict[str, Any]] | None) -> str | None:
        if todos is None:
            return "'todos' is required for set."
        if not isinstance(todos, list):
            return "'todos' must be a list for set."
        for index, todo in enumerate(todos, start=1):
            if not isinstance(todo, dict):
                return f"Todo #{index} must be an object."
            task = str(todo.get("task") or "").strip()
            if not task:
                return f"'task' is required for todo #{index}."
            status = str(todo.get("status") or "pending")
            if status not in _VALID_STATUSES:
                return f"Invalid status for todo #{index}: {status}."
            priority = str(todo.get("priority") or "medium")
            if priority not in _VALID_PRIORITIES:
                return f"Invalid priority for todo #{index}: {priority}."
        return None


class TodoReadTool(Tool):
    """Read the current todo list."""

    def __init__(self, store: TodoStore):
        self._store = store

    @property
    def name(self) -> str:
        return "todo_read"

    @property
    def description(self) -> str:
        return (
            "Read the current todo list. Returns all items or filtered by status. "
            "Use this to review progress and decide what to work on next."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "string",
                    "description": "Optional: get a single item by ID.",
                },
                "status": {
                    "type": "string",
                    "enum": list(_VALID_STATUSES),
                    "description": "Optional: filter by status.",
                },
            },
        }

    async def execute(self, todo_id: str | None = None, status: str | None = None) -> ToolResult:
        # Single item lookup
        if todo_id:
            item = self._store.get(todo_id)
            if item is None:
                return ToolResult(success=False, error=f"Todo #{todo_id} not found.")
            return ToolResult(success=True, content=self._format_items([item]), raw_output=_todo_snapshot([item]))

        # List (optionally filtered)
        items = self._store.list(status)
        if not items:
            label = f" ({status})" if status else ""
            return ToolResult(success=True, content=f"No todo items{label}.", raw_output=_todo_snapshot([]))
        return ToolResult(success=True, content=self._format_items(items), raw_output=_todo_snapshot(items))

    @staticmethod
    def _format_items(items: list[dict]) -> str:
        status_icon = {"pending": "○", "in_progress": "◑", "completed": "●"}
        lines = []
        for item in items:
            icon = status_icon.get(item["status"], "?")
            pri = f" [{item['priority']}]" if item.get("priority", "medium") != "medium" else ""
            lines.append(f"  {icon} #{item['id']} {item['task']}{pri}")

        # Summary line
        total = len(items)
        done = sum(1 for i in items if i["status"] == "completed")
        active = sum(1 for i in items if i["status"] == "in_progress")
        pending = total - done - active
        summary = f"Total: {total} | ● {done} done · ◑ {active} active · ○ {pending} pending"

        return "\n".join(lines) + "\n" + summary
