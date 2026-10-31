import json
import os
import sys
import time
import sqlite3
import urllib.request
import urllib.parse
import base64
import io
import re
import secrets
import threading
import uuid
from pathlib import Path
import psutil

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify, send_from_directory, session
from core.router import ActionRequest
from core.memory import Memory
from memory.database import Database
from tools.files import FilesTool
from tools.base import Risk, ToolResult
from tools.image import ImageTool

try:
    from study_lib.knowledge import KB, KnowledgeBase
    from study_lib.qa import QAEngine
except Exception:
    KB = KnowledgeBase = QAEngine = None

try:
    from voice.speech_to_text import SpeechToText, OK
except Exception:
    SpeechToText = None
    OK = "ok"

try:
    from voice.text_to_speech import TextToSpeech
except Exception:
    TextToSpeech = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"},
)


@app.before_request
def _ensure_web_session():
    session.permanent = True
    session.setdefault("web_user_id", uuid.uuid4().hex)


def _current_web_user():
    try:
        return session.get("web_user_id", "guest")
    except RuntimeError:
        return "guest"

# Database Path
DB_PATH = os.path.join(PROJECT_ROOT, "data", "jarvis_web.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT UNIQUE,
            type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_identifier TEXT,
            sender TEXT,
            message TEXT,
            tag TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# In-memory OTP storage: {identifier: {"otp": "123456", "expires": timestamp}}
_OTP_STORE = {}

# Translation Helpers
def translate_text(text: str, source: str = "auto", target: str = "en") -> str:
    """Translates text using Google Translate API.
    Supports English (en), Hindi (hi), Marathi (mr).
    """
    if not text or not text.strip():
        return text
    target_lang = {"en": "en", "hi": "hi", "mr": "mr"}.get(target, "en")
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl="
               + source + "&tl=" + target_lang + "&dt=t&q=" + urllib.parse.quote(text))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return "".join([part[0] for part in data[0] if part[0]])
    except Exception as e:
        print(f"[translate_text error]: {e}")
        return text

def is_non_english_text(text: str) -> bool:
    """Detect Devanagari script (Hindi/Marathi) or common Hinglish/Marathi transliteration."""
    if re.search(r"[\u0900-\u097F]", text):
        return True
    hinglish_words = {"namaste", "kaise", "samay", "kya", "mausam", "chutkula", "dhanyawad",
                      "shukriya", "aap", "tum", "batao", "sunao", "karo", "hai", "hain", "kaun",
                      "marathi", "kasa", "kay", "kasla", "kiti", "chi", "mala"}
    words = set(re.findall(r"\w+", text.lower()))
    return len(words.intersection(hinglish_words)) >= 1

def is_hindi_text(text: str) -> bool:
    """True when the text is Devanagari or Hinglish."""
    return is_non_english_text(text)

# Lazily-initialized TTS/STT engines (never open audio at import time, so the
# app boots cleanly on headless Linux hosts like Render).
tts_engine = None
stt_engine = None

def _get_tts():
    global tts_engine
    if tts_engine is None and TextToSpeech is not None:
        try:
            tts_engine = TextToSpeech(enabled=True)
        except Exception as e:
            print(f"[app.py] TTS init failed: {e}")
            tts_engine = None
    return tts_engine

def _get_stt():
    global stt_engine
    if stt_engine is None and SpeechToText is not None:
        try:
            stt_engine = SpeechToText(enabled=True)
        except Exception as e:
            print(f"[app.py] STT init failed: {e}")
            stt_engine = None
    return stt_engine

# Lazy initialization of assistant
_assistant_instances = {}
_assistant_lock = threading.RLock()
_pending_web_actions = {}
_pending_web_actions_lock = threading.Lock()
WEB_FILES_DIR = os.path.join(PROJECT_ROOT, "data", "web_files")
os.makedirs(WEB_FILES_DIR, exist_ok=True)


class WebFilesTool(FilesTool):
    """Files tool limited to the web app's own workspace."""

    description = "Manage files in your private web workspace only."

    def run(self, action="", path="", content=None, destination="", pattern="*", **kwargs):
        user_root = os.path.join(WEB_FILES_DIR, _current_web_user())
        os.makedirs(user_root, exist_ok=True)
        root = os.path.realpath(user_root)

        def inside_root(value):
            expanded = os.path.expandvars(os.path.expanduser(value or "."))
            candidate = os.path.realpath(expanded if os.path.isabs(expanded) else os.path.join(root, expanded))
            try:
                return os.path.commonpath((root, candidate)) == root, candidate
            except ValueError:
                return False, candidate

        safe_path, target = inside_root(path)
        safe_destination, dest = inside_root(destination) if destination else (True, "")
        if not safe_path or not safe_destination:
            return ToolResult.failure("Web file access is limited to your private web workspace. Use a relative path inside that folder.")
        return super().run(action=action, path=target, content=content,
                           destination=dest, pattern=pattern, **kwargs)

def get_assistant():
    user = _current_web_user()
    with _assistant_lock:
        if user not in _assistant_instances:
            try:
                from core.assistant import Assistant
                memory_path = os.path.join(PROJECT_ROOT, "data", "web_memory", f"{user}.db")
                assistant = Assistant(memory=Memory(Database(memory_path)))
                assistant.router.register(WebFilesTool())
                assistant.router.register(ImageTool(output_dir=Path(WEB_FILES_DIR) / user / "images"))
                if hasattr(assistant.engine, "set_tool_schemas"):
                    assistant.engine.set_tool_schemas(assistant.router.schemas())
                _assistant_instances[user] = assistant
            except Exception as e:
                print(f"[app.py] Warning: Could not instantiate Assistant: {e}")
                return None
        return _assistant_instances[user]


def _web_execute(action, user, assistant=None):
    """Run a tool through the assistant router, requiring browser approval for changes."""
    command_origin = assistant is not None
    assistant = assistant or get_assistant()
    if assistant is None:
        return {"success": False, "error": "Assistant is unavailable."}, 503
    tool = assistant.router.get(action.tool)
    if tool is None:
        return {"success": False, "error": f"Unknown tool: {action.tool}"}, 404
    # Direct browser opening: launch on local desktop and forward URL to web client
    if action.tool == "browser":
        target = assistant.browser_tool._normalize(action.params.get("url", ""))
        if not target:
            return {"success": False, "error": "I need a website or URL to open."}, 200
        if urllib.parse.urlsplit(target).scheme.lower() not in {"http", "https", "mailto"}:
            return {"success": False, "error": "Web links must use HTTP, HTTPS, or mailto."}, 200
        try:
            import webbrowser
            webbrowser.open(target)
        except Exception as e:
            print(f"[webbrowser.open error]: {e}")
        display_name = assistant.browser_tool._display(target)
        return {"success": True, "output": f"Opening {display_name}.", "tool": "browser", "data": {"url": target}}, 200

    # Direct apps launching / closing on local desktop
    if action.tool == "apps":
        with _assistant_lock:
            outcome = assistant.router.dispatch(action)
        return {
            "success": outcome.ok,
            "output": outcome.spoken,
            "tool": outcome.tool,
            "data": outcome.result.data if outcome.result else {},
        }, 200
    risk = tool.risk_for(**action.params)
    summary = assistant.router._summarise(tool, action.params)
    if risk is not Risk.LOW:
        token = uuid.uuid4().hex
        with _pending_web_actions_lock:
            _pending_web_actions[token] = {
                "action": action,
                "user": user,
                "assistant": assistant,
                "command": command_origin,
                "expires": time.time() + 180,
            }
        return {
            "success": True,
            "confirmation_required": True,
            "confirmation_token": token,
            "prompt": f"Allow {action.tool} to {summary}?",
        }, 200
    with _assistant_lock:
        outcome = assistant.router.dispatch(action)
    result_data = outcome.result.data if outcome.result else {}
    if action.tool == "image" and result_data.get("path"):
        result_data = dict(result_data)
        result_data["image_url"] = f"/api/images/{os.path.basename(result_data['path'])}"
    return {
        "success": outcome.ok,
        "output": outcome.spoken,
        "tool": outcome.tool,
        "data": result_data,
    }, 200


def _web_confirm(token, user, approved, lang="en-US"):
    with _pending_web_actions_lock:
        pending = _pending_web_actions.pop(token, None)
    if pending is None or pending["expires"] < time.time() or pending["user"] != user:
        return {"success": False, "error": "This confirmation has expired. Please try again."}, 410
    if not approved:
        message = "Action cancelled."
        if lang in ("hi-IN", "mr-IN"):
            message = translate_text(message, source="en", target="hi" if lang == "hi-IN" else "mr")
        if pending.get("command"):
            assistant = pending["assistant"]
            assistant.context.add_assistant(message)
            assistant.memory.log("assistant", message)
            save_chat_turn(user, "ai", message, "VARSHA RESPONSE")
        return {"success": True, "output": message}, 200
    assistant = pending["assistant"]
    with _assistant_lock:
        assistant.permissions.set_confirmer(lambda _prompt: True)
        try:
            outcome = assistant.router.dispatch(pending["action"])
        finally:
            assistant.permissions.set_confirmer(None)
    output = outcome.spoken
    if lang in ("hi-IN", "mr-IN") and not re.search(r"[\u0900-\u097F]", output):
        output = translate_text(output, source="en", target="hi" if lang == "hi-IN" else "mr")
    result_data = outcome.result.data if outcome.result else {}
    if pending["action"].tool == "image" and result_data.get("path"):
        result_data = dict(result_data)
        result_data["image_url"] = f"/api/images/{os.path.basename(result_data['path'])}"
    result = {
        "success": outcome.ok,
        "output": output,
        "tool": outcome.tool,
        "data": result_data,
    }
    if pending.get("command"):
        if outcome.ok:
            assistant.context.add_tool(outcome.tool, outcome.spoken)
            assistant._note_context(pending["action"])
        assistant.context.add_assistant(output)
        assistant.memory.log("assistant", output)
        save_chat_turn(user, "ai", output, "VARSHA RESPONSE")
    return result, 200

qa_engine = None
if QAEngine is not None:
    try:
        qa_engine = QAEngine()
    except Exception as e:
        print(f"[app.py] QAEngine init failed: {e}")

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

# ==========================================
# AUTHENTICATION (EMAIL / PHONE OTP)
# ==========================================
@app.route("/api/auth/send-otp", methods=["POST"])
def send_otp():
    """Generates an OTP for Email or Mobile Number and returns demo notification."""
    data = request.get_json(force=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    auth_type = data.get("type", "email")  # 'email' or 'phone'

    if not identifier:
        return jsonify({"success": False, "error": "Identifier required"}), 400

    otp = str(secrets.randbelow(900000) + 100000)
    _OTP_STORE[identifier] = {
        "otp": otp,
        "expires": time.time() + 300  # 5 minutes validity
    }

    # This is a local demo profile flow; real email/SMS delivery needs a provider.
    return jsonify({
        "success": True,
        "message": f"Verification code generated for {identifier}",
        "demo_otp": otp
    })

@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(force=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    otp = data.get("otp", "").strip()

    entry = _OTP_STORE.get(identifier)
    if not entry:
        return jsonify({"success": False, "error": "No OTP requested for this identifier."}), 400

    if time.time() > entry["expires"]:
        return jsonify({"success": False, "error": "OTP has expired. Please request a new one."}), 400

    if entry["otp"] != otp:
        return jsonify({"success": False, "error": "Invalid verification code."}), 400

    # Save user into DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (identifier, type) VALUES (?, ?)", (identifier, "email" if "@" in identifier else "phone"))
    conn.commit()
    conn.close()

    del _OTP_STORE[identifier]
    return jsonify({
        "success": True,
        "identifier": identifier,
        "user_name": identifier.split("@")[0] if "@" in identifier else identifier
    })

# ==========================================
# CHAT HISTORY PERSISTENCE
# ==========================================
@app.route("/api/history", methods=["GET"])
def get_chat_history():
    user = _current_web_user()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT sender, message, tag, timestamp FROM chat_history WHERE user_identifier = ? ORDER BY id ASC LIMIT 100", (user,))
    rows = c.fetchall()
    conn.close()

    history = [dict(r) for r in rows]
    return jsonify({"history": history})

@app.route("/api/history/clear", methods=["POST"])
def clear_chat_history():
    data = request.get_json(force=True) or {}
    user = _current_web_user()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_identifier = ?", (user,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

def save_chat_turn(user: str, sender: str, message: str, tag: str = ""):
    try:
        if not user:
            user = _current_web_user()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO chat_history (user_identifier, sender, message, tag) VALUES (?, ?, ?, ?)",
                  (user or "default", sender, message, tag))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[save_chat_turn error]: {e}")

# ==========================================
# SYSTEM TELEMETRY & VOICE
# ==========================================
@app.route("/api/status", methods=["GET"])
def system_status():
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(PROJECT_ROOT)
        net = psutil.net_io_counters()
        battery = psutil.sensors_battery()
        bat_pct = battery.percent if battery else 100
        power_plugged = battery.power_plugged if battery else True

        return jsonify({
            "status": "OPTIMAL",
            "cpu": {"percent": round(cpu_pct, 1), "count": psutil.cpu_count()},
            "memory": {"percent": round(mem.percent, 1), "used_gb": round(mem.used / (1024**3), 2), "total_gb": round(mem.total / (1024**3), 2)},
            "storage": {"percent": round(disk.percent, 1), "free_gb": round(disk.free / (1024**3), 2), "total_gb": round(disk.total / (1024**3), 2)},
            "power": {"percent": int(bat_pct), "plugged": power_plugged},
            "net": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
            "voice": {
                "tts_available": _get_tts().available if _get_tts() else False,
                "stt_available": _get_stt().available if _get_stt() else False,
                "device_index": _get_stt().device_index if _get_stt() else None
            },
            "time": time.strftime("%H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/listen", methods=["POST"])
def voice_listen():
    data = request.get_json(silent=True) or {}
    try:
        timeout = max(1, min(int(data.get("timeout", 6)), 15))
        phrase_limit = max(1, min(int(data.get("phrase_time_limit", 10)), 20))
    except (TypeError, ValueError):
        return jsonify({"success": False, "status": "error", "text": "", "error": "Invalid listen duration."}), 400
    device_override = data.get("device_index", None)
    lang = data.get("lang", "en-US")

    try:
        if sr is None:
            return jsonify({"success": False, "status": "error", "text": "", "error": "SpeechRecognition unavailable"}), 500
        r = sr.Recognizer()
        r.energy_threshold = 200
        r.dynamic_energy_threshold = True
        r.pause_threshold = 0.8

        dev_idx = device_override if device_override is not None else (_get_stt().device_index if _get_stt() else None)
        mic_kwargs = {}
        if dev_idx is not None and dev_idx >= 0:
            mic_kwargs["device_index"] = dev_idx

        with sr.Microphone(**mic_kwargs) as source:
            r.adjust_for_ambient_noise(source, duration=0.6)
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)

        text = r.recognize_google(audio, language=lang)
        if text:
            return jsonify({"success": True, "status": "ok", "text": text.strip()})
        return jsonify({"success": False, "status": "unclear", "text": "", "error": "Speech was unclear."})
    except sr.WaitTimeoutError:
        return jsonify({"success": False, "status": "silence", "text": "", "error": "No speech detected (timeout)."})
    except sr.UnknownValueError:
        return jsonify({"success": False, "status": "unclear", "text": "", "error": "Speech not understood."})
    except Exception as e:
        return jsonify({"success": False, "status": "error", "text": "", "error": str(e)})

@app.route("/api/voice/speak", methods=["POST"])
def voice_speak():
    data = request.get_json(force=True) or {}
    text_to_say = data.get("text", "").strip()
    lang = data.get("lang", "auto")
    if not text_to_say:
        return jsonify({"error": "Empty text"}), 400

    # Determine target language for TTS
    # Supports English (default), Hindi (hi), and Marathi (mr)
    if lang.startswith("hi"):
        target_lang = "hi"
    elif lang.startswith("mr"):
        target_lang = "mr"
    elif lang == "auto":
        # Auto-detect Devanagari (Hindi/Marathi) text
        target_lang = "hi" if is_non_english_text(text_to_say) else "en"
    else:
        target_lang = "en"

    if target_lang == "hi" or target_lang == "mr":
        try:
            from gtts import gTTS
            tts = gTTS(text=text_to_say, lang=target_lang)
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            audio_b64 = base64.b64encode(fp.getvalue()).decode("utf-8")
            return jsonify({"success": True, "audio_base64": audio_b64, "format": "audio/mp3", "lang": target_lang})
        except Exception as e:
            print(f"[voice_speak] gTTS {target_lang} error: {e}")

    try:
        engine = _get_tts()
        if engine and engine.available:
            engine.speak(text_to_say)
            return jsonify({"success": True, "lang": "en"})
        return jsonify({"success": False, "error": "TTS engine unavailable"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ==========================================
# COMMAND EXECUTION (WITH FULL HINDI TRANSLATION)
# ==========================================
@app.route("/api/command", methods=["POST"])
def execute_command():
    data = request.get_json(force=True) or {}
    command_text = data.get("command", "").strip()
    lang = data.get("lang", "en-US")
    user = _current_web_user()
    is_indic_mode = (lang in ("hi-IN", "mr-IN") or is_non_english_text(command_text))
    target_lang = "mr" if lang == "mr-IN" else ("hi" if (lang == "hi-IN" or is_hindi_text(command_text)) else "en")

    if not command_text:
        return jsonify({"error": "Empty command"}), 400

    user_tag = "OPERATOR // MARATHI" if lang == "mr-IN" else ("OPERATOR // HINDI" if is_indic_mode else "OPERATOR")
    save_chat_turn(user, "user", command_text, user_tag)

    asst = get_assistant()
    if asst is None:
        return jsonify({"success": False, "error": "Assistant is unavailable."}), 503
    try:
        internal_cmd = command_text
        if is_indic_mode and re.search(r"[\u0900-\u097F]", command_text):
            internal_cmd = translate_text(command_text, source=target_lang, target="en")

        with _assistant_lock:
            asst.context.add_user(internal_cmd)
            asst.memory.log("user", internal_cmd)
            response = asst.engine.respond(internal_cmd, asst.context)
            tool_result = {}
            if response.has_action:
                result, status = _web_execute(response.action, user, asst)
                if result.get("confirmation_required"):
                    if is_indic_mode:
                        result["prompt"] = translate_text(result["prompt"], source="en", target=target_lang)
                    result["is_hindi"] = is_indic_mode
                    return jsonify(result), status
                tool_result = result
                reply = result.get("output") or result.get("error", "The action failed.")
                if result.get("success") and result.get("tool"):
                    asst.context.add_tool(result["tool"], reply)
                    asst._note_context(response.action)
            else:
                reply = response.speech or ""

            # If fallback response ("I'm not sure..."), attempt Wikipedia / Knowledge lookup before giving up
            if not reply or "not sure what you'd like" in reply.lower():
                try:
                    from tools.wikipedia import WikipediaTool
                    wiki = WikipediaTool()
                    cleaned_q = re.sub(r"^(?:what is|what are|who is|who was|tell me about|explain|describe)\s+", "", internal_cmd, flags=re.IGNORECASE).strip()
                    cleaned_q = re.sub(r"^(?:an?|the)\s+", "", cleaned_q, flags=re.IGNORECASE).strip()
                    w_res = wiki.run(query=cleaned_q or internal_cmd)
                    if w_res.ok and w_res.message:
                        reply = w_res.message
                        tool_result = {"tool": "wikipedia", "data": w_res.data}
                except Exception:
                    pass

            if not reply:
                reply = "I'm online and listening. How can I assist you?"

            if is_indic_mode and not re.search(r"[\u0900-\u097F]", reply):
                reply = translate_text(reply, source="en", target=target_lang)

            asst.context.add_assistant(reply)
            asst.memory.log("assistant", reply)
    except Exception as e:
        app.logger.exception("Command failed")
        return jsonify({"success": False, "error": str(e)}), 500

    resp_tag = "JARVIS // MARATHI" if lang == "mr-IN" else ("JARVIS // HINDI" if is_indic_mode else "JARVIS RESPONSE")
    save_chat_turn(user, "ai", reply, resp_tag)
    return jsonify({"success": True, "response": reply, "is_hindi": is_indic_mode,
                    "tool": tool_result.get("tool"), "data": tool_result.get("data", {})})

# ==========================================
# STUDY & DOUBT SOLVER (WITH HINDI SUPPORT)
# ==========================================
@app.route("/api/study/subjects", methods=["GET"])
def study_subjects():
    if KB is None:
        return jsonify({"subjects": [], "error": "Study knowledge files are unavailable."}), 503
    KB._load_all()
    subjects = KB.subjects()
    data_summary = {s: len(KB._db.get(s, {})) for s in subjects}
    return jsonify({"subjects": subjects, "summary": data_summary})

@app.route("/api/study/ask", methods=["POST"])
def study_ask():
    data = request.get_json(force=True) or {}
    question = data.get("question", "").strip()
    subject = data.get("subject", "").strip() or None
    lang = data.get("lang", "en-US")
    user = _current_web_user()
    is_hindi_mode = (lang == "hi-IN" or is_hindi_text(question))

    if not question:
        return jsonify({"error": "Empty question"}), 400

    save_chat_turn(user, "user", question, "DOUBT // HINDI" if is_hindi_mode else "DOUBT")

    if KB is None:
        return jsonify({"error": "Study knowledge files are unavailable."}), 503
    KB._load_all()
    search_q = question
    if is_hindi_mode:
        search_q = translate_text(question, source="mr" if lang == "mr-IN" else "hi", target="en")

    local_hit = None
    if subject:
        local_hit = KB.search(subject, search_q)
    else:
        for s in KB.subjects():
            res = KB.search(s, search_q)
            if res:
                local_hit = res
                subject = s
                break

    ans_text = ""
    ans_source = ""
    ans_subject = subject or "General"
    ans_topic = question

    if local_hit:
        topic, content = next(iter(local_hit.items()))
        ans_source = "LOCAL_KNOWLEDGE_BASE"
        ans_subject = subject
        ans_topic = topic
        ans_text = content
    else:
        asst = get_assistant()
        if asst:
            try:
                prompt = f"As an educational tutor for {subject or 'all students'}, provide a clear, concise step-by-step conceptual answer to this student question: {search_q}"
                ans_text = asst.handle(prompt, speak=False)
                ans_source = "AI_NEURAL_SOLVER"
            except Exception as e:
                ans_text = f"Solver error: {e}"
                ans_source = "ERROR"
        else:
            ans_text = "No entry found in local database."
            ans_source = "NOT_FOUND"

    if is_hindi_mode and not re.search(r"[\u0900-\u097F]", ans_text):
        ans_text = translate_text(ans_text, source="en", target="mr" if lang == "mr-IN" else "hi")

    save_chat_turn(user, "ai", ans_text, f"{ans_source} // हिन्दी" if is_hindi_mode else f"{ans_source} // {ans_subject}")

    return jsonify({
        "source": ans_source,
        "subject": ans_subject,
        "topic": ans_topic,
        "answer": ans_text,
        "is_hindi": is_hindi_mode
    })

@app.route("/api/exam/quiz", methods=["GET"])
def exam_quiz():
    try:
        from tools.exam_prep import ExamPrepTool
        tool = ExamPrepTool()
        exam_type = request.args.get("exam", "NEET")
        subject = request.args.get("subject", "")
        lang = request.args.get("lang", "en-US")
        res = tool.run(action="quiz", exam=exam_type, subject=subject)
        out = res.spoken
        if lang in ("hi-IN", "mr-IN"):
            out = translate_text(out, source="en", target="hi" if lang == "hi-IN" else "mr")
        return jsonify({"output": out, "raw": res.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools", methods=["GET"])
def list_tools():
    assistant = get_assistant()
    if assistant is None:
        return jsonify({"tools": []}), 503
    tools = [schema for schema in assistant.router.schemas()]
    return jsonify({"tools": tools})


@app.route("/api/tool/execute", methods=["POST"])
def execute_tool_direct():
    data = request.get_json(silent=True) or {}
    tool_name = str(data.get("tool", "")).strip().lower()
    user = _current_web_user()
    if not tool_name:
        return jsonify({"success": False, "error": "Tool name is required."}), 400
    params = {key: value for key, value in data.items() if key not in {"tool", "lang", "user"}}
    result, status = _web_execute(ActionRequest(tool=tool_name, params=params), user)
    lang = data.get("lang")
    if result.get("output") and lang in ("hi-IN", "mr-IN") and not re.search(r"[\u0900-\u097F]", result["output"]):
        result["output"] = translate_text(result["output"], source="en", target="hi" if lang == "hi-IN" else "mr")
    if result.get("confirmation_required") and lang in ("hi-IN", "mr-IN"):
        result["prompt"] = translate_text(result["prompt"], source="en", target="hi" if lang == "hi-IN" else "mr")
    return jsonify(result), status


@app.route("/api/confirm", methods=["POST"])
def confirm_web_action():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token", ""))
    user = _current_web_user()
    result, status = _web_confirm(token, user, bool(data.get("approved")), data.get("lang", "en-US"))
    return jsonify(result), status


@app.route("/api/images/<path:filename>", methods=["GET"])
def serve_generated_image(filename):
    image_dir = os.path.join(WEB_FILES_DIR, _current_web_user(), "images")
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return jsonify({"error": "Image not found."}), 404
    return send_from_directory(image_dir, safe_name, conditional=True)

if __name__ == "__main__":
    print("=" * 60)
    print(" VARSHA WEB ASSISTANT & STUDY CORE ONLINE")
    print(" [AUTH SYSTEM]  Email / Mobile Phone OTP Auth Enabled")
    print(" [PERSISTENCE]  SQLite Chat History Active")
    print(" [TRANSLATION]  100% Hindi Universal Mode Active")
    print("=" * 60)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
