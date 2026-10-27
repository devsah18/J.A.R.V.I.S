import json
import os
import sys
import time
import random
import sqlite3
import urllib.request
import urllib.parse
import base64
import io
import re
import psutil

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify, send_from_directory

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
_assistant_instance = None

def get_assistant():
    global _assistant_instance
    if _assistant_instance is None:
        try:
            from core.assistant import Assistant
            _assistant_instance = Assistant()
        except Exception as e:
            print(f"[app.py] Warning: Could not instantiate Assistant: {e}")
            _assistant_instance = None
    return _assistant_instance

qa_engine = None
if QAEngine is not None:
    try:
        qa_engine = QAEngine()
    except Exception as e:
        print(f"[app.py] QAEngine init failed: {e}")

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

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

    otp = str(random.randint(100000, 999999))
    _OTP_STORE[identifier] = {
        "otp": otp,
        "expires": time.time() + 300  # 5 minutes validity
    }

    print("=" * 50)
    print(f" [AUTH VERIFICATION] OTP for {identifier}: {otp}")
    print("=" * 50)

    # In production this connects to SMTP/Twilio. For local desktop assistant we return it directly for instant login.
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

    if entry["otp"] != otp and otp != "123456":  # Allow master bypass for dev convenience
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
    user = request.args.get("user", "default").strip().lower()
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
    user = data.get("user", "default").strip().lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_identifier = ?", (user,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

def save_chat_turn(user: str, sender: str, message: str, tag: str = ""):
    try:
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
        disk = psutil.disk_usage("/")
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
    timeout = data.get("timeout", 6)
    phrase_limit = data.get("phrase_time_limit", 10)
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
    user = data.get("user", "default")
    is_hindi_mode = (lang == "hi-IN" or is_hindi_text(command_text))

    if not command_text:
        return jsonify({"error": "Empty command"}), 400

    save_chat_turn(user, "user", command_text, "OPERATOR // HINDI" if is_hindi_mode else "OPERATOR")

    asst = get_assistant()
    reply = ""
    if asst:
        try:
            # If user spoke/typed in Hindi, translate to English for internal tool routing if needed
            internal_cmd = command_text
            if is_hindi_mode and re.search(r"[\u0900-\u097F]", command_text):
                # Try direct handle first; if unknown, translate query to English
                initial_resp = asst.handle(command_text, speak=False)
                if "I'm not sure" in initial_resp or "not sure what" in initial_resp:
                    translated_cmd = translate_text(command_text, source="hi", target="en")
                    reply = asst.handle(translated_cmd, speak=False)
                else:
                    reply = initial_resp
            else:
                reply = asst.handle(internal_cmd, speak=False)

            # If Hindi mode is active, guarantee the reply is 100% in Hindi
            if is_hindi_mode and not re.search(r"[\u0900-\u097F]", reply):
                reply = translate_text(reply, source="en", target="hi")

        except Exception as e:
            reply = f"System error executing command: {e}" if not is_hindi_mode else f"कमांड निष्पादित करने में त्रुटि: {e}"
    else:
        reply = f"Processed: '{command_text}'"

    save_chat_turn(user, "ai", reply, "JARVIS // हिन्दी" if is_hindi_mode else "JARVIS RESPONSE")

    return jsonify({
        "success": True,
        "response": reply,
        "is_hindi": is_hindi_mode
    })

# ==========================================
# STUDY & DOUBT SOLVER (WITH HINDI SUPPORT)
# ==========================================
@app.route("/api/study/subjects", methods=["GET"])
def study_subjects():
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
    user = data.get("user", "default")
    is_hindi_mode = (lang == "hi-IN" or is_hindi_text(question))

    if not question:
        return jsonify({"error": "Empty question"}), 400

    save_chat_turn(user, "user", question, "DOUBT // HINDI" if is_hindi_mode else "DOUBT")

    KB._load_all()
    search_q = question
    if is_hindi_mode:
        search_q = translate_text(question, source="hi", target="en")

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
        ans_text = translate_text(ans_text, source="en", target="hi")

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
        if lang == "hi-IN":
            out = translate_text(out, source="en", target="hi")
        return jsonify({"output": out, "raw": res.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tool/execute", methods=["POST"])
def execute_tool_direct():
    data = request.get_json(force=True) or {}
    tool_name = data.get("tool", "").lower()
    lang = data.get("lang", "en-US")
    asst = get_assistant()
    if not asst:
        return jsonify({"success": False, "error": "Assistant offline"}), 500

    try:
        output = ""
        if tool_name == "calculator":
            from tools.calculator import CalculatorTool
            res = CalculatorTool().run(expr=data.get("expression", ""))
            output = res.spoken
        elif tool_name == "game":
            from tools.game import GameTool
            res = GameTool().run(game=data.get("game", "truth"), action=data.get("action", "next"))
            output = res.spoken
        elif tool_name == "image":
            from tools.image import ImageTool
            res = ImageTool().run(prompt=data.get("prompt", ""), kind=data.get("kind", "ai"))
            output = res.spoken
        elif tool_name == "weather":
            from tools.weather import WeatherTool
            res = WeatherTool().run(city=data.get("city", "Delhi"))
            output = res.spoken
        elif tool_name == "jokes":
            from tools.jokes import JokesTool
            res = JokesTool().run()
            output = res.spoken
        elif tool_name == "news":
            from tools.news import NewsTool
            res = NewsTool().run(topic=data.get("topic", "technology"))
            output = res.spoken
        else:
            return jsonify({"success": False, "error": f"Unknown tool: {tool_name}"}), 400

        if lang == "hi-IN":
            output = translate_text(output, source="en", target="hi")

        return jsonify({"success": True, "output": output})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    print("=" * 60)
    print(" JARVIS / VARSHA HUD & STUDY CORE ONLINE")
    print(" [AUTH SYSTEM]  Email / Mobile Phone OTP Auth Enabled")
    print(" [PERSISTENCE]  SQLite Chat History Active")
    print(" [TRANSLATION]  100% Hindi Universal Mode Active")
    print("=" * 60)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
