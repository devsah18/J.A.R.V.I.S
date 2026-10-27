"""Tool registry and dispatch.

The router is the single choke point through which every action flows. It maps
a requested tool name to the registered tool, asks the permission system whether
the call is allowed, runs it, and normalises the outcome.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from collections.abc import Iterable

from core.permissions import PermissionManager, PermissionRequest
from tools.base import Risk, Tool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ActionRequest:
    """A decision by the AI layer to invoke a tool."""

    tool: str
    params: dict = field(default_factory=dict)


@dataclass
class DispatchOutcome:
    """The result of routing an :class:`ActionRequest`."""

    ok: bool
    spoken: str
    tool: str
    denied: bool = False
    result: ToolResult | None = None


class Router:
    def __init__(self, tools: Iterable[Tool], permissions: PermissionManager):
        self._tools: dict[str, Tool] = {}
        self._permissions = permissions
        for tool in tools:
            self.register(tool)

    # ------------------------------------------------------------------ #
    # Registry
    # ------------------------------------------------------------------ #
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    def dispatch(self, action: ActionRequest) -> DispatchOutcome:
        tool = self._tools.get(action.tool)
        if tool is None:
            return DispatchOutcome(
                ok=False,
                spoken=f"I don't have a tool for '{action.tool}'.",
                tool=action.tool,
            )

        risk = tool.risk_for(**action.params)
        request = PermissionRequest(
            tool=tool.name,
            risk=risk,
            summary=self._summarise(tool, action.params),
            params=action.params,
        )
        if not self._permissions.evaluate(request):
            logger.info("Denied %s (risk=%s)", tool.name, risk)
            return DispatchOutcome(
                ok=False,
                spoken="Understood - I won't do that.",
                tool=tool.name,
                denied=True,
            )

        try:
            result = tool.run(**action.params)
        except Exception as error:  # noqa: BLE001 - report any tool failure gracefully
            logger.exception("Tool %s raised", tool.name)
            return DispatchOutcome(
                ok=False,
                spoken=f"Something went wrong running {tool.name}: {error}",
                tool=tool.name,
            )

        return DispatchOutcome(ok=result.ok, spoken=result.message, tool=tool.name, result=result)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _summarise(tool: Tool, params: dict) -> str:
        if not params:
            return tool.description
        detail = ", ".join(f"{key}={value}" for key, value in params.items() if value not in (None, ""))
        return f"{tool.description} ({detail})" if detail else tool.description
