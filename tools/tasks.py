"""Task and reminder tool. Persistence is provided by an injected store."""

from __future__ import annotations

from tools.base import ParamSpec, Risk, Tool, ToolResult


class TasksTool(Tool):
    name = "tasks"
    description = "Create, list, complete and remove tasks and reminders."
    risk = Risk.LOW
    params = (
        ParamSpec("action", "add, list, complete or remove"),
        ParamSpec("title", "Task description (add), or match text (complete/remove)", required=False),
        ParamSpec("due", "Optional due time, free text", required=False),
    )

    def __init__(self, store):
        self._store = store

    def run(self, action: str = "list", title: str = "", due: str = "", **kwargs) -> ToolResult:
        if self._store is None:
            return ToolResult.failure("Task storage isn't available right now.")

        action = (action or "list").strip().lower()
        if action == "add":
            return self._add(title, due)
        if action == "list":
            return self._list()
        if action == "complete":
            return self._complete(title)
        if action == "remove":
            return self._remove(title)
        return ToolResult.failure("I can add, list, complete or remove tasks.")

    # ------------------------------------------------------------------ #
    def _add(self, title: str, due: str) -> ToolResult:
        title = (title or "").strip()
        if not title:
            return ToolResult.failure("What should the task be?")
        task = self._store.add_task(title, due or None)
        suffix = f" for {due}" if due else ""
        return ToolResult.success(f"Added task: {title}{suffix}.", task=task)

    def _list(self) -> ToolResult:
        tasks = self._store.list_tasks()
        if not tasks:
            return ToolResult.success("You have no open tasks.", tasks=[])
        preview = "; ".join(t["title"] for t in tasks[:5])
        return ToolResult.success(
            f"You have {len(tasks)} open tasks: {preview}.", tasks=tasks
        )

    def _complete(self, title: str) -> ToolResult:
        task = self._store.complete_task((title or "").strip())
        if task is None:
            return ToolResult.failure(f"I couldn't find a task matching '{title}'.")
        return ToolResult.success(f"Marked '{task['title']}' as done.", task=task)

    def _remove(self, title: str) -> ToolResult:
        removed = self._store.remove_task((title or "").strip())
        if removed == 0:
            return ToolResult.failure(f"I couldn't find a task matching '{title}'.")
        return ToolResult.success(f"Removed {removed} task(s).", removed=removed)
