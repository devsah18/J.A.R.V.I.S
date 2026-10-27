"""VARSHA - personal desktop AI assistant (entry point).

Supports interactive CLI, hands-free voice, the PySide6 HUD, one-shot commands,
and renaming the assistant.
"""

from __future__ import annotations

import argparse
import logging

import config
from core.assistant import Assistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{config.ASSISTANT_NAME} - personal AI assistant")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--cli", action="store_true", help="interactive terminal mode")
    modes.add_argument("--gui", action="store_true", help="holographic HUD mode")
    modes.add_argument("--voice", action="store_true", help="hands-free voice mode")
    parser.add_argument("--rename", metavar="NAME", help="rename the assistant and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    parser.add_argument("command", nargs="*", help="optional one-shot command to run and exit")
    return parser


_APP_LOGGERS = ("core", "ai", "tools", "voice", "ui", "memory")


def _configure_logging(verbose: bool) -> None:
    """Show VARSHA's own logs; keep noisy third-party loggers quiet."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    level = logging.DEBUG if verbose else logging.INFO
    for name in _APP_LOGGERS:
        logging.getLogger(name).setLevel(level)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    if args.rename:
        print(f"Assistant renamed to: {config.set_assistant_name(args.rename)}")
        return 0

    assistant = Assistant()

    if args.command:
        assistant.handle(" ".join(args.command))
        return 0

    if args.cli:
        mode = "cli"
    elif args.gui:
        mode = "gui"
    elif args.voice:
        mode = "voice"
    else:
        mode = "auto"
    assistant.start(mode=mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
