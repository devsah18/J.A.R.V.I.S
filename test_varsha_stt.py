import logging
import sys
import config
from voice.speech_to_text import SpeechToText

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone speech diagnostic")

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("Testing VARSHA SpeechToText directly...")
print("="*50)

try:
    # Create STT engine with settings from .env
    stt = SpeechToText(
        language="en-US",
        energy_threshold=150,
        pause_threshold=0.8,
        listen_timeout=10,
        phrase_time_limit=15,
        enabled=True,
        device_index=config.STT_DEVICE_INDEX,
    )
    
    print(f"STT available: {stt.available}")
    print(f"Device index: {stt.device_index}")
    print(f"Recognizer: {stt._recognizer}")
    print(f"Mic OK: {stt._mic_ok}")
    
    if not stt.available:
        print("STT not available! Checking why...")
        import speech_recognition as sr
        print(f"speech_recognition available: {sr is not None}")
        if stt._recognizer is None:
            print("Recognizer is None")
        if not stt._mic_ok:
            print("Mic probe failed")
            
        # Test mic probe manually
        try:
            mic = stt.get_microphone()
            print(f"Microphone object: {mic}")
        except Exception as e:
            print(f"Error getting microphone: {e}")
    
    else:
        print("STT is available, testing listen...")
        print("Say something loudly (you have 10 seconds)...")
        result = stt.listen(timeout=10, phrase_limit=15)
        print(f"Listen result: status={result.status}, text='{result.text}'")
        
        if result.status == "ok":
            print(f"SUCCESS: Recognized '{result.text}'")
        elif result.status == "unclear":
            print("UNCLEAR: Audio detected but not understood")
        elif result.status == "silence":
            print("SILENCE: No speech detected")
        elif result.status == "unavailable":
            print("UNAVAILABLE: Microphone not available")
        else:
            print(f"ERROR: {result.status}")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
