"""Safety and permission checks for tool execution.

The assistant is *not* an unrestricted autonomous agent. Every tool call is
classified by risk and, when the risk warrants it, must be confirmed before it
runs. The confirmation itself is supplied as a callback so the same policy works
for the CLI, voice and GUI front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from tools.base import Risk


@dataclass
class PermissionRequest:
    """A pending tool call awaiting a permission decision."""

    tool: str
    risk: Risk
    summary: str
    params: dict


class PermissionManager:
    def __init__(
        self,
        confirm: Callable[[str], bool] | None = None,
        confirm_high_risk: bool = True,
        confirm_medium_risk: bool = False,
    ):
        self._confirm = confirm
        self.confirm_high_risk = confirm_high_risk
        self.confirm_medium_risk = confirm_medium_risk

    def set_confirmer(self, confirm: Callable[[str], bool] | None) -> None:
        """Swap the confirmation callback (e.g. when switching to GUI mode)."""
        self._confirm = confirm

    def requires_confirmation(self, request: PermissionRequest) -> bool:
        if request.risk is Risk.HIGH:
            return self.confirm_high_risk
        if request.risk is Risk.MEDIUM:
            return self.confirm_medium_risk
        return False

    def evaluate(self, request: PermissionRequest) -> bool:
        """Return True if the call may proceed, False if it is denied."""
        if not self.requires_confirmation(request):
            return True
        if self._confirm is None:
            # No way to ask -> refuse the risky action rather than guess.
            return False
        return bool(self._confirm(self.describe(request)))

    @staticmethod
    def describe(request: PermissionRequest) -> str:
        level = str(request.risk).upper()
        return f"[{level}] Allow {request.tool} to {request.summary}?"
