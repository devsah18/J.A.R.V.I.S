"""File-management tool: list, read, write, append, move, delete, search."""

from __future__ import annotations

import os
from pathlib import Path

from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    from send2trash import send2trash
except ImportError:  # pragma: no cover - optional dependency
    send2trash = None


READ_LIMIT_BYTES = 200_000
MAX_LIST_ENTRIES = 200

_READ_ONLY_ACTIONS = {"list", "read", "search"}
_WRITE_ACTIONS = {"write", "append"}
_MOVE_ACTIONS = {"rename", "move"}


class FilesTool(Tool):
    name = "files"
    description = "List, read, create, edit, rename, move, search and delete files."
    risk = Risk.MEDIUM
    params = (
        ParamSpec("action", "list, read, write, append, rename, move, delete or search"),
        ParamSpec("path", "Target file or directory"),
        ParamSpec("content", "Text to write (write/append)", required=False),
        ParamSpec("destination", "New path (rename/move)", required=False),
        ParamSpec("pattern", "Glob pattern (search), default '*'", required=False),
    )

    def risk_for(self, action: str = "", **kwargs) -> Risk:
        action = (action or "").strip().lower()
        if action == "delete":
            return Risk.HIGH
        if action in _READ_ONLY_ACTIONS:
            return Risk.LOW
        return Risk.MEDIUM

    def run(
        self,
        action: str = "",
        path: str = "",
        content: str | None = None,
        destination: str = "",
        pattern: str = "*",
        **kwargs,
    ) -> ToolResult:
        action = (action or "").strip().lower()
        if not action:
            return ToolResult.failure("What should I do with the file?")
        if not path:
            return ToolResult.failure("Which file or folder should I use?")

        target = self._resolve(path)

        if action in _READ_ONLY_ACTIONS:
            return {"list": self._list, "read": self._read, "search": self._search}[action](
                target, pattern if action == "search" else None
            )
        if action in _WRITE_ACTIONS:
            return self._write(target, content or "", append=(action == "append"))
        if action in _MOVE_ACTIONS:
            return self._move(target, self._resolve(destination))
        if action == "delete":
            return self._delete(target)
        return ToolResult.failure(
            "I can list, read, write, append, rename, move, delete or search files."
        )

    # ------------------------------------------------------------------ #
    # Read-only
    # ------------------------------------------------------------------ #
    def _list(self, target: Path, _pattern) -> ToolResult:
        if not target.exists():
            return ToolResult.failure(f"{target} doesn't exist.")
        if target.is_file():
            size = target.stat().st_size
            return ToolResult.success(f"{target.name} is a file, {size} bytes.", path=str(target))

        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())[:MAX_LIST_ENTRIES]
        names = [f"{item.name}{'/' if item.is_dir() else ''}" for item in entries]
        preview = ", ".join(names[:6]) + ("..." if len(names) > 6 else "")
        spoken = f"{target} contains {len(names)} items: {preview}" if names else f"{target} is empty."
        return ToolResult.success(spoken, path=str(target), entries=names)

    def _read(self, target: Path, _pattern) -> ToolResult:
        if not target.exists():
            return ToolResult.failure(f"{target} doesn't exist.")
        if target.is_dir():
            return ToolResult.failure(f"{target} is a folder, not a file.")
        try:
            with target.open("r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(READ_LIMIT_BYTES)
        except OSError as error:
            return ToolResult.failure(f"I couldn't read {target.name}: {error}")
        preview = text.strip().splitlines()[:5]
        spoken = f"Here are the first lines of {target.name}: " + " ".join(preview)
        return ToolResult.success(spoken, path=str(target), content=text)

    def _search(self, target: Path, pattern: str | None) -> ToolResult:
        if not target.is_dir():
            return ToolResult.failure(f"{target} isn't a folder to search.")
        matches = sorted(target.rglob(pattern or "*"))[:MAX_LIST_ENTRIES]
        names = [str(item.relative_to(target)) for item in matches if item != target]
        if not names:
            return ToolResult.success(f"No files matching '{pattern}' in {target.name}.", matches=[])
        return ToolResult.success(
            f"Found {len(names)} matches for '{pattern}' in {target.name}.",
            matches=names,
        )

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def _write(self, target: Path, content: str, append: bool) -> ToolResult:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with target.open(mode, encoding="utf-8") as handle:
                handle.write(content)
        except OSError as error:
            return ToolResult.failure(f"I couldn't write {target.name}: {error}")
        verb = "Appended to" if append else "Saved"
        return ToolResult.success(f"{verb} {target.name}.", path=str(target))

    def _move(self, source: Path, destination: Path) -> ToolResult:
        if not source.exists():
            return ToolResult.failure(f"{source} doesn't exist.")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination) if source.is_file() else source.rename(destination)
        except OSError as error:
            return ToolResult.failure(f"I couldn't move {source.name}: {error}")
        return ToolResult.success(
            f"Moved {source.name} to {destination}.", source=str(source), destination=str(destination)
        )

    def _delete(self, target: Path) -> ToolResult:
        if not target.exists():
            return ToolResult.failure(f"{target} doesn't exist.")
        try:
            if send2trash is not None:
                send2trash(str(target))
                return ToolResult.success(f"Moved {target.name} to the recycle bin.", path=str(target))
            if target.is_dir():
                return ToolResult.failure(
                    "I won't permanently delete a folder without a recycle-bin backend."
                )
            os.remove(target)
        except OSError as error:
            return ToolResult.failure(f"I couldn't delete {target.name}: {error}")
        return ToolResult.success(f"Deleted {target.name}.", path=str(target))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve(raw_path: str) -> Path:
        path = Path(os.path.expandvars(raw_path)).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path
