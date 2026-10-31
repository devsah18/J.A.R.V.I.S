"""Rule-based natural-language understanding for the built-in engine.

Deliberately dependency-free: it recognises the command families the assistant
supports and turns them into either a direct reply or a tool action. When a
configured LLM backend is present it supersedes this parser, but the built-in
engine keeps VARSHA fully functional offline.
"""

from __future__ import annotations

import re
from datetime import datetime

from ai.response import EngineResponse
from core.router import ActionRequest

try:
    from tools.apps import APP_ALIASES
except Exception:  # pragma: no cover - import guard
    APP_ALIASES = {}


WEBSITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "stack overflow": "https://stackoverflow.com",
    "chatgpt": "https://chat.openai.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "news": "https://news.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "flipkart": "https://www.flipkart.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "gemini": "https://gemini.google.com",
    "claude": "https://claude.ai",
}

_GREETINGS = {
    "hi", "hello", "hey", "yo", "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening",
    "how are you", "how are you doing", "how are you today", "how do you do", "how is it going",
    # Hindi Greetings
    "namaste", "namaskar", "pranam", "kya haal hai", "kaise ho", "kaise hain aap",
    "नमस्ते", "नमस्कार", "प्रणाम", "कैसे हो", "क्या हाल है", "शुभ प्रभात",
    # Marathi Greetings
    "kasa ahes", "kase ahat", "kashi ahes", "kay challay", "shubh sakal", "shubh sandhyakal",
    "कसा आहेस", "कसे आहात", "कशी आहेस", "काय चाललंय", "शुभ सकाळ", "शुभ संध्याकाळ",
}
_THANKS = {
    "thanks", "thank you", "thanks a lot", "much appreciated", "cheers",
    "dhanyawad", "shukriya", "bahut dhanyawad", "धन्यवाद", "शुक्रिया",
    "aabhar", "khup aabhar", "आभार", "खूप आभार",
}

_URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^[\w-]+(\.[\w-]+)+(/\S*)?$")
_LEADING_ARTICLE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_KEY_ARTICLE_RE = re.compile(r"^(?:my|our|the|your|his|her)\s+", re.IGNORECASE)


class IntentParser:
    def __init__(self, memory=None):
        self._memory = memory

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def parse(self, text: str, context) -> EngineResponse | None:
        raw = (text or "").strip()
        if not raw:
            return None
        low = raw.lower().rstrip(" .!?")

        if low in _GREETINGS or (low.split(" ")[0] in {"hi", "hello", "hey"} and len(low.split()) <= 2):
            if any(k in low for k in ("kasa ahes", "kase ahat", "kashi ahes", "kay challay", "कसा", "कसे आहात", "कशी आहेस")):
                return EngineResponse(speech="मी अगदी मजेत आहे! तुम्ही कसे आहात? मी तुम्हाला कशी मदत करू शकतो?")
            if any(k in low for k in ("namaskar", "shubh sakal", "नमस्कार", "शुभ सकाळ")):
                return EngineResponse(speech=f"नमस्कार! मी {self._name()} आहे. मी तुम्हाला कशी मदत करू शकतो?")
            if any(k in low for k in ("namaste", "pranam", "नमस्ते", "प्रणाम")):
                return EngineResponse(speech=f"नमस्ते! मैं {self._name()} हूँ। मैं आपकी क्या मदद कर सकता हूँ?")
            if any(k in low for k in ("kaise ho", "kya haal hai", "कैसे हो", "क्या हाल है")):
                return EngineResponse(speech="मैं बिल्कुल ठीक हूँ! आप कैसे हैं?")
            if any(k in low for k in ("how are you", "how do you do", "how is it going")):
                return EngineResponse(speech=f"I'm doing great, thank you! How can I help you today?")
            return EngineResponse(speech=f"{self._name()} online. What do you need?")
        if low in _THANKS:
            if any(k in low for k in ("aabhar", "आभार")):
                return EngineResponse(speech="काही हरकत नाही! आपले स्वागत आहे.")
            if any(k in low for k in ("dhanyawad", "shukriya", "धन्यवाद", "शुक्रिया")):
                return EngineResponse(speech="आपका स्वागत है!")
            return EngineResponse(speech="Anytime.")
        if re.search(r"(who are you|what are you|your name|aap kaun ho|tum kaun ho|aapka naam kya hai|आप कौन हो|तुम कौन हो|आपका नाम क्या है|आप कौन हैं|tu kon ahes|tumhi kon ahat|tujhe naav|tumche naav|तुम्ही कोण|तू कोण|नाव काय)", low):
            if any(k in low for k in ("tu kon", "tumhi kon", "tujhe naav", "tumche naav", "कोण", "नाव")):
                return EngineResponse(speech=f"मी {self._name()} आहे, तुमचा वैयक्तिक AI सहाय्यक.")
            if any(k in low for k in ("aap kaun", "tum kaun", "aapka naam", "कौन", "नाम")):
                return EngineResponse(speech=f"मैं {self._name()} हूँ, आपका व्यक्तिगत AI सहायक।")
            return EngineResponse(speech=f"I'm {self._name()}, your personal assistant.")
        if re.search(r"\b(what can you do|help|your capabilities|what are you capable of|kya kar sakte ho|madad|मदद|क्या कर सकते हो|काय करू शकतोस|मदत)\b", low):
            return EngineResponse(speech=self._help_text())

        for handler in (
            self._time_date,
            self._exam_cmd,
            self._calc_cmd,
            self._image_cmd,
            self._weather_cmd,
            self._news_cmd,
            self._jokes_cmd,
            self._finance_cmd,
            self._dictionary_cmd,
            self._system,
            self._memory_cmd,
            self._tasks_cmd,
            self._maps_cmd,
            self._files_cmd,
            self._wiki_cmd,
            self._search,
            self._open,
            self._close,
            self._game_cmd,
        ):
            response = handler(raw, low, context)
            if response is not None:
                return response
        return None

    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Calculator / Math
    # ------------------------------------------------------------------ #
    def _calc_cmd(self, raw, low, context) -> EngineResponse | None:
        calc_prefix = re.match(r'^(?:calculate|compute|eval|evaluate)\s+(.+)$', low)
        if calc_prefix:
            return EngineResponse(action=ActionRequest('calculator', {'expression': calc_prefix.group(1).strip()}))

        math_op = re.search(r'\b\d+(?:\.\d+)?\s*(?:[\+\-\*/\^%]|plus|minus|times|into|multiplied by|divided by|over|to the power of)\s*\d+', low)
        percent_op = re.search(r'\b\d+(?:\.\d+)?\s*(?:%|percent)\s+of\s+\d+', low)
        sqrt_op = re.search(r'\b(?:square root|sqrt)\s+of\s+\d+', low)

        if math_op or percent_op or sqrt_op:
            # Check if prefixed by what is / what's / how much is
            what_is = re.match(r'^(?:what(?: is|\'s)|how much is)\s+(.+)$', low)
            expr = what_is.group(1).strip() if what_is else low
            return EngineResponse(action=ActionRequest('calculator', {'expression': expr}))
        return None

    # Time / date
    # ------------------------------------------------------------------ #
    def _time_date(self, raw, low, context) -> EngineResponse | None:
        now = datetime.now()
        is_marathi = any(w in low for w in ("kiti vajle", "vela kay", "kiti time", "konta divas", "tarikh kay", "वेळ", "वाजले", "तारीख", "दिवस"))
        is_hindi = any(w in low for w in ("samay", "kitne baje", "kya samay", "kya time", "samay kya", "समय", "कितने बजे", "तारीख", "din kya"))
        if re.search(r"\b(what time|the time|current time|time is it|samay|kitne baje|समय|बजे|kiti vajle|vela kay|वाजले|वेळ)\b", low):
            time_str = now.strftime('%I:%M %p').lstrip('0')
            if is_marathi:
                return EngineResponse(speech=f"सध्या {time_str} वाजले आहेत.")
            if is_hindi:
                return EngineResponse(speech=f"अभी समय {time_str} हुआ है।")
            return EngineResponse(speech=f"It's {time_str}.")
        if re.search(r"\b(what(?:'s| is)? the date|today'?s date|what day is it|aaj ki date|aaj ka din|तारीख|आज का दिन|aajchi tarikh|konta divas|आजची तारीख)\b", low):
            date_str = now.strftime('%A, %d %B %Y')
            if is_marathi:
                return EngineResponse(speech=f"आज {date_str} आहे.")
            if is_hindi:
                return EngineResponse(speech=f"आज {date_str} है।")
            return EngineResponse(speech=f"Today is {date_str}.")
        return None

    # ------------------------------------------------------------------ #
    # System status
    # ------------------------------------------------------------------ #
    def _system(self, raw, low, context) -> EngineResponse | None:
        if re.search(r"\b(cpu|processor|सीपीयू)\b", low):
            metric = "cpu"
        elif re.search(r"\b(ram|memory|रैम)\b", low):
            metric = "memory"
        elif re.search(r"\b(battery|charge|बैटरी)\b", low):
            metric = "battery"
        elif re.search(r"\b(disk|storage|drive|hard ?space|free space|स्टोरेज)\b", low):
            metric = "disk"
        elif re.search(r"\b(system status|status report|system report|system health|how(?:'s| is) the system|system kaisa hai|सिस्टम)\b", low):
            metric = "all"
        else:
            return None
        return EngineResponse(action=ActionRequest("system", {"metric": metric}))

    # ------------------------------------------------------------------ #
    # Memory
    # ------------------------------------------------------------------ #
    def _memory_cmd(self, raw, low, context) -> EngineResponse | None:
        if self._memory is None:
            return None

        if re.match(r"^remember(?: that)?\s+(.+)$", low):
            return self._remember(raw)

        if re.search(r"(what do you know about me|list (?:your )?memories|what do you remember)", low):
            facts = self._memory.all_facts()
            if not facts:
                return EngineResponse(speech="I don't have anything stored about you yet.")
            items = "; ".join(f"{k}: {v}" for k, v in list(facts.items())[:6])
            return EngineResponse(speech=f"Here's what I remember: {items}.")

        match = re.match(r"^(?:what(?:'s| is) my|do you remember|what do you remember about)\s+(.+)$", low)
        if match:
            key = self._normalize_key(match.group(1))
            value = self._memory.recall(key)
            if value is None:
                return EngineResponse(speech=f"I don't have anything stored for '{key}'.")
            return EngineResponse(speech=f"Your {key} is {value}.")

        match = re.match(r"^forget(?:\s+about)?\s+(.+)$", low)
        if match:
            key = self._normalize_key(match.group(1))
            forgotten = self._memory.forget(key)
            return EngineResponse(speech=f"Forgotten: {key}." if forgotten else f"I had nothing stored for '{key}'.")
        return None

    def _remember(self, raw: str) -> EngineResponse:
        original = re.sub(r"^remember\s+", "", raw.strip(), flags=re.IGNORECASE)
        original = re.sub(r"^that\s+", "", original, flags=re.IGNORECASE)
        parts = re.split(r"\s+is\s+|\s*=\s*", original, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            key, value = parts[0].strip(), parts[1].strip()
        else:
            key, value = original.strip(), original.strip()
        key = self._normalize_key(key)
        self._memory.remember(key, value)
        return EngineResponse(speech=f"Noted: {key} is {value}.")

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #
    def _tasks_cmd(self, raw, low, context) -> EngineResponse | None:
        match = re.match(r"^(?:remind me to|remind me|add (?:a )?task(?: to)?|add (?:a )?reminder to)\s+(.+)$", low)
        if match:
            return EngineResponse(action=ActionRequest("tasks", {"action": "add", "title": match.group(1).strip()}))

        if re.search(r"\b(what are my tasks|list (?:my )?tasks|my tasks|show (?:my )?tasks|any tasks)\b", low):
            return EngineResponse(action=ActionRequest("tasks", {"action": "list"}))

        match = re.match(r"^(?:remove|delete)\s+task\s+(.+)$", low)
        if match:
            return EngineResponse(action=ActionRequest("tasks", {"action": "remove", "title": match.group(1).strip()}))

        match = re.match(r"^(?:mark|complete|finish)\s+(.+?)(?:\s+(?:as\s+)?(?:done|complete))?$", low)
        if match:
            return EngineResponse(action=ActionRequest("tasks", {"action": "complete", "title": match.group(1).strip()}))
        return None

    # ------------------------------------------------------------------ #
    # Files
    # ------------------------------------------------------------------ #
    def _files_cmd(self, raw, low, context) -> EngineResponse | None:
        match = re.match(r"^(?:read|show me|cat)\s+(?:file\s+)?(.+)$", low)
        if match:
            return EngineResponse(action=ActionRequest("files", {"action": "read", "path": match.group(1).strip()}))

        match = re.match(r"^(?:list files in|list|what(?:'s| is) in)\s+(.+)$", low)
        if match and low.split(" ")[0] in {"list", "what's", "what"}:
            return EngineResponse(action=ActionRequest("files", {"action": "list", "path": match.group(1).strip()}))

        match = re.match(r"^(?:find|locate)\s+(.+?)\s+files?(?:\s+in\s+(.+))?$", low)
        if match:
            pattern = match.group(1).strip()
            directory = (match.group(2) or ".").strip()
            return EngineResponse(
                action=ActionRequest("files", {"action": "search", "path": directory, "pattern": f"*{pattern}*"})
            )

        match = re.match(r"^(?:delete|remove)\s+file\s+(.+)$", low)
        if match:
            return EngineResponse(action=ActionRequest("files", {"action": "delete", "path": match.group(1).strip()}))

        match = re.match(
            r"^(?:create|make|new)\s+(?:a\s+)?file\s+(?:called\s+|named\s+)?(.+?)(?:\s+with\s+(.+))?$", low
        )
        if match:
            path = match.group(1).strip()
            content = match.group(2) or ""
            return EngineResponse(action=ActionRequest("files", {"action": "write", "path": path, "content": content}))
        return None

    # ------------------------------------------------------------------ #
    # Web search
    # ------------------------------------------------------------------ #
    def _search(self, raw, low, context) -> EngineResponse | None:
        match = re.match(r"^(?:search(?: the web)?(?: for)?|google|look up)\s+(.+)$", low)
        if match:
            return EngineResponse(action=ActionRequest("search", {"query": match.group(1).strip()}))
        return None

    # ------------------------------------------------------------------ #
    # Open / close
    # ------------------------------------------------------------------ #
    def _open(self, raw, low, context) -> EngineResponse | None:
        target = None
        # Prefix match: "open chrome", "launch vs code", "kholo youtube", "ughada calculator"
        prefix_match = re.match(r"^(?:open|launch|start|go to|kholo|ughada|suru kara|chalu karo|खोलो|उघडा|सुरू करा|चालू करा)\s+(.+)$", low)
        if prefix_match:
            target = prefix_match.group(1).strip()
        else:
            # Suffix match: "youtube kholo", "chrome open karo", "notepad chalu karo", "calculator ughada"
            suffix_match = re.match(r"^(.+?)\s*(?:open karo|kholo|chalu karo|start karo|ughada|suru kara|खोलो|उघडा|चालू करा|सुरू करा)$", low)
            if suffix_match:
                target = suffix_match.group(1).strip()

        if not target:
            return None

        target = self._clean_target(target)

        if _URL_RE.match(target) or _DOMAIN_RE.match(target):
            return EngineResponse(action=ActionRequest("browser", {"url": target}))
        if target in WEBSITES:
            return EngineResponse(action=ActionRequest("browser", {"url": WEBSITES[target]}))
        if target in {"the project", "project", "my project"}:
            if context.current_project:
                return EngineResponse(action=ActionRequest("apps", {"action": "open", "name": context.current_project}))
            return EngineResponse(speech="Which project should I open?")
        return EngineResponse(action=ActionRequest("apps", {"action": "open", "name": target}))

    def _close(self, raw, low, context) -> EngineResponse | None:
        target = None
        prefix_match = re.match(r"^(?:close|quit|exit|kill|stop|band karo|band kara|बंद करो|बंद करा)\s+(.+)$", low)
        if prefix_match:
            target = prefix_match.group(1).strip()
        else:
            suffix_match = re.match(r"^(.+?)\s*(?:close karo|band karo|band kara|stop karo|बंद करो|बंद करा)$", low)
            if suffix_match:
                target = suffix_match.group(1).strip()

        if not target:
            return None
        target = self._clean_target(target)
        return EngineResponse(action=ActionRequest("apps", {"action": "close", "name": target}))

    # ------------------------------------------------------------------ #
    # Game mode (truth, dare, imposter)
    # ------------------------------------------------------------------ #
    def _game_cmd(self, raw, low, context) -> EngineResponse | None:
        # Start a game: "start truth", "play dare", "begin imposter"
        start_match = re.match(r"^(?:start|play|begin)\s+(truth|dare|imposter)$", low)
        if start_match:
            game = start_match.group(1)
            return EngineResponse(action=ActionRequest("game", {"game": game, "action": "start"}))
        # Next prompt for truth/dare: "next truth", "next dare", or just "next"
        next_match = re.match(r"^next\s*(truth|dare)?$", low)
        if next_match:
            game = next_match.group(1) or ""
            params = {"action": "next"}
            if game:
                params["game"] = game
            return EngineResponse(action=ActionRequest("game", params))
        # Imposter specific commands
        # add player: "add player <name>"
        add_match = re.match(r"^add\s+player\s+(.+)$", low)
        if add_match:
            return EngineResponse(action=ActionRequest("game", {"game": "imposter", "action": "add", "player": add_match.group(1).strip()}))
        # begin imposter after players added
        if low == "begin imposter":
            return EngineResponse(action=ActionRequest("game", {"game": "imposter", "action": "begin"}))
        # guess imposter: "guess <name>"
        guess_match = re.match(r"^guess\s+(.+)$", low)
        if guess_match:
            return EngineResponse(action=ActionRequest("game", {"game": "imposter", "action": "guess", "player": guess_match.group(1).strip()}))
        # reveal imposter
        if low in {"reveal imposter", "show imposter"}:
            return EngineResponse(action=ActionRequest("game", {"game": "imposter", "action": "reveal"}))
        # end game
        if low.startswith("end "):
            end_match = re.match(r"^end\s+(truth|dare|imposter)$", low)
            if end_match:
                return EngineResponse(action=ActionRequest("game", {"game": end_match.group(1), "action": "end"}))
        return None

    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # NEET / JEE / CET Exam Prep & Solver
    # ------------------------------------------------------------------ #
    def _exam_cmd(self, raw, low, context) -> EngineResponse | None:
        # 1. Syllabus requests
        if "syllabus" in low or "weightage" in low or "high yield" in low:
            exam = "NEET"
            if "jee" in low:
                exam = "JEE"
            elif "cet" in low:
                exam = "CET"

            subject = ""
            for sub in ("physics", "chemistry", "mathematics", "maths", "math", "biology", "botany", "zoology"):
                if sub in low:
                    subject = "Mathematics" if "math" in sub else sub.capitalize()
                    break
            return EngineResponse(action=ActionRequest("exam", {"action": "syllabus", "exam": exam, "subject": subject}))

        # 2. Practice questions / Mock quiz
        if re.search(r"\b(practice question|practice mcq|quiz me|ask me a question|give me a question|mock question|test question|test me)\b", low) or (
            any(k in low for k in ("neet", "jee", "cet")) and any(q in low for q in ("question", "mcq", "quiz", "problem"))
        ):
            if not low.startswith(("solve", "how to solve", "answer")):
                exam = "NEET"
                if "jee" in low:
                    exam = "JEE"
                elif "cet" in low:
                    exam = "CET"

                subject = ""
                for sub in ("physics", "chemistry", "mathematics", "maths", "math", "biology"):
                    if sub in low:
                        subject = "Mathematics" if "math" in sub else sub.capitalize()
                        break
                return EngineResponse(action=ActionRequest("exam", {"action": "quiz", "exam": exam, "subject": subject}))

        # 3. Solve question / MCQ
        solve_match = re.search(r"^(?:solve|how to solve|answer)\s*(?:this)?\s*(?:question|mcq|problem|jee|neet|cet|chemistry|physics|biology|maths|math)?\s*[:\s]\s*(.+)$", low)
        if solve_match:
            q_text = solve_match.group(1).strip()
            q_cleaned = re.sub(r"^(?:neet|jee|cet)?\s*(?:question|mcq|problem)?\s*[:\s]\s*", "", q_text, flags=re.IGNORECASE)
            exam = "JEE" if "jee" in low else ("CET" if "cet" in low else "NEET")
            return EngineResponse(action=ActionRequest("exam", {"action": "solve", "exam": exam, "question": q_cleaned or q_text}))

        # 4. User answering a quiz option: e.g. "option B", "B"
        ans_match = re.match(r"^(?:option|choice|answer is|the answer is)?\s*([a-d])\b", low)
        if ans_match and context and any(turn.content and "Options: (" in turn.content for turn in context.recent(2)):
            return EngineResponse(action=ActionRequest("exam", {"action": "check", "choice": ans_match.group(1).upper()}))

        return None


    # ------------------------------------------------------------------ #
    # Image Generation & Retrieval (AI & Real)
    # ------------------------------------------------------------------ #
    def _image_cmd(self, raw, low, context) -> EngineResponse | None:
        img_keywords = (
            "image of", "photo of", "picture of", "photograph of",
            "generate image", "create image", "ai image", "real image",
            "real photo", "draw ", "make an image", "show me a photo",
            "show me an image", "show me a picture"
        )
        if any(k in low for k in img_keywords):
            is_real = any(w in low for w in ("real photo", "real image", "actual photo", "real picture", "photograph of"))
            is_ai = any(w in low for w in ("ai image", "ai photo", "draw", "generate", "create image", "make an image"))
            kind = "real" if is_real else ("ai" if is_ai else "auto")

            cleaned = re.sub(
                r"^(?:generate|create|make|draw|show me|find|get)?\s*(?:an?|the)?\s*(?:ai|real|actual)?\s*(?:image|photo|picture|photograph)?\s*(?:of)?\s*",
                "",
                low,
                flags=re.IGNORECASE,
            ).strip()
            prompt_text = cleaned or raw
            return EngineResponse(action=ActionRequest("image", {"prompt": prompt_text, "kind": kind}))
        return None

    # Weather
    # ------------------------------------------------------------------ #
    def _weather_cmd(self, raw, low, context) -> EngineResponse | None:
        if re.search(r"^(मौसम कैसा है|mausam kaisa hai|weather|how(?:'s| is) the weather|forecast)$", low):
            return EngineResponse(action=ActionRequest("weather", {"location": "Delhi"}))
        match = re.search(r"(?:weather|forecast|temperature|climate|mausam|मौसम)\s+(?:in|for|at|me|mein|ka)?\s*([a-zA-Z\u0900-\u097F]+)", low)
        if match:
            loc = match.group(1).strip()
            if loc in ("kaisa", "hai", "batao", "today", "tomorrow", "now", "कैसा", "है", "बताओ", "का", "mein", "me"):
                loc = "Delhi"
            is_forecast = "forecast" in low or "tomorrow" in low or "kal" in low
            return EngineResponse(action=ActionRequest("weather", {"location": loc, "forecast": is_forecast}))
        return None

    # ------------------------------------------------------------------ #
    # Maps / Directions / Places
    # ------------------------------------------------------------------ #
    def _maps_cmd(self, raw, low, context) -> EngineResponse | None:
        # Directions: "directions from X to Y", "route X to Y", "how to reach X from Y"
        dir_match = re.search(
            r"(?:directions?|route|how to reach)\s+(?:from\s+)?(.+?)\s+(?:to|until|till|via)\s+(.+)$", low
        )
        if dir_match:
            return EngineResponse(action=ActionRequest("maps", {
                "action": "directions",
                "origin": dir_match.group(1).strip(),
                "destination": dir_match.group(2).strip(),
            }))

        # Distance: "distance between X and Y"
        dist_match = re.search(r"distance\s+between\s+(.+?)\s+and\s+(.+)$", low)
        if dist_match:
            return EngineResponse(action=ActionRequest("maps", {
                "action": "distance",
                "origin": dist_match.group(1).strip(),
                "destination": dist_match.group(2).strip(),
            }))

        # Generic "open map" / "maps" trigger (check before place search so
        # "show me the map" doesn't get parsed as a search for "the map").
        if re.search(r"\b(maps|google maps|open map|show map|show me the map)\b", low):
            return EngineResponse(action=ActionRequest("maps", {"action": "search", "query": "my location"}))

        # Place search — only maps-specific phrasing (avoids stealing plain
        # "search for X" queries, which belong to the web-search tool).
        search_match = re.search(
            r"(?:find|locate|where is|show me)\s+(.+?)\s*(?:near me|on the map|map|maps|station|restaurant|hotel|cafe|shop|mall|market|airport|school|hospital)?\s*$", low
        )
        if search_match and re.search(r"\b(near me|on the map|map|maps|station|restaurant|hotel|cafe|shop|mall|market|airport|school|hospital)\b", low):
            return EngineResponse(action=ActionRequest("maps", {
                "action": "search",
                "query": search_match.group(1).strip(),
            }))
        return None

    # ------------------------------------------------------------------ #
    # News
    # ------------------------------------------------------------------ #
    def _news_cmd(self, raw, low, context) -> EngineResponse | None:
        if re.search(r"\b(tech news|technology headlines|hacker news)\b", low):
            return EngineResponse(action=ActionRequest("news", {"category": "tech"}))
        if re.search(r"\b(news|headlines|top stories|breaking news|what(?:'s| is) in the news|samachar|taza khabar|समाचार|खबर)\b", low):
            return EngineResponse(action=ActionRequest("news", {"category": "world"}))
        return None

    # ------------------------------------------------------------------ #
    # Jokes & Trivia
    # ------------------------------------------------------------------ #
    def _jokes_cmd(self, raw, low, context) -> EngineResponse | None:
        if re.search(r"\b(programming joke|coding joke|developer joke)\b", low):
            return EngineResponse(action=ActionRequest("jokes", {"kind": "programming"}))
        if re.search(r"(joke|make me laugh|tell me a joke|funny|chutkula|joke sunao|chutkula sunao|जोक|चुटकुला)", low):
            return EngineResponse(action=ActionRequest("jokes", {"kind": "joke"}))
        if re.search(r"\b(random fact|tell me a fact|trivia|fact of the day|did you know)\b", low):
            return EngineResponse(action=ActionRequest("jokes", {"kind": "fact"}))
        return None

    # ------------------------------------------------------------------ #
    # Finance & Crypto
    # ------------------------------------------------------------------ #
    def _finance_cmd(self, raw, low, context) -> EngineResponse | None:
        match = re.search(r"\b(?:price of|crypto price|value of|exchange rate of)\s+(.+)$", low)
        if match:
            asset = match.group(1).strip()
            return EngineResponse(action=ActionRequest("finance", {"asset": asset}))
        if re.search(r"\b(bitcoin price|btc price|crypto|crypto price)\b", low):
            return EngineResponse(action=ActionRequest("finance", {"asset": "bitcoin"}))
        if re.search(r"\b(ethereum price|eth price)\b", low):
            return EngineResponse(action=ActionRequest("finance", {"asset": "ethereum"}))
        match = re.search(r"\b([a-z]{3}\s+(?:to|in)\s+[a-z]{3})\b", low)
        if match:
            return EngineResponse(action=ActionRequest("finance", {"asset": match.group(1)}))
        return None

    # ------------------------------------------------------------------ #
    # Dictionary
    # ------------------------------------------------------------------ #
    def _dictionary_cmd(self, raw, low, context) -> EngineResponse | None:
        match = re.match(r"^(?:define|meaning of|definition of|what does\s+(.+?)\s+mean)\s*(.*)$", low)
        if match:
            word = (match.group(1) or match.group(2) or "").strip()
            if word:
                return EngineResponse(action=ActionRequest("dictionary", {"word": word}))
        return None

    # ------------------------------------------------------------------ #
    # Wikipedia / Knowledge
    # ------------------------------------------------------------------ #
    def _wiki_cmd(self, raw, low, context) -> EngineResponse | None:
        # Prefix patterns: "what is X", "who is X", "tell me about X", "explain X"
        match = re.match(r"^(?:wikipedia|who is|who was|tell me about|what is(?: an?| the)?|what are(?: the)?|explain|describe)\s+(.+)$", low)
        if match:
            query = match.group(1).strip()
            # Avoid routing system/time/weather/calc queries to wiki
            if not any(k in query for k in ("the time", "the date", "system", "cpu", "ram", "battery", "my name", "weather", "today", "tomorrow")):
                # Strip leading articles
                query = re.sub(r"^(?:an?|the)\s+", "", query).strip()
                if query:
                    return EngineResponse(action=ActionRequest("wikipedia", {"query": query}))

        # Suffix patterns for Hindi / Marathi: "photosynthesis kya hai", "gravity kay ahe"
        suffix_match = re.search(r"^(.+?)\s*(?:kya hai|kya hota hai|kay ahe|kay asate|बद्दल माहिती द्या|बद्दल माहिती सांगा|म्हणजे काय)\s*$", low)
        if suffix_match:
            query = suffix_match.group(1).strip()
            if query and not any(k in query for k in ("time", "samay", "weather", "mausam")):
                return EngineResponse(action=ActionRequest("wikipedia", {"query": query}))

        return None

    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_key(key: str) -> str:
        return _KEY_ARTICLE_RE.sub("", key.strip().lower()).strip()

    @staticmethod
    def _clean_target(target: str) -> str:
        target = target.strip().strip("\"'").strip()
        return _LEADING_ARTICLE_RE.sub("", target).strip()

    @staticmethod
    def _name() -> str:
        import config

        return config.ASSISTANT_NAME

    def _help_text(self) -> str:
        return (
            "I can open and close applications, run web searches, open sites, read your system status, "
            "manage files and tasks, and remember things you ask me to. Just tell me what you need."
        )
