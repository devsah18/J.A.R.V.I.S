# VARSHA — Personal AI Assistant

A voice-first personal AI assistant for the desktop, in the spirit of JARVIS:
one intelligence layer that connects you to your computer, the web, your files
and your notes — spoken aloud, and able to act.

```
🎙️ USER SPEAKS → 🗣️ SPEECH-TO-TEXT → 🧠 AI BRAIN → 🛠️ TOOL → 💬 RESPONSE → 🔊 TEXT-TO-SPEECH
```

The text interface is secondary; when voice mode is active VARSHA speaks its
answers by default.

---

## Quick start

```bash
pip install -r requirements.txt
python main.py                # default: HUD if PySide6 is present, else CLI
python main.py --cli          # interactive terminal
python main.py --voice        # hands-free (needs PyAudio for the microphone)
python main.py "what is my cpu usage"   # one-shot command
python main.py --rename JARVIS          # rename the assistant (persisted to .env)
```

Voice mode needs a microphone backend:

```bash
pip install pipwin && pipwin install pyaudio   # Windows, for PyAudio
```

Without PyAudio, VARSHA still runs — it reports the missing backend and falls
back to text instead of failing.

---

## Modes

| Mode | Flag | Behaviour |
| --- | --- | --- |
| CLI | `--cli` | Type commands; printed replies. |
| Voice | `--voice` | Wake-word ("varsha") then continuous conversation; TTS replies. |
| HUD | `--gui` | PySide6 window with transcript, push-to-talk, voice toggle. |
| Auto | _(default)_ | HUD when PySide6 is installed, otherwise CLI. |

In voice mode, after the wake word VARSHA keeps listening for follow-ups until
you fall silent, so you do not have to repeat its name every time.

---

## What VARSHA can do

| Tool | Examples |
| --- | --- |
| **System** | "what's my CPU usage", "system status", "how's my battery" |
| **Apps** | "open Chrome", "close notepad" |
| **Browser** | "open github.com", "open youtube" |
| **Search** | "search for rust ownership", "google quantum computing" |
| **Files** | "read notes.txt", "list C:\Users", "find report files in .." |
| **Tasks** | "remind me to call home", "what are my tasks", "mark call home done" |
| **Memory** | "remember my editor is VS Code", "what is my editor", "forget my editor" |
| **Conversation** | "hello", "what time is it", "who are you", "what can you do" |

Destructive actions (deleting files, closing apps) are classified **high risk**
and require confirmation before they run.

---

## Architecture

```
                 👤 USER
                    │
              🎙️ MICROPHONE
                    │
             SPEECH-TO-TEXT          voice/speech_to_text.py
                    │
          ┌──────────────────┐
          │    AI BRAIN      │       ai/engine.py, ai/intents.py, ai/remote.py
          │ reasoning · plan │       ai/prompts.py, ai/model_manager.py
          └────────┬─────────┘
                   │
            ┌──────▼──────┐
            │   MEMORY    │         core/memory.py · memory/database.py (SQLite)
            └──────┬──────┘
                   │
            ┌──────▼──────┐
            │ TOOL ROUTER │         core/router.py
            └──────┬──────┘
                   │
            ┌──────▼──────────┐
            │  PERMISSIONS    │      core/permissions.py
            └──────┬──────────┘
                   │
       ┌───────────┼───────────┐
   COMPUTER     BROWSER      FILES        tools/system.py · apps.py · browser.py
       │           │           │         tools/search.py · files.py · tasks.py
       └───────────┼───────────┘
                   ▼
           RESPONSE GENERATOR             core/assistant.py
                   │
             TEXT-TO-SPEECH               voice/text_to_speech.py
                   │
              🔊 VARSHA → 👤 USER
```

Source layout:

```
config.py                 settings (env + .env), paths, feature flags
main.py                   entry point and CLI flags
ai/                       the brain: prompts, intent parser, engines, model manager
core/                     assistant orchestrator, context, memory facade,
                          permissions, router
tools/                    modular tools (base contract + one file per tool)
memory/                   SQLite persistence (facts, conversation log, tasks)
voice/                    speech-to-text, text-to-speech, wake word
ui/                       optional PySide6 HUD window
tests/                    unittest suite
```

---

## The AI brain

VARSHA works out of the box with a built-in, offline engine
(`ai/engine.py` → `LocalEngine`) that recognises command families and never
needs a network. Two optional LLM backends sit behind the same interface and are
selected automatically when configured and installed:

| `AI_BACKEND` | Requirement |
| --- | --- |
| `local` _(default)_ | none — always available |
| `ollama` | a running Ollama server (`OLLAMA_HOST`) |
| `openai` | `openai` package + `OPENAI_API_KEY` |

If a configured backend is unavailable, VARSHA logs it and falls back to local.

---

## Configuration

Override anything by setting environment variables, or editing `.env`
(created by `--rename`). Key settings:

```ini
ASSISTANT_NAME=VARSHA
VOICE_ENABLED=true          # speak replies when voice mode is on
TTS_ENABLED=true
TTS_RATE=180
STT_LANGUAGE=en-US
WAKE_WORD=varsha
CONVERSATION_TIMEOUT=30      # seconds of continuous listening after the wake word

AI_BACKEND=local             # local | ollama | openai
AI_MODEL=                    # e.g. gpt-4o-mini or llama3.1
OPENAI_API_KEY=
OLLAMA_HOST=http://localhost:11434

CONFIRM_HIGH_RISK=true       # confirm destructive actions
CONFIRM_MEDIUM_RISK=false
```

---

## Safety

VARSHA is an assistant, not an unrestricted agent. Every action passes through
the router and the permission system, which classifies it by risk and asks for
confirmation when necessary (with the CLI, the voice, or a GUI dialog depending
on the front-end). It never claims an action succeeded when it failed, and it
never fabricates results or memories.

---

## Tests

```bash
python -m unittest discover -s tests
```

Covers the intent parser, memory (SQLite), each tool, the router and permission
policy, and the end-to-end assistant pipeline.

---

## Status

Working: voice-first pipeline, offline AI engine, seven tools, SQLite memory and
tasks, permission system, CLI and voice front-ends, and an optional PySide6 HUD.

Extensible next steps (architecture is ready for them): plugins/tools, calendar
and email, screen awareness, scheduled routines, and proactive notifications.
