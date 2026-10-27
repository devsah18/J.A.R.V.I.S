try:
    import speech_recognition as sr
except ImportError:
    sr = None
import time

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone microphone diagnostic")

print("Testing microphone access...")
try:
    if sr is None:
        raise RuntimeError("SpeechRecognition is not installed; run: python -m pip install -r requirements.txt")
    # List microphones
    mics = sr.Microphone.list_microphone_names()
    print(f"Found {len(mics)} microphone devices")
    
    # Test first few microphones for signal
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 150
    recognizer.dynamic_energy_threshold = True
    
    print("\nTesting microphone signal (speak now)...")
    with sr.Microphone() as source:
        print("Adjusting for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print(f"Energy threshold set to: {recognizer.energy_threshold}")
        print("Listening for speech (say something)...")
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        print("Audio captured, attempting recognition...")
        text = recognizer.recognize_google(audio)
        print(f"You said: {text}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
