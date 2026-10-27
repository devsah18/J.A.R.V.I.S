'''Game tool – lightweight party games (truth, dare, imposter).

The tool stores a very simple in‑memory session (single global session
sufficient for a single user) and returns spoken strings that can be
read aloud by the assistant.
'''

from __future__ import annotations

import random
from typing import Any, Dict, Set

from tools.base import ParamSpec, Risk, Tool, ToolResult

# Simple static prompt banks
_TRUTHS = [
    "What is your biggest fear?",
    "What is a secret you’ve never told anyone?",
    "What is the most embarrassing thing you’ve ever done?",
    "What is a hobby you wish you had more time for?",
    "What is a memory that always makes you smile?",
]

_DARES = [
    "Do 10 push‑ups.",
    "Sing the chorus of your favourite song aloud.",
    "Swap a piece of clothing with someone nearby.",
    "Talk in a funny accent for the next minute.",
    "Send a random emoji to a contact you haven’t messaged in a week.",
]

# Global in‑memory session store – keyed by a static id because the
# current architecture does not pass a per‑conversation identifier to tools.
_SESSIONS: Dict[str, Dict[str, Any]] = {}


class GameTool(Tool):
    name = "game"
    description = (
        "Play simple party games: truth, dare, or imposter. "
        "The tool manages a lightweight session and returns text prompts that can be spoken."
    )
    risk = Risk.LOW
    params = (
        ParamSpec("game", "Which game to play: truth, dare, or imposter", required=True),
        ParamSpec("action", "Action to perform: start, next, add, begin, guess, end", required=False),
        ParamSpec("player", "Player name (used for imposter guesses or adding players)", required=False),
    )

    def _session(self) -> Dict[str, Any]:
        """Return the dictionary representing the current session.
        A single global session keyed by ``default`` is used because the tool
        receives no explicit conversation identifier.
        """
        return _SESSIONS.setdefault("default", {})

    # ------------------------------------------------------------------ #
    # Core logic
    # ------------------------------------------------------------------ #
    def run(self, game: str, action: str = "start", player: str | None = None, **kwargs) -> ToolResult:
        game = game.lower()
        action = (action or "").lower()
        sess = self._session()

        # --- start a new game ------------------------------------------------
        if action == "start":
            sess.clear()
            sess["game"] = game
            if game in ("truth", "dare"):
                sess["used"] = set()  # type: ignore[assignment]
                return ToolResult.success(f"Started {game} game. Say ‘next’ for a prompt.", game=game)
            if game == "imposter":
                sess["players"] = []
                sess["imposter"] = None
                return ToolResult.success(
                    "Started Imposter game. Add players using ‘add player <name>’ and then ‘begin imposter’.",
                    game=game,
                )
            return ToolResult.failure(f"Unknown game '{game}'.")

        # --- truth / dare next prompt ---------------------------------------
        if game in ("truth", "dare") and action == "next":
            pool = _TRUTHS if game == "truth" else _DARES
            used: Set[str] = sess.get("used", set())
            remaining = [p for p in pool if p not in used]
            if not remaining:  # all used – start over
                used.clear()
                remaining = pool[:]
            prompt = random.choice(remaining)
            used.add(prompt)
            sess["used"] = used
            return ToolResult.success(prompt, game=game)

        # --- imposter actions ------------------------------------------------
        if game == "imposter":
            # add a player
            if action == "add":
                if not player:
                    return ToolResult.failure("Provide a player name to add.")
                players = sess.setdefault("players", [])
                if player in players:
                    return ToolResult.failure(f"Player '{player}' is already in the game.")
                players.append(player)
                return ToolResult.success(f"Added player {player}.", game=game)
            # begin – choose the imposter
            if action == "begin":
                players = sess.get("players", [])
                if len(players) < 3:
                    return ToolResult.failure("Imposter needs at least 3 players.")
                imp = random.choice(players)
                sess["imposter"] = imp
                return ToolResult.success(
                    "Imposter assigned. Players can now guess using ‘guess <name>’.",
                    game=game,
                )
            # guess a player
            if action == "guess":
                if not player:
                    return ToolResult.failure("Provide a name to guess.")
                imp = sess.get("imposter")
                if not imp:
                    return ToolResult.failure(
                        "Imposter has not been assigned yet. Use ‘start imposter’ then add players and ‘begin’."
                    )
                correct = player == imp
                msg = f"Correct! {player} was the imposter." if correct else f"Wrong – {player} is not the imposter."
                return ToolResult.success(msg, game=game, correct=correct)
            # reveal the imposter (cheat)
            if action == "reveal":
                imp = sess.get("imposter")
                if not imp:
                    return ToolResult.failure("Imposter not chosen yet.")
                return ToolResult.success(f"The imposter is {imp}.", game=game)
        # --- end any game ----------------------------------------------------
        if action == "end":
            _SESSIONS.pop("default", None)
            return ToolResult.success(f"Ended {game} game.")

        return ToolResult.failure("Unrecognised command for game tool.")

        return ToolResult.failure("Unrecognised command for game tool.")

