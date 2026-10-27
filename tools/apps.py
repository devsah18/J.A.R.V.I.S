"""Application launching and control (Windows-first, degrades elsewhere)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time

from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None


# Friendly name -> (launch command, expected process executable name)
APP_ALIASES: dict[str, tuple[str, str]] = {
    "chrome": ("chrome", "chrome.exe"),
    "google chrome": ("chrome", "chrome.exe"),
    "edge": ("msedge", "msedge.exe"),
    "microsoft edge": ("msedge", "msedge.exe"),
    "firefox": ("firefox", "firefox.exe"),
    "vscode": ("code", "Code.exe"),
    "vs code": ("code", "Code.exe"),
    "code": ("code", "Code.exe"),
    "notepad": ("notepad", "notepad.exe"),
    "calculator": ("calc", "calc.exe"),
    "calc": ("calc", "calc.exe"),
    "explorer": ("explorer", "explorer.exe"),
    "file explorer": ("explorer", "explorer.exe"),
    "cmd": ("cmd", "cmd.exe"),
    "command prompt": ("cmd", "cmd.exe"),
    "powershell": ("powershell", "powershell.exe"),
    "terminal": ("wt", "WindowsTerminal.exe"),
    "spotify": ("spotify", "Spotify.exe"),
    "task manager": ("taskmgr", "Taskmgr.exe"),
    "paint": ("mspaint", "mspaint.exe"),
    "word": ("winword", "WINWORD.EXE"),
    "excel": ("excel", "EXCEL.EXE"),
}

LAUNCH_TIMEOUT_SECONDS = 6.0


class AppsTool(Tool):
    name = "apps"
    description = "Open or close desktop applications by name."
    risk = Risk.MEDIUM
    params = (
        ParamSpec("action", "'open' or 'close'"),
        ParamSpec("name", "Application name, e.g. 'Chrome' or 'VS Code'"),
        ParamSpec("args", "Optional arguments to pass to the application", required=False),
    )

    def risk_for(self, action: str = "open", **kwargs) -> Risk:
        return Risk.HIGH if (action or "").strip().lower() == "close" else Risk.MEDIUM

    def run(self, action: str = "open", name: str = "", args=None, **kwargs) -> ToolResult:
        action = (action or "open").strip().lower()
        name = (name or "").strip()
        if not name:
            return ToolResult.failure("Which application should I use?")

        command, process = self._resolve(name)
        display = name.title()

        if action == "close":
            return self._close(display, process)
        if action == "open":
            return self._open(display, command, process, self._split_args(args))
        return ToolResult.failure(f"I only know how to open or close apps, not '{action}'.")

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def _resolve(self, name: str) -> tuple[str, str]:
        key = name.strip().lower()
        if key in APP_ALIASES:
            return APP_ALIASES[key]
        # Unknown app: assume the name is an executable or registered target.
        return name, f"{name}.exe"

    @staticmethod
    def _split_args(args) -> list[str]:
        if not args:
            return []
        if isinstance(args, (list, tuple)):
            return [str(a) for a in args]
        return shlex.split(str(args))

    # ------------------------------------------------------------------ #
    # Open
    # ------------------------------------------------------------------ #
    def _open(self, display: str, command: str, process: str, args: list[str]) -> ToolResult:
        if not self._spawn(command, args):
            return ToolResult.failure(
                f"{display} didn't open. The application isn't available at the expected location."
            )

        if self._wait_for_process(process, LAUNCH_TIMEOUT_SECONDS):
            return ToolResult.success(f"Opening {display}.", launched=command)
        return ToolResult.success(
            f"I sent the command to open {display}, but I couldn't confirm it started.",
            launched=command,
        )

    @staticmethod
    def _spawn(command: str, args: list[str]) -> bool:
        if shutil.which(command):
            try:
                subprocess.Popen([command, *args])
                return True
            except OSError:
                pass
        try:  # Registered app / document / URI.
            os.startfile(command)  # type: ignore[attr-defined]
            return True
        except (OSError, AttributeError):
            pass
        try:
            subprocess.Popen(["cmd", "/c", "start", "", command, *args])
            return True
        except OSError:
            return False

    @staticmethod
    def _wait_for_process(process: str, timeout: float) -> bool:
        if psutil is None:
            return False
        target = process.lower().removesuffix(".exe")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if AppsTool._find_processes(target):
                return True
            time.sleep(0.4)
        return False

    # ------------------------------------------------------------------ #
    # Close
    # ------------------------------------------------------------------ #
    def _close(self, display: str, process: str) -> ToolResult:
        if psutil is None:
            return ToolResult.failure("Closing applications needs psutil, which isn't installed.")
        target = process.lower().removesuffix(".exe")
        matches = self._find_processes(target)
        if not matches:
            return ToolResult.failure(f"{display} doesn't appear to be running.")

        terminated = 0
        for proc in matches:
            try:
                proc.terminate()
                terminated += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return ToolResult.success(f"Closing {display}.", terminated=terminated)

    @staticmethod
    def _find_processes(target: str) -> list:
        if psutil is None:
            return []
        found = []
        for proc in psutil.process_iter(["name"]):
            proc_name = (proc.info.get("name") or "").lower().removesuffix(".exe")
            if proc_name and (target == proc_name or target in proc_name):
                found.append(proc)
        return found
