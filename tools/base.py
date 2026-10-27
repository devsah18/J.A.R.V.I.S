"""Shared tool contracts for VARSHA's modular tool system.

Every capability the assistant can perform is expressed as a :class:`Tool`.
Tools never touch the operating system directly from the AI layer - they are
registered with the router, checked by the permission system, and only then
executed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Risk(Enum):
    """How consequential a tool call is, used by the permission system."""

    LOW = "low"      # read-only / harmless
    MEDIUM = "medium"  # changes local state (launch app, write file)
    HIGH = "high"    # destructive or irreversible

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass
class ParamSpec:
    """A single argument a tool understands."""

    name: str
    description: str
    required: bool = True


@dataclass
class ToolResult:
    """The outcome of running a tool.

    ``message`` is phrased so it can be spoken aloud directly.
    """

    ok: bool
    message: str
    data: dict = field(default_factory=dict)

    @classmethod
    def success(cls, message: str, **data) -> "ToolResult":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def failure(cls, message: str, **data) -> "ToolResult":
        return cls(ok=False, message=message, data=data)


class Tool(ABC):
    """Base class for every tool.

    Subclasses set the class attributes and implement :meth:`run`.
    """

    name: str = ""
    description: str = ""
    risk: Risk = Risk.LOW
    params: tuple[ParamSpec, ...] = ()

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        """Execute the tool and return a :class:`ToolResult`."""

    def risk_for(self, **kwargs) -> Risk:
        """Risk of one specific invocation.

        Defaults to the tool's static :attr:`risk`; tools whose danger depends
        on the action being performed (open vs. close, read vs. delete) override
        this to report it accurately.
        """
        return self.risk

    def schema(self) -> dict:
        """Machine-readable description, used for LLM function-calling."""
        return {
            "name": self.name,
            "description": self.description,
            "risk": str(self.risk),
            "parameters": [
                {
                    "name": param.name,
                    "description": param.description,
                    "required": param.required,
                }
                for param in self.params
            ],
        }
