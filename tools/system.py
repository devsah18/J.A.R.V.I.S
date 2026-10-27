"""System-information tool backed by psutil."""

from __future__ import annotations

from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None


class SystemTool(Tool):
    name = "system"
    description = "Report the computer's CPU, memory, disk and battery status."
    risk = Risk.LOW
    params = (
        ParamSpec("metric", "cpu, memory, disk, battery or all", required=False),
        ParamSpec("path", "Disk path to inspect (defaults to the system drive)", required=False),
    )

    def run(self, metric: str = "all", path: str | None = None, **kwargs) -> ToolResult:
        if psutil is None:
            return ToolResult.failure(
                "System monitoring isn't available because psutil isn't installed."
            )

        metric = (metric or "all").strip().lower()
        handlers = {
            "cpu": self._cpu,
            "memory": self._memory,
            "disk": lambda: self._disk(path),
            "battery": self._battery,
        }

        if metric == "all":
            return self._summary()

        handler = handlers.get(metric)
        if handler is None:
            return ToolResult.failure(
                f"I can't report '{metric}'. Try cpu, memory, disk, battery or all."
            )
        return handler()

    # ------------------------------------------------------------------ #
    # Individual metrics
    # ------------------------------------------------------------------ #
    def _cpu(self) -> ToolResult:
        percent = psutil.cpu_percent(interval=0.5)
        cores = psutil.cpu_count(logical=True) or 0
        physical = psutil.cpu_count(logical=False) or 0
        return ToolResult.success(
            f"CPU usage is currently {percent:.0f} percent.",
            metric="cpu",
            percent=round(percent, 1),
            logical_cores=cores,
            physical_cores=physical,
        )

    def _memory(self) -> ToolResult:
        mem = psutil.virtual_memory()
        used_gb = self._gb(mem.used)
        total_gb = self._gb(mem.total)
        return ToolResult.success(
            f"Memory usage is {mem.percent:.0f} percent - {used_gb:.1f} of {total_gb:.1f} gigabytes in use.",
            metric="memory",
            percent=round(mem.percent, 1),
            used_gb=round(used_gb, 1),
            total_gb=round(total_gb, 1),
        )

    def _disk(self, path: str | None) -> ToolResult:
        try:
            usage = psutil.disk_usage(path or "C:\\")
        except (FileNotFoundError, PermissionError, OSError) as error:
            return ToolResult.failure(f"I couldn't read that disk: {error}")
        free_gb = self._gb(usage.free)
        total_gb = self._gb(usage.total)
        return ToolResult.success(
            f"Disk usage is {usage.percent:.0f} percent - {free_gb:.1f} gigabytes free of {total_gb:.1f}.",
            metric="disk",
            percent=round(usage.percent, 1),
            free_gb=round(free_gb, 1),
            total_gb=round(total_gb, 1),
        )

    def _battery(self) -> ToolResult:
        battery = psutil.sensors_battery()
        if battery is None:
            return ToolResult.failure("This computer doesn't report a battery.", metric="battery")
        state = "charging" if battery.power_plugged else "on battery"
        return ToolResult.success(
            f"Battery is at {battery.percent:.0f} percent and {state}.",
            metric="battery",
            percent=round(battery.percent, 1),
            plugged_in=bool(battery.power_plugged),
        )

    # ------------------------------------------------------------------ #
    # Aggregate
    # ------------------------------------------------------------------ #
    def _summary(self) -> ToolResult:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        parts = [f"CPU usage is {cpu:.0f} percent", f"memory usage is {mem.percent:.0f} percent"]

        battery = psutil.sensors_battery()
        alerts: list[str] = []
        if battery is not None:
            parts.append(f"battery is at {battery.percent:.0f} percent")
            if battery.percent <= 20 and not battery.power_plugged:
                alerts.append("Battery is low.")

        spoken = "Your system is operating normally. " + ", ".join(parts) + "."
        if alerts:
            spoken += " " + " ".join(alerts)

        return ToolResult.success(
            spoken,
            metric="all",
            cpu_percent=round(cpu, 1),
            memory_percent=round(mem.percent, 1),
            battery_percent=round(battery.percent, 1) if battery else None,
            alerts=alerts,
        )

    @staticmethod
    def _gb(byte_count: int) -> float:
        return byte_count / (1024 ** 3)
