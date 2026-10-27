"""Quick interactive microphone diagnostic tool for JARVIS."""

import sys
try:
    import speech_recognition as sr
except ImportError:
    sr = None
from voice.speech_to_text import SpeechToText

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone microphone diagnostic")

def main():
    print("=" * 60)
    print(" JARVIS MICROPHONE DIAGNOSTIC")
    print("=" * 60)

    if sr is None:
        print("SpeechRecognition is not installed; run: python -m pip install -r requirements.txt")
        return
    mics = sr.Microphone.list_microphone_names()
    print(f"\n[1] Detected {len(mics)} audio devices:")
    for idx, name in enumerate(mics[:10]):
        print(f"    Index {idx}: {name}")

    print("\n[2] Testing default microphone...")
    stt = SpeechToText()
    if not stt.available:
        print("ERROR: Microphone backend not available.")
        return

    print("    Calibrating ambient noise (please be quiet for 1 sec)...")
    ambient = stt.calibrate(duration=1.0)
    print(f"    Ambient noise level: {ambient:.1f} (energy threshold)")

    print("\n[3] Speak a sentence into your microphone now (5 seconds)...")
    result = stt.listen(timeout=7, phrase_limit=10)

    print(f"\n[4] Result: status='{result.status}'")
    if result.status == "ok":
        print(f"    SUCCESS! Transcribed text: \"{result.text}\"")
    elif result.status == "silence":
        print("    No speech detected. Check if your microphone is muted or volume is low.")
    elif result.status == "unclear":
        print("    Audio was detected, but Google Speech could not understand the words. Try speaking closer to the mic.")
    else:
        print(f"    Status: {result.status}")

if __name__ == "__main__":
    main()

